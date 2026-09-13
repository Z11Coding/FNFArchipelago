from __future__ import annotations

"""Centralized injection: the only place that waits for games or patches them.

Add-on packs stay declarative (``inject_option`` / ``inject_world_behavior``);
APAPI handles load-order waiting, patching, and option plumbing:

- options apply now when loaded, later via ``when_game_available`` or the
  register wrapper, with native ``__init__`` support (dataclass re-run) and
  a cooperative ``set_options`` wrapper so values always land;
- behavior patches are version-gated class patches firing on registration.
"""

import logging
import threading
from typing import Any, TYPE_CHECKING, Union

from .debug import dprint
from .world_hooks import HookAfter, HookBefore, HookWrapper
from .world_ready import on_worlds_loaded, when_game_available

if TYPE_CHECKING:
    from BaseClasses import MultiWorld
    from Options import Option
    from worlds.AutoWorld import World

logger = logging.getLogger("APAPI.Injection")

#: A game reference: either a game-name string (resolved via the registry,
#: waiting if needed) or a world class directly when the caller has access.
#: Union (not |) so this stays a runtime expression on every Python.
GameRef = Union[str, "type[World]"]

_registry_lock = threading.RLock()
#: option_key -> option class, applied to every game.
_global_options: dict[str, "type[Option[Any]]"] = {}
#: game -> {option_key -> option class}, applied only to that game.
_targeted_options: dict[str, dict[str, "type[Option[Any]]"]] = {}

_register_patched = False
_set_options_wrapped = False


def _clear_type_hint_cache() -> None:
    try:
        from Options import OptionsMetaProperty
        OptionsMetaProperty.type_hints.fget.cache_clear()
    except Exception:
        pass


def _pending_for_game(game: str) -> dict[str, "type[Option[Any]]"]:
    merged: dict[str, "type[Option[Any]]"] = dict(_global_options)
    merged.update(_targeted_options.get(game, {}))
    return merged


def _resolve_target(ref: GameRef) -> "tuple[str, type[World] | None]":
    """Normalize a game reference to ``(game_name, world_class_or_None)``.

    Strings resolve via the registry (None when not loaded — caller queues).
    Classes are used as-is since the caller already has access; the game
    name comes from the class's ``game`` attribute.
    """
    if isinstance(ref, str):
        try:
            from worlds.AutoWorld import AutoWorldRegister
            return ref, AutoWorldRegister.world_types.get(ref)
        except Exception:
            return ref, None
    if isinstance(ref, type):
        name: Any = getattr(ref, "game", None)
        if not isinstance(name, str):
            raise TypeError(
                f"World class {ref.__name__} has no string 'game' attribute; "
                "pass a game name instead.")
        return name, ref
    raise TypeError(f"Game reference must be a game name or world class, got {type(ref).__name__}")


def _apply_to_world(game: str, world_type: "type[World]") -> list[str]:
    """Apply all pending injections for ``game`` to an already-created world class."""
    try:
        options_dc: Any = world_type.options_dataclass
    except Exception:
        return []
    annotations: Any = getattr(options_dc, "__annotations__", None)
    if annotations is None:
        return []
    pending: dict[str, type] = _pending_for_game(game)
    if not pending:
        return []
    applied: list[str] = []
    fields: Any = getattr(options_dc, "__dataclass_fields__", {})
    for key, option_class in pending.items():
        if key in annotations and key in fields:
            continue  # already natively supported
        annotations[key] = option_class
        applied.append(key)
    if not applied:
        return []
    # Re-run dataclass processing so the generated __init__ natively accepts
    # the new keys (NoLogic achieves the same for future worlds via
    # __init_subclass__; post-hoc re-run is the targeted equivalent).
    # NOTE: dataclass() never overwrites an existing __init__/__repr__/__eq__
    # (_set_new_attribute guard), so those generated members must be removed
    # first. Option containers never define custom ones (verified by scan),
    # and originals are restored if regeneration fails.
    saved_dunder: dict[str, Any] = {}
    try:
        import dataclasses
        import inspect as _inspect
        for attr in ("__init__", "__repr__", "__eq__"):
            if attr in options_dc.__dict__:
                saved_dunder[attr] = options_dc.__dict__[attr]
                try:
                    delattr(options_dc, attr)
                except Exception:
                    saved_dunder.pop(attr, None)
        dataclasses.dataclass(options_dc)
        missing: list[str] = [key for key in applied
                              if key not in _inspect.signature(options_dc).parameters]
        if missing:
            raise TypeError(f"regenerated __init__ missing {missing}")
        dprint("inject", f"dataclass re-run ok for {game} options ({', '.join(applied)})")
    except Exception as exc:
        for attr, original in saved_dunder.items():
            try:
                setattr(options_dc, attr, original)
            except Exception:
                pass
        logger.warning("[APAPI:inject] dataclass re-run failed for %s options: %s "
                       "(falling back to set_options overflow handling)", game, exc)
    _clear_type_hint_cache()
    _sync_web_groups_for_world(game, world_type)
    dprint("inject", f"injected option(s) {', '.join(applied)} into {game}")
    return applied


