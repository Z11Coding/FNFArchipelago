from __future__ import annotations

"""Per-instance world method hooks for APAPI.

Design constraints (custom_worlds-only):
- We cannot safely rewrite other worlds' classes at import time because
  load order is undefined and class patching leaks across generations.
- Instead, add-on worlds call these helpers from their own
  ``generate_early`` (which runs before the target stage) to wrap specific
  world *instances* already present in ``multiworld.worlds``.

Each hook supports:
- ``before``: runs first, may return ``False`` to cancel the original call.
- ``after``: runs after, may return a replacement result.
- ``wrapper``: full ``(next_callable, *args, **kwargs)`` control; if it never
  calls ``next_callable`` the original operation is cancelled.
"""

from collections.abc import Callable
import functools
import logging
import time
from typing import Any, TYPE_CHECKING

from .debug import dprint, hook_timer

if TYPE_CHECKING:
    from BaseClasses import MultiWorld
    from worlds.AutoWorld import World

logger = logging.getLogger("APAPI")

CANCEL = object()
"""Sentinel a ``before`` hook may return to cancel the original call."""

#: A ``before`` hook receives ``(*args, **kwargs)``; returning ``False`` or
#: ``CANCEL`` cancels the original call.
HookBefore = Callable[..., Any]
#: An ``after`` hook receives ``(result, *args, **kwargs)`` and may return a
#: replacement result (``None`` keeps the original).
HookAfter = Callable[..., Any]
#: A full wrapper receives ``(next_callable, *args, **kwargs)``; skipping
#: ``next_callable`` cancels the original operation.
HookWrapper = Callable[..., Any]
#: Restores a previously installed hook.
Unhook = Callable[[], None]


def hook_world_method(
    world_instance: "World",
    method_name: str,
    *,
    before: HookBefore | None = None,
    after: HookAfter | None = None,
    wrapper: HookWrapper | None = None,
) -> Unhook:
    """Wrap ``world_instance.method_name`` with hook behavior.

    Returns an unhook callable restoring the original bound method.
    ``before`` receives ``(*args, **kwargs)``; returning ``False`` or
    ``CANCEL`` cancels the original call (result becomes ``None`` unless an
    ``after`` hook replaces it). ``after`` receives ``(result, *args,
    **kwargs)`` and may return a replacement result.
    """
    game: str = str(getattr(world_instance, "game", "?"))
    original: Any | None = getattr(world_instance, method_name, None)
    if not callable(original):
        dprint("hooks", f"FAILED to hook {game}.{method_name}: no such callable")
        raise AttributeError(f"{game}: has no callable {method_name!r}")
    # Unwrap any previous APAPI hook to keep chains short and idempotent-ish.
    base: Callable[..., Any] = getattr(original, "__apapi_unwrapped__", original)

    @functools.wraps(base)
    def hooked(*args: Any, **kwargs: Any) -> Any:
        start: float = time.perf_counter()
        try:
            if wrapper is not None:
                def next_callable(*n_args: Any, **n_kwargs: Any) -> Any:
                    return _run_with_before_after(base, before, after, n_args or args, n_kwargs or kwargs)

                return wrapper(next_callable, *args, **kwargs)
            return _run_with_before_after(base, before, after, args, kwargs)
        finally:
            from .debug import record_hook_time
            record_hook_time(game, method_name, time.perf_counter() - start)

    hooked.__apapi_unwrapped__ = base  # type: ignore[attr-defined]
    # NOTE: plain instance attribute (no descriptor binding): functions set
    # on an instance do not receive `self` automatically, and `base` above
    # is already a bound method, so `hooked(*args)` matches the original
    # call signature exactly.
    setattr(world_instance, method_name, hooked)
    dprint("hooks", f"hooked {game}.{method_name} successfully")

    def unhook() -> None:
        try:
            setattr(world_instance, method_name, original)
            dprint("hooks", f"unhooked {game}.{method_name}")
        except Exception as exc:
            logger.warning("APAPI unhook failed for %s: %s", method_name, exc)

    return unhook


