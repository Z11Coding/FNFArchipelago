from __future__ import annotations

"""Logic analysis helpers for sphere and blockade queries."""

from collections import Counter
from copy import deepcopy
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from BaseClasses import CollectionState, MultiWorld


def _clone_state(multiworld: "MultiWorld") -> "CollectionState":
    """Input: multiworld. Returns: cloned CollectionState."""
    state = multiworld.get_all_state()
    try:
        return state.copy()
    except Exception:
        return deepcopy(state)


def sphere_summary_with_inventory(
    multiworld: "MultiWorld",
    player: int,
    extra_items: dict[str, int] | None = None,
    max_spheres: int = 25,
) -> list[dict[str, Any]]:
    """Input: multiworld, player, extra_items, max_spheres. Returns: sphere list."""
    from BaseClasses import ItemClassification

    state = _clone_state(multiworld)
    world = multiworld.worlds[player]
    extra_items = extra_items or {}
    for name, count in extra_items.items():
        for _ in range(count):
            try:
                item = world.create_item(name)
            except Exception:
                break
            item.player = player
            state.collect(item, prevent_sweep=True)
    try:
        state.sweep_for_events()
    except Exception:
        pass

    spheres: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index in range(max_spheres):
        reachable = [
            loc.name
            for loc in multiworld.get_locations()
            if loc.player == player and loc.can_access(state)
        ]
        newly = [name for name in reachable if name not in seen]
        spheres.append(
            {"sphere": index, "reachable_locations": sorted(reachable), "newly_reachable": sorted(newly)}
        )
        seen.update(newly)
        if not newly:
            break
        progressed = False
        for loc in list(multiworld.get_locations()):
            if loc.player == player and loc.name in newly and loc.item:
                if loc.item.classification & (
                    ItemClassification.progression | ItemClassification.progression_skip_balancing
                ):
                    owned = loc.item
                    state.collect(owned, prevent_sweep=True)
                    progressed = True
        try:
            state.sweep_for_events()
        except Exception:
            pass
        if not progressed:
            break
    return spheres


def first_blockades(
    multiworld: "MultiWorld", player: int, limit: int = 10
) -> list[dict[str, Any]]:
    """Input: multiworld, player, limit. Returns: blocked locations."""
    state = _clone_state(multiworld)
    blocked = []
    for loc in multiworld.get_locations():
        if loc.player != player:
            continue
        try:
            if not loc.can_access(state):
                blocked.append({"location": loc.name, "region": loc.parent_region.name if loc.parent_region else None})
        except Exception:
            continue
        if len(blocked) >= limit:
            break
    return blocked


__all__ = ["first_blockades", "sphere_summary_with_inventory"]
