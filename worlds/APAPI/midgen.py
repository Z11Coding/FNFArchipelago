from __future__ import annotations

"""Live player injection during generate_early."""

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from .debug import dprint
from .generation import get_current_stage

if TYPE_CHECKING:
    from BaseClasses import CollectionState, MultiWorld
    from Options import Option
    from worlds.AutoWorld import World

logger = logging.getLogger("APAPI.Midgen")

_midgen_hooks: dict[str, list[dict[str, Any]]] = {}


def hook_midgen_instance(
    world: "World",
    method_name: str,
    *,
    before: Any | None = None,
    after: Any | None = None,
    wrapper: Any | None = None,
) -> Any:
    """Hook a midgen world instance like world_hooks. Returns unhook."""
    from .world_hooks import hook_world_method

    return hook_world_method(world, method_name, before=before, after=after, wrapper=wrapper)


def register_midgen_hook(
    game: str,
    method_name: str,
    *,
    before: Any | None = None,
    after: Any | None = None,
    wrapper: Any | None = None,
    as_static: bool = False,
) -> None:
    """Register a hook for future midgen-injected worlds of game. Applied on inject."""
    _midgen_hooks.setdefault(game, []).append(
        {"method": method_name, "before": before, "after": after, "wrapper": wrapper, "as_static": as_static}
    )
    dprint("midgen", f"registered midgen hook {game}.{method_name} static={as_static}")


def _apply_midgen_hooks(world: "World") -> None:
    """Apply registered midgen hooks to a newly injected world."""
    game = getattr(world, "game", None)
    if not isinstance(game, str):
        return
    for hook in list(_midgen_hooks.get(game, [])):
        method = hook["method"]
        before = hook["before"]
        after = hook["after"]
        wrapper = hook["wrapper"]
        as_static = hook.get("as_static", False)
        try:
            if as_static:
                # Install as staticmethod on the instance's class
                orig = getattr(world, method, None)
                if callable(orig):
                    base = getattr(orig, "__apapi_unwrapped__", orig)
                    # Create wrapper that doesn't pass self
                    @__import__("functools").wraps(base)
                    def static_patched(*args: Any, **kwargs: Any) -> Any:
                        return base(*args, **kwargs)

                    static_patched.__apapi_unwrapped__ = base  # type: ignore[attr-defined]
                    setattr(world, method, staticmethod(static_patched))
                    # Also update class for consistency if needed
                    try:
                        setattr(type(world), method, staticmethod(static_patched))
                    except Exception:
                        pass
                    dprint("midgen", f"applied static midgen hook {game}.{method}")
                else:
                    # If no original, just set static
                    if wrapper is not None:
                        setattr(world, method, staticmethod(wrapper))
                    elif before is not None:
                        setattr(world, method, staticmethod(before))
            else:
                hook_midgen_instance(world, method, before=before, after=after, wrapper=wrapper)
                dprint("midgen", f"applied midgen hook {game}.{method}")
        except Exception as exc:
            logger.warning("APAPI midgen hook failed for %s.%s: %s", game, method, exc)


@dataclass
class ExpansionSpec:
    """Spec for a new player to inject. Holds game, name and options."""

    game: str
    name: str
    options: dict[str, "Option[Any]"] = field(default_factory=dict)


class LiveInjectError(Exception):
    """Raised when live injection cannot proceed."""


def _invalidate_caches(multiworld: "MultiWorld") -> None:
    """Input: multiworld. Returns: None (clears caches)."""
    removed: list[str] = []
    try:
        instance_dict: Any = vars(multiworld)
    except Exception:
        instance_dict = {}
    for key in ("player_ids", "__cache_get_game_players__", "__cache_get_game_groups__",
                "__cache_get_game_worlds__"):
        try:
            if key in instance_dict:
                del instance_dict[key]
                removed.append(key)
        except Exception:
            continue
    for key in list(instance_dict):
        if key.startswith("__cache_") and key.endswith("__"):
            try:
                del instance_dict[key]
                if key not in removed:
                    removed.append(key)
            except Exception:
                continue
    dprint("midgen", f"invalidated caches: {removed or 'none present'}")


def _extend_dicts(multiworld: "MultiWorld", player: int, name: str) -> None:
    """Input: multiworld, player, name. Returns: None (extends per-player dicts)."""
    try:
        from NetUtils import SlotType
        player_type: Any = SlotType.player
    except Exception:
        existing: Any = getattr(multiworld, "player_types", {})
        player_type = next(iter(existing.values()), None)
    multiworld.player_types[player] = player_type
    multiworld.game[player] = ""
    multiworld.player_name[player] = name
    default_completion: Any = lambda state: True
    multiworld.completion_condition[player] = default_completion
    multiworld.precollected_items[player] = []
    multiworld.early_items[player] = {}
    multiworld.local_early_items[player] = {}
    multiworld.plando_item_blocks[player] = []
    sprite: Any = getattr(multiworld, "sprite", None)
    if isinstance(sprite, dict):
        sprite[player] = None
    dprint("midgen", f"extended per-player dicts for player {player}")