def _sync_web_groups_for_world(game: str, world_type: "type[World]") -> None:
    """Insert injection option groups into the world's web option groups."""
    try:
        from .options_api import _build_group, _group_names, _insert_group_into
    except Exception:
        return
    with _registry_lock:
        wanted: dict[str, type] = _pending_for_game(game)
        group_names: list[str] = [
            name for name, (options, _collapsed) in _group_names.items()
            if any(option in wanted.values() for option in options)
        ]
    if not group_names:
        return
    try:
        web_class: Any = world_type.web.__class__
    except Exception:
        return
    for name in group_names:
        try:
            _insert_group_into(web_class.option_groups, _build_group(name))
        except Exception:
            continue


def _patch_autoworld_register() -> None:
    """Wrap the world metaclass so later-registered worlds get pending injections."""
    global _register_patched
    if _register_patched:
        return
    try:
        from worlds.AutoWorld import AutoWorldRegister
    except Exception as exc:
        logger.warning("[APAPI:inject] cannot wrap world register (no AutoWorld): %s", exc)
        return
    previous: Any = AutoWorldRegister.__new__

    def patched_new(mcs: Any, name: str, bases: Any, dct: Any) -> Any:
        cls: Any = previous(mcs, name, bases, dct)
        game: Any = dct.get("game") if isinstance(dct, dict) else None
        if isinstance(game, str):
            try:
                with _registry_lock:
                    _apply_to_world(game, cls)
            except Exception as exc:
                logger.warning("[APAPI:inject] late injection failed for %s: %s", game, exc)
        return cls

    try:
        AutoWorldRegister.__new__ = patched_new  # type: ignore[method-assign]
    except Exception as exc:
        logger.warning("[APAPI:inject] cannot wrap world register: %s", exc)
        return
    _register_patched = True
    dprint("inject", "world register wrapper installed")


def _attach_injected_values(multiworld: "MultiWorld", args: Any) -> None:
    """Attach injected option values to each world (runs after real set_options)."""
    with _registry_lock:
        snapshot: dict[str, dict[str, type]] = {game: dict(options)
                                                for game, options in _targeted_options.items()}
        global_snapshot: dict[str, type] = dict(_global_options)
    for player in list(getattr(multiworld, "player_ids", [])):
        try:
            world: Any = multiworld.worlds[player]
        except Exception:
            continue
        game: Any = getattr(world, "game", None)
        pending: dict[str, type] = dict(global_snapshot)
        if isinstance(game, str):
            pending.update(snapshot.get(game, {}))
        if not pending:
            continue
        for key, option_class in pending.items():
            if hasattr(world.options, key):
                continue  # native or previously attached value wins
            value: Any = None
            try:
                per_player: Any = getattr(args, key, None)
                value = per_player.get(player) if hasattr(per_player, "get") else None
            except Exception:
                value = None
            if value is None:
                try:
                    value = option_class.from_any(option_class.default)
                except Exception:
                    continue
            try:
                setattr(world.options, key, value)
            except Exception:
                continue


def _install_set_options_wrapper() -> None:
    """Wrap MultiWorld.set_options outermost so injected values always land."""
    global _set_options_wrapped
    if _set_options_wrapped:
        return
    try:
        from BaseClasses import MultiWorld
    except Exception as exc:
        logger.warning("[APAPI:inject] cannot wrap set_options (no BaseClasses): %s", exc)
        return
    if getattr(MultiWorld.set_options, "__apapi_inject_wrapped__", False):
        _set_options_wrapped = True
        return
    previous: Any = MultiWorld.set_options

    def apapi_set_options(self: Any, args: Any) -> None:
        previous(self, args)
        try:
            _attach_injected_values(self, args)
        except Exception as exc:
            logger.warning("[APAPI:inject] value attach failed: %s", exc)

    apapi_set_options.__apapi_inject_wrapped__ = True  # type: ignore[attr-defined]
    MultiWorld.set_options = apapi_set_options  # type: ignore[method-assign]
    _set_options_wrapped = True
    dprint("inject", "cooperative set_options wrapper installed")


