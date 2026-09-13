from __future__ import annotations

"""Add players to a live MultiWorld mid-generation (generate_early window).

Nothing here is immutable: cached results live in instance dicts and every
per-player structure is a plain dict that can be extended. Safe because of
*when* it runs: during generate_early, later stages evaluate player_ids
fresh so newcomers flow through, and the newcomer gets explicit catch-up
(stage_assert_generate + generate_early) for the current stage.

TODO: relax strictness when feasible — support item-link groups (their ids
already occupy the space above the player range, so adding a player now
collides), and define catch-up for later stages (start-inventory/plando
processing in Main.main cannot simply re-run today).

Refuses loudly (LiveInjectError) outside generate_early or with groups.
"""

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
    """One synthetic slot: game, name, and rolled option values for it."""

    game: str
    name: str
    options: dict[str, "Option[Any]"] = field(default_factory=dict)


class LiveInjectError(Exception):
    """Raised when a live player injection cannot proceed safely."""


def _invalidate_caches(multiworld: "MultiWorld") -> None:
    """Drop derived player caches so they recompute with the new roster."""
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
    # cache_self1 also memoizes on first miss differently; belt and suspenders:
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
    """Extend every per-player structure sized at construction."""
    try:
        from NetUtils import SlotType
        player_type: Any = SlotType.player
    except Exception:
        existing: Any = getattr(multiworld, "player_types", {})
        player_type = next(iter(existing.values()), None)
    multiworld.player_types[player] = player_type
    multiworld.game[player] = ""  # replaced by caller with the real game next
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
    """Mirror RegionManager.add_group's cache extension for a real player."""
    manager: Any = multiworld.regions
    for cache_name in ("region_cache", "location_cache", "entrance_cache"):
        cache: Any = getattr(manager, cache_name, None)
        if isinstance(cache, dict):
            cache[player] = {}
    dprint("midgen", f"extended region caches for player {player}")


def _repair_state(multiworld: "MultiWorld", player: int) -> None:
    """Give CollectionState its per-player structures (+ re-run mixin inits)."""
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
    try:
        return option_class.from_any(option_class.default)
    except Exception as exc:
        raise LiveInjectError(
            f"Cannot default option {getattr(option_class, '__name__', option_class)}: {exc}") from exc


def inject_player_now(multiworld: "MultiWorld", spec: ExpansionSpec) -> int:
    """Add one player to a live MultiWorld. Returns the new player id.

    Only during ``generate_early`` (see module docstring for the full
    protocol). Raises :class:`LiveInjectError` otherwise.
    """
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
            # Lazily defaulted: from_any(default) may consume RNG, so only
            # call it for keys the spec does not provide.
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

    # State repair comes AFTER instantiation: mixin re-runs may read the new
    # world's options (e.g. SoH hearts), and get_game_players already sees it.
    _extend_region_caches(multiworld, player)
    _repair_state(multiworld, player)

    # Catch up the current stage for the newcomer only (the running call_all
    # already materialized its player tuple; later stages evaluate fresh).
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