def _extend_region_caches(multiworld: "MultiWorld", player: int) -> None:
    """Input: multiworld, player. Returns: None (extends region caches)."""
    manager: Any = multiworld.regions
    for cache_name in ("region_cache", "location_cache", "entrance_cache"):
        cache: Any = getattr(manager, cache_name, None)
        if isinstance(cache, dict):
            cache[player] = {}
    dprint("midgen", f"extended region caches for player {player}")


def _repair_state(multiworld: "MultiWorld", player: int) -> None:
    """Input: multiworld, player. Returns: None (repairs CollectionState)."""
    state: "CollectionState | None" = getattr(multiworld, "state", None)
    if state is None:
        dprint("midgen", "no CollectionState yet; nothing to repair")
        return
    try:
        state.prog_items[player] = Counter()
        state.reachable_regions[player] = set()
        state.blocked_connections[player] = set()
        state.stale[player] = True
    except Exception as exc:
        raise LiveInjectError(f"Cannot repair CollectionState for player {player}: {exc}") from exc
    rerun: int = 0
    for function in list(getattr(state, "additional_init_functions", [])):
        try:
            function(state, multiworld)
            rerun += 1
        except Exception as exc:
            which: str = getattr(function, "__qualname__", repr(function))
            raise LiveInjectError(
                f"Logic-mixin re-init {which} failed for player {player}: {exc}") from exc
    dprint("midgen", f"repaired CollectionState for player {player} ({rerun} mixin re-init(s))")


def _default_option_value(option_class: "type[Option[Any]]") -> "Option[Any]":
    """Input: option class. Returns: default Option instance."""
    try:
        return option_class.from_any(option_class.default)
    except Exception as exc:
        raise LiveInjectError(
            f"Cannot default option {getattr(option_class, '__name__', option_class)}: {exc}") from exc


def _get_known_option_keys(world_type: "type[World]", game: str) -> tuple[set[str], set[str], set[str]]:
    """Return (constructible_fields, type_hint_keys, injected_keys) for game."""
    try:
        type_hints: dict[str, Any] = getattr(world_type.options_dataclass, "type_hints", {}) or {}
    except Exception:
        type_hints: dict[str, Any] = {}
    try:
        dc_fields: set[str] = set(getattr(world_type.options_dataclass, "__dataclass_fields__", {}).keys())
    except Exception:
        dc_fields = set(type_hints.keys())
    # APAPI injected options that may not yet be in dataclass fields for early worlds
    injected: set[str] = set()
    try:
        from .injection import _global_options, _targeted_options
        injected.update(_global_options.keys())
        injected.update(_targeted_options.get(game, {}).keys())
    except Exception:
        pass
    try:
        from Options import PerGameCommonOptions
        per_game_ann = getattr(PerGameCommonOptions, "__annotations__", {})
        injected.update(per_game_ann.keys())
    except Exception:
        pass
    return dc_fields, set(type_hints.keys()), injected


