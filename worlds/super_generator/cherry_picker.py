"""Cherry-pick greedy fill algorithm for super-generator"""

import logging
import random
from typing import List, Dict, Set, Optional
from BaseClasses import Item, Location, MultiWorld, CollectionState, ItemClassification
from Fill import fill_restrictive, FillError, sweep_from_pool
from .collection_analyzer import LocationRequirementAnalyzer


def cherry_pick_fill(multiworld: MultiWorld,
                    locations: List[Location],
                    item_pool: List[Item],
                    logging_level: str = "informative") -> None:
    """
    Attempt to fill the multiworld using a cherry-pick algorithm that:
    1. Places items in accessible locations
    2. When stuck, tries to replace fillers to unlock new locations
    
    :param multiworld: The multiworld to fill
    :param locations: Locations to fill (will be mutated)
    :param item_pool: Items to place (will be mutated)
    :param logging_level: How verbose the logging should be
    :raises FillError: If unable to find valid placement
    """
    logger = logging.getLogger()

    if logging_level in ("informative", "detailed"):
        logger.info("[Super-Generator] Starting cherry-pick recovery...")

    analyzer = LocationRequirementAnalyzer(multiworld)

    # Initialize state
    state = multiworld.state.copy()
    placements: Dict[Location, Item] = {}
    filled_locations: Set[Location] = set()
    remaining_items = item_pool.copy()
    remaining_locations = set(locations)

    attempt_count = 0
    max_iterations = len(locations) * 3  # Safety limit

    print(f"[Super-Generator] Initial items: {len(remaining_items)}, locations: {len(remaining_locations)}")

    while remaining_items and remaining_locations and attempt_count < max_iterations:
        attempt_count += 1

        # Get currently accessible locations
        accessible_locs = [loc for loc in remaining_locations 
                          if loc.access_rule is None or loc.access_rule(state)]

        if logging_level == "detailed":
            logger.info(f"[Super-Generator] Iteration {attempt_count}: "
                       f"{len(accessible_locs)} accessible, "
                       f"{len(remaining_items)} items, "
                       f"{len(remaining_locations)} locations left")

        if not accessible_locs:
            # Stuck with no accessible locations
            # Try to unlock new location by replacing a filler
            if not _try_unlock_next_location(multiworld, remaining_items, placements, 
                                             remaining_locations, state, analyzer, logging_level):
                raise FillError("[Super-Generator] Cherry-pick failed: Cannot unlock any new locations",
                               multiworld=multiworld)
            continue

        # Place items in accessible locations
        items_to_place = remaining_items.copy()
        for item in items_to_place:
            if not accessible_locs:
                break

            # Choose best location for this item
            location = _pick_best_location_for_item(item, accessible_locs, state, analyzer, 
                                                     multiworld.random, logging_level)

            # Place the item
            placements[location] = item
            filled_locations.add(location)
            remaining_items.remove(item)
            remaining_locations.discard(location)
            accessible_locs.remove(location)

            # Update state
            state.collect(item, True)

            if logging_level == "detailed":
                logger.info(f"[Super-Generator] Placed {item.name} at {location.name}")

    if remaining_items or remaining_locations:
        raise FillError(f"[Super-Generator] Cherry-pick failed: {len(remaining_items)} items and "
                       f"{len(remaining_locations)} locations remaining",
                       multiworld=multiworld)

    # Verify final state
    if not multiworld.can_beat_game(state):
        raise FillError("[Super-Generator] Cherry-pick failed: Game appears unbeatable",
                       multiworld=multiworld)

    # Apply placements to the actual multiworld
    locations[:] = []
    item_pool[:] = []

    for location, item in placements.items():
        location.item = item
        item.location = location

    if logging_level in ("informative", "detailed"):
        logger.info(f"[Super-Generator] Cherry-pick recovery succeeded with {len(placements)} placements")


def _try_unlock_next_location(multiworld: MultiWorld,
                             remaining_items: List[Item],
                             placements: Dict[Location, Item],
                             remaining_locations: Set[Location],
                             state: CollectionState,
                             analyzer: LocationRequirementAnalyzer,
                             logging_level: str) -> bool:
    """
    Attempt to unlock a new location by replacing a filler item with a needed item.
    Returns True if succeeded in unlocking at least one location.
    """
    logger = logging.getLogger()

    # Find inaccessible locations that need fewest items
    inaccessible = [loc for loc in remaining_locations 
                   if loc.access_rule is not None and not loc.access_rule(state)]

    if not inaccessible:
        return False

    # Sort by fewest items needed to access
    inaccessible_sorted = sorted(
        inaccessible,
        key=lambda loc: len(analyzer.find_items_that_unlock(loc, state))
    )

    # Try to unlock by replacing fillers
    for location in inaccessible_sorted:
        needed_items = analyzer.find_items_that_unlock(location, state)

        for needed_name in needed_items.keys():
            # Find a filler item in placements to replace
            for placed_loc, placed_item in list(placements.items()):
                if placed_item.classification == ItemClassification.filler:
                    # Try replacing this filler with the needed item
                    # Find the needed item in remaining pool
                    for idx, item in enumerate(remaining_items):
                        if item.name == needed_name and item.player == location.player:
                            # Swap!
                            placements[placed_loc] = item
                            remaining_items[idx] = placed_item
                            state.collect(item, True)

                            if logging_level == "detailed":
                                logger.info(f"[Super-Generator] Replaced filler at {placed_loc.name} "
                                           f"with {item.name} to unlock {location.name}")

                            return True

    return False

def _pick_best_location_for_item(item: Item,
                                accessible_locs: List[Location],
                                state: CollectionState,
                                analyzer: LocationRequirementAnalyzer,
                                random_obj,
                                logging_level: str) -> Location:
    """
    Choose the best location to place an item among accessible locations.
    Considers item type and future location needs.
    """
    if not accessible_locs:
        raise FillError("[Super-Generator] No accessible locations available")

    # Prioritize progression items to progression locations
    if item.classification == ItemClassification.progression:
        progression_locs = [loc for loc in accessible_locs 
                           if not loc.item or loc.item.classification == ItemClassification.progression]
        if progression_locs:
            return random_obj.choice(progression_locs)

    # Otherwise, random among accessible
    return random_obj.choice(accessible_locs)
