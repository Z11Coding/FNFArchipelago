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


@dataclass
class ExpansionSpec:
    """Input: game, name, options. Output: spec for new player."""

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
        type_hints: dict[str, Any] = getattr(world_type.options_dataclass, "type_hints", {})
        kwargs: dict[str, Any] = {}
        for key, option_class in type_hints.items():
            if key in spec.options and spec.options[key] is not None:
                kwargs[key] = spec.options[key]
            else:
                kwargs[key] = _default_option_value(option_class)
        world: "World" = world_type(multiworld, player)
        world.options = world_type.options_dataclass(**kwargs)
        multiworld.worlds[player] = world
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


__all__ = ["ExpansionSpec", "LiveInjectError", "inject_player_now"]