def inject_player_now(multiworld: "MultiWorld", spec: ExpansionSpec) -> int:
    """Input: multiworld, spec. Returns: new player id."""
    stage: str | None = get_current_stage()
    if stage != "generate_early":
        raise LiveInjectError(
            f"Live injection only runs during generate_early (current stage: {stage!r}).")
    if getattr(multiworld, "groups", {}):
        raise LiveInjectError(
            "Live injection refuses seeds with item-link groups: group ids already "
            "occupy the id space above the player range. Disable item links.")

    try:
        from worlds.AutoWorld import AutoWorldRegister
    except Exception as exc:
        raise LiveInjectError(f"World registry unavailable: {exc}") from exc
    if spec.game not in AutoWorldRegister.world_types:
        raise LiveInjectError(f"Unknown game {spec.game!r}.")
    world_type: "type[World]" = AutoWorldRegister.world_types[spec.game]

    try:
        existing: list[int] = sorted(pid for pid in multiworld.player_ids if isinstance(pid, int))
    except Exception as exc:
        raise LiveInjectError(f"Cannot read player roster: {exc}") from exc
    if not existing:
        raise LiveInjectError("No existing players to extend.")
    player: int = max(existing) + 1

    multiworld.players = max(int(getattr(multiworld, "players", player - 1)), player)
    _invalidate_caches(multiworld)
    _extend_dicts(multiworld, player, spec.name)
    multiworld.game[player] = spec.game

    try:
        type_hints: dict[str, Any] = getattr(world_type.options_dataclass, "type_hints", {}) or {}
        dc_fields, hint_keys, injected_keys = _get_known_option_keys(world_type, spec.game)
        # Union of all keys APAPI knows about for this game
        known_keys: set[str] = hint_keys | dc_fields | injected_keys
        # Warn for keys in spec that are unknown to this world
        for key in list(spec.options.keys()):
            if key not in known_keys:
                # APAPI knows what exists — warn, not error (mirrors AP's roll_settings warning)
                try:
                    from .fuzzy import format_did_you_mean, did_you_mean
                    suggestion = did_you_mean(key, sorted(known_keys))
                    hint = format_did_you_mean(suggestion) if suggestion else ""
                except Exception:
                    hint = ""
                logger.warning(
                    "[APAPI:midgen] ignoring unknown option %r for game %r (not in %s)%s — treating as warning, not error",
                    key, spec.game, world_type.__name__, hint)
                dprint("midgen", f"ignoring unknown option {key!r} for {spec.game}")
                # Do not include in kwargs; still allow other options to exist
                continue
        # Build kwargs only for constructible fields; remaining injected-but-not-field keys will be attached as plain attrs
        kwargs: dict[str, Any] = {}
        remaining_injected: dict[str, Any] = {}
        # Ensure type_hints covers all dataclass fields (handle stale cache)
        try:
            ann_all = getattr(world_type.options_dataclass, "__annotations__", {}) or {}
        except Exception:
            ann_all = {}
        # Union of fields and hints to avoid missing required args when cache is stale
        for key in set(dc_fields) | set(type_hints.keys()):
            if key in dc_fields:
                # Native field — can be passed to dataclass __init__
                option_class = type_hints.get(key) or ann_all.get(key)
                if option_class is None:
                    # No class info — skip, will be handled as plain attr if in spec
                    if key in spec.options and spec.options[key] is not None:
                        remaining_injected[key] = spec.options[key]
                    continue
                if key in spec.options and spec.options[key] is not None:
                    kwargs[key] = spec.options[key]
                else:
                    try:
                        kwargs[key] = _default_option_value(option_class)
                    except Exception:
                        # If default fails, leave missing — dataclass may have its own default
                        if key in spec.options:
                            kwargs[key] = spec.options[key]
            else:
                # type_hints key but not in fields (stale cache or injected not yet compiled) — treat as injected fallback
                if key in spec.options and spec.options[key] is not None:
                    remaining_injected[key] = spec.options[key]
        # Handle injected keys that are not in type_hints but are in spec and should be plain attrs
        for key in injected_keys:
            if key not in dc_fields and key not in kwargs and key not in remaining_injected and key in spec.options:
                remaining_injected[key] = spec.options[key]
        for key, val in spec.options.items():
            if key not in known_keys:
                continue
            if key not in dc_fields and key not in kwargs and key not in remaining_injected:
                remaining_injected[key] = val
        world: "World" = world_type(multiworld, player)
        import re as _re
        attempt_kwargs = dict(kwargs)
        for _ in range(10):
            try:
                world.options = world_type.options_dataclass(**attempt_kwargs)
                break
            except TypeError as exc:
                msg = str(exc)
                m = _re.search(r"unexpected keyword argument '([^']+)'", msg)
                if m:
                    bad_key = m.group(1)
                    if bad_key in attempt_kwargs:
                        try:
                            from .fuzzy import format_did_you_mean, did_you_mean
                            suggestion = did_you_mean(bad_key, sorted(known_keys))
                            hint = format_did_you_mean(suggestion) if suggestion else ""
                        except Exception:
                            hint = ""
                        logger.warning(
                            "[APAPI:midgen] ignoring unknown option %r for game %r (dataclass rejected)%s — warning, not error",
                            bad_key, spec.game, hint)
                        if bad_key in injected_keys:
                            remaining_injected[bad_key] = attempt_kwargs.pop(bad_key)
                        else:
                            attempt_kwargs.pop(bad_key, None)
                        continue
                raise LiveInjectError(f"Cannot instantiate {spec.game} world: {exc}") from exc
        else:
            raise LiveInjectError(f"Cannot instantiate {spec.game} world: too many bad options") from None
        # Attach remaining injected keys as plain attributes (mirrors NoLogic's fallback for early worlds)
        for key, val in remaining_injected.items():
            try:
                setattr(world.options, key, val)
                dprint("midgen", f"attached injected option {key!r} as plain attr for {spec.game} p{player}")
            except Exception as exc:
                logger.warning("[APAPI:midgen] could not attach injected option %r for %s: %s", key, spec.game, exc)
        multiworld.worlds[player] = world
        _apply_midgen_hooks(world)
    except LiveInjectError:
        raise
    except Exception as exc:
        raise LiveInjectError(f"Cannot instantiate {spec.game} world: {exc}") from exc
    dprint("midgen", f"instantiated {spec.game} as player {player} ({spec.name!r})")

    _extend_region_caches(multiworld, player)
    _repair_state(multiworld, player)

    try:
        stage_assert: Any = getattr(world_type, "stage_assert_generate", None)
        if callable(stage_assert):
            stage_assert(multiworld)
        world.generate_early()
    except Exception as exc:
        raise LiveInjectError(f"New player {player} failed generate_early catch-up: {exc}") from exc
    dprint("midgen", f"player {player} caught up through generate_early")

    try:
        final_ids: tuple[int, ...] = multiworld.player_ids
    except Exception:
        final_ids = ()
    dprint("midgen", f"roster now {len(final_ids)} player(s)")
    return player


__all__ = ["ExpansionSpec", "LiveInjectError", "inject_player_now", "hook_midgen_instance", "register_midgen_hook"]
