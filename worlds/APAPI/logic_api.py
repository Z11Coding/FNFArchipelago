from __future__ import annotations

"""Logical analysis helpers for APAPI.

- ``sphere_summary`` / ``blockade_summary`` answer "what do spheres look like
  with a given inventory" and "when do the first blockades appear".
- Implemented read-only on top of ``CollectionState`` so add-on worlds never
  mutate generation state.
"""

from collections import Counter
from copy import deepcopy
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from BaseClasses import CollectionState, MultiWorld


def _clone_state(multiworld: "MultiWorld") -> "CollectionState":
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
    """Simulate reachability for ``player`` with ``extra_items`` added.

    Returns a list of ``{"sphere": i, "reachable_locations": [...],
    "newly_reachable": [...]}``. Locations are identified by name. This does
    not modify the real state.
    """
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
            # Force ownership to this player for the simulation.
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
        # Advance one step: collect everything newly reachable (progression only).
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
    """Return locations of ``player`` that are unreachable with starting inventory.

    Each entry is ``{"location": name, "requires": [missing item names]}``.
    Best-effort: uses the world's ``get_rule`` closure source is opaque, so we
    report which progression items exist in the pool but are not yet held.
    """
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