def inject_option(
    option_key: str,
    option_class: "type[Option[Any]]",
    games: list[GameRef] | None = None,
    group_name: str = "APAPI Add-On Options",
    start_collapsed: bool = True,
) -> None:
    """Inject ``option_class`` under ``option_key`` so it acts native to those games.

    Each entry of ``games`` may be a game-name string (resolved via the
    registry, waiting if needed) or a world class directly when the caller
    already has access to it. ``games=None`` means every game (global, like
    No Logic's meta options). APAPI exclusively handles waiting: loaded
    worlds (or given classes) are patched now, missing names via
    :func:`when_game_available`, future worlds via the register wrapper.
    Generation ``args`` values are attached cooperatively at ``set_options``.
    """
    from .options_api import (
        _group_names,
        _patch_multiworld_set_options,
        _patch_webworld_register,
        _sync_webworld_groups,
    )

    with _registry_lock:
        if games is None:
            _global_options[option_key] = option_class
        else:
            for entry in games:
                if isinstance(entry, str):
                    _targeted_options.setdefault(entry, {})[option_key] = option_class
                elif isinstance(entry, type):
                    name: Any = getattr(entry, "game", None)
                    if not isinstance(name, str):
                        raise TypeError(
                            f"World class {entry.__name__} has no string 'game' attribute; "
                            "pass a game name instead.")
                    _targeted_options.setdefault(name, {})[option_key] = option_class
                else:
                    raise TypeError(
                        "Game reference must be a game name or world class, "
                        f"got {type(entry).__name__}")
        if group_name not in _group_names:
            _group_names[group_name] = ([], start_collapsed)
        if option_class not in _group_names[group_name][0]:
            _group_names[group_name][0].append(option_class)

    _patch_autoworld_register()
    _patch_webworld_register()
    _sync_webworld_groups()
    # Keep the legacy overflow path available for already-compiled dataclasses
    # whose re-run failed; harmless otherwise (flag-guarded, runs once).
    try:
        _patch_multiworld_set_options()
    except Exception:
        pass
    on_worlds_loaded(_install_set_options_wrapper)

    if games is None:
        try:
            from worlds.AutoWorld import AutoWorldRegister
            loaded: list[Any] = list(AutoWorldRegister.world_types.values())
        except Exception:
            loaded = []
        with _registry_lock:
            for world_type in loaded:
                try:
                    game_name: Any = getattr(world_type, "game", None)
                    if isinstance(game_name, str):
                        _apply_to_world(game_name, world_type)
                except Exception:
                    continue
        dprint("inject", f"registered global option '{option_key}'")
        return

    names: list[str] = []
    for entry in games:
        name, world_type = _resolve_target(entry)
        names.append(name)
        if world_type is not None:
            # Covers both given classes (access exists) and loaded names.
            with _registry_lock:
                _apply_to_world(name, world_type)
        else:
            dprint("inject", f"option '{option_key}': {name} not loaded yet; queued")

            def _deferred(found: Any | None, _game: str = name, _key: str = option_key) -> None:
                if found is None:
                    dprint("inject", f"option '{_key}': {_game} never loaded; skipped")
                    return
                with _registry_lock:
                    _apply_to_world(_game, found)

            when_game_available(name, _deferred)
    try:
        from worlds.AutoWorld import AutoWorldRegister as _Reg
        for name in names:
            world_type = _Reg.world_types.get(name)
            if world_type is not None:
                _sync_web_groups_for_world(name, world_type)
    except Exception:
        pass
    dprint("inject", f"registered option '{option_key}' for {', '.join(names)}")


def inject_world_behavior(
    game: GameRef,
    method_name: str,
    *,
    before: HookBefore | None = None,
    after: HookAfter | None = None,
    wrapper: HookWrapper | None = None,
    min_version: str | tuple[int, int, int] | None = None,
    max_version: str | tuple[int, int, int] | None = None,
) -> None:
    """Queue a version-gated class-level behavior patch for ``game``.

    ``game`` may be a game-name string (patch fires via
    :func:`when_game_available`, so import order can never prevent it) or a
    world class directly when the caller already has access to it (patched
    immediately, no waiting). Out-of-range versions log a warning but still
    apply.
    """
    from .world_hooks import patch_world_class_method

    def _apply(name: str, world_type: "type[World] | None") -> None:
        if world_type is None:
            dprint("inject", f"behavior {name}.{method_name}: game never loaded; skipped")
            return
        try:
            from .game_versions import check_world_version, get_world_version
            version: Any = get_world_version(name)
            in_range: bool = check_world_version(name, min_version, max_version)
        except Exception:
            version, in_range = "unknown", True
        dprint("inject", f"{name} version detected: {version}")
        if not in_range:
            logger.warning("[APAPI:inject] Untested %s version %s for %s; attempting patch anyway.",
                           name, version, method_name)
        unhook: Any = patch_world_class_method(
            world_type, method_name, before=before, after=after, wrapper=wrapper)
        if unhook is None:
            dprint("inject", f"FAILED to patch {name}.{method_name}")

    name, world_type = _resolve_target(game)
    if world_type is not None and not isinstance(game, str):
        # Direct class access: patch now, no waiting involved.
        _apply(name, world_type)
        dprint("inject", f"behavior {name}.{method_name} applied directly")
        return
    # Name strings always go through the queue (immediate when loaded).
    when_game_available(name, lambda found: _apply(name, found))
    dprint("inject", f"behavior {name}.{method_name} queued")


def list_injected_options() -> dict[str, list[str]]:
    """Return ``{game: [keys]}`` of targeted injections plus ``{'*': [...]}`` globals."""
    with _registry_lock:
        result: dict[str, list[str]] = {"*": sorted(_global_options)}
        for game, options in _targeted_options.items():
            result[game] = sorted(options)
        return result


__all__ = ["GameRef", "inject_option", "inject_world_behavior", "list_injected_options"]