def _run_with_before_after(
    base: Callable[..., Any],
    before: HookBefore | None,
    after: HookAfter | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    cancelled: bool = False
    if before is not None:
        decision: Any = before(*args, **kwargs)
        if decision is False or decision is CANCEL:
            cancelled = True
    result: Any = None if cancelled else base(*args, **kwargs)
    if after is not None:
        replaced: Any = after(result, *args, **kwargs)
        if replaced is not None:
            result = replaced
    return result


def hook_worlds_for_game(
    multiworld: "MultiWorld",
    game: str,
    method_name: str,
    *,
    before: HookBefore | None = None,
    after: HookAfter | None = None,
    wrapper: HookWrapper | None = None,
) -> list[Unhook]:
    """Hook ``method_name`` on every world instance of ``game`` in this multiworld."""
    unhooks: list[Unhook] = []
    hooked_count: int = 0
    for player in list(getattr(multiworld, "player_ids", [])):
        try:
            world: Any = multiworld.worlds[player]
        except Exception:
            continue
        if getattr(world, "game", None) != game:
            continue
        try:
            unhooks.append(hook_world_method(world, method_name, before=before, after=after, wrapper=wrapper))
            hooked_count += 1
        except Exception as exc:
            logger.warning("APAPI could not hook %s.%s: %s", game, method_name, exc)
    dprint("hooks", f"hooked {hooked_count} instance(s) of {game}.{method_name}")
    return unhooks


def patch_world_class_method(
    game: str | type,
    method_name: str,
    *,
    before: HookBefore | None = None,
    after: HookAfter | None = None,
    wrapper: HookWrapper | None = None,
) -> Unhook | None:
    """Patch ``method_name`` on the world *class* for ``game`` (all instances).

    ``game`` may be a game-name string (resolved via the registry — None if
    not loaded) or a world class directly when the caller already has access
    to it (patched as-is, no lookup needed).

    Intended for use from :func:`worlds.APAPI.world_ready.when_game_available`
    callbacks, i.e. after loading completes, so load order cannot prevent the
    patch. Idempotent per ``(game, method)``: repeat calls replace the
    previously installed APAPI wrapper instead of stacking. Returns an
    unhook callable, or None if the target cannot be resolved.
    """
    world_type: Any | None
    label: str
    if isinstance(game, str):
        try:
            from worlds.AutoWorld import AutoWorldRegister
        except Exception as exc:
            logger.warning("APAPI could not patch %s.%s (no registry): %s", game, method_name, exc)
            return None
        world_type = AutoWorldRegister.world_types.get(game)
        label = game
        if world_type is None:
            dprint("hooks", f"FAILED to patch {label}.{method_name}: game not loaded")
            return None
    elif isinstance(game, type):
        world_type = game
        name_attr: Any = getattr(game, "game", None)
        label = name_attr if isinstance(name_attr, str) else game.__name__
    else:
        raise TypeError(f"patch target must be a game name or world class, got {type(game).__name__}")
    original: Any | None = getattr(world_type, method_name, None)
    if not callable(original):
        dprint("hooks", f"FAILED to patch {label}.{method_name}: no such method")
        logger.warning("APAPI could not patch %s.%s: no such method", label, method_name)
        return None
    base: Callable[..., Any] = getattr(original, "__apapi_unwrapped__", original)

    @functools.wraps(base)
    def patched(self: Any, *args: Any, **kwargs: Any) -> Any:
        with hook_timer(label, method_name):
            if wrapper is not None:
                # Bind self explicitly: base is the unbound class function.
                def bound_next(*n_args: Any, **n_kwargs: Any) -> Any:
                    return _run_with_before_after(
                        base, before, after,
                        (self, *(n_args or args)), dict(n_kwargs or kwargs))

                return wrapper(bound_next, self, *args, **kwargs)
            return _run_with_before_after(base, before, after, (self, *args), kwargs)

    patched.__apapi_unwrapped__ = base  # type: ignore[attr-defined]
    setattr(world_type, method_name, patched)
    dprint("hooks", f"patched class {label}.{method_name} successfully")

    def unhook() -> None:
        try:
            setattr(world_type, method_name, original)
            dprint("hooks", f"unpatched class {label}.{method_name}")
        except Exception as exc:
            logger.warning("APAPI unpatch failed for %s.%s: %s", label, method_name, exc)

    return unhook


__all__ = ["CANCEL", "HookAfter", "HookBefore", "HookWrapper", "Unhook",
           "hook_world_method", "hook_worlds_for_game", "patch_world_class_method"]
