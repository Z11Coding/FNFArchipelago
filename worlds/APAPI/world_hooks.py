from __future__ import annotations

"""Per-instance and class-level world method hooks."""

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

HookBefore = Callable[..., Any]
HookAfter = Callable[..., Any]
HookWrapper = Callable[..., Any]
Unhook = Callable[[], None]


def hook_world_method(
    world_instance: "World",
    method_name: str,
    *,
    before: HookBefore | None = None,
    after: HookAfter | None = None,
    wrapper: HookWrapper | None = None,
) -> Unhook:
    """Input: instance, method, hooks. Returns: unhook callable."""
    game: str = str(getattr(world_instance, "game", "?"))
    original: Any | None = getattr(world_instance, method_name, None)
    if not callable(original):
        dprint("hooks", f"FAILED to hook {game}.{method_name}: no such callable")
        raise AttributeError(f"{game}: has no callable {method_name!r}")
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
    """Input: base, before, after, args, kwargs. Returns: result."""
    cancelled: bool = False
    if before is not None:
        decision: Any = before(*args, **kwargs)
        if decision is CANCEL:
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
    """Input: multiworld, game, method, hooks. Returns: list of unhooks."""
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
    sync_existing: bool = False,
    as_static: bool = False,
) -> Unhook | None:
    """Patch a world class method and optionally sync existing instances.

    Args: game, method name, hooks, sync, static flag.
    Returns unhook or None. If sync_existing, also patches live worlds
    in the current multiworld. If as_static, installs as staticmethod.
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
                def bound_next(*n_args: Any, **n_kwargs: Any) -> Any:
                    return _run_with_before_after(
                        base, before, after,
                        (self, *(n_args or args)), dict(n_kwargs or kwargs))

                return wrapper(bound_next, self, *args, **kwargs)
            return _run_with_before_after(base, before, after, (self, *args), kwargs)

    patched.__apapi_unwrapped__ = base  # type: ignore[attr-defined]
    if as_static:
        setattr(world_type, method_name, staticmethod(patched))
        dprint("hooks", f"patched class {label}.{method_name} as staticmethod successfully")
    else:
        setattr(world_type, method_name, patched)
        dprint("hooks", f"patched class {label}.{method_name} successfully")

    if sync_existing:
        try:
            from .multiworld_api import get_current_multiworld, has_current_multiworld
            if has_current_multiworld():
                mw = get_current_multiworld()
                for pid in list(getattr(mw, "player_ids", [])):
                    try:
                        w = mw.worlds[pid]
                    except Exception:
                        continue
                    if getattr(w, "game", None) != label and not (isinstance(game, type) and isinstance(w, game)):
                        continue
                    try:
                        if as_static:
                            setattr(w, method_name, getattr(world_type, method_name))
                        else:
                            # Sync by hooking instance or rebinding to new class method
                            # Prefer hooking to keep before/after parity
                            hook_world_method(w, method_name, before=before, after=after, wrapper=wrapper)
                        dprint("hooks", f"synced existing instance {label}.{method_name} for player {pid}")
                    except Exception as exc:
                        logger.warning("APAPI sync_existing failed for %s.%s player %s: %s", label, method_name, pid, exc)
        except Exception as exc:
            logger.warning("APAPI sync_existing check failed for %s.%s: %s", label, method_name, exc)

    def unhook() -> None:
        try:
            setattr(world_type, method_name, original)
            dprint("hooks", f"unpatched class {label}.{method_name}")
        except Exception as exc:
            logger.warning("APAPI unpatch failed for %s.%s: %s", label, method_name, exc)

    return unhook


__all__ = ["CANCEL", "HookAfter", "HookBefore", "HookWrapper", "Unhook",
           "hook_world_method", "hook_worlds_for_game", "patch_world_class_method"]
