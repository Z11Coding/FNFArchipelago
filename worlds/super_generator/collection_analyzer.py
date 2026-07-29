"""Location requirement analysis for cherry-pick algorithm"""

import logging
from typing import Dict, List, Set, Tuple, Optional
from BaseClasses import Location, CollectionState, Item, MultiWorld, ItemClassification


class LocationRequirementAnalyzer:
    """Analyzes what items are needed to access specific locations"""

    def __init__(self, multiworld: MultiWorld):
        self.multiworld = multiworld
        self.logger = logging.getLogger()
        self._requirement_cache: Dict[int, List[str]] = {}

    def analyze_location_requirements(self, location: Location, state: CollectionState) -> List[str]:
        """
        Analyze what items are needed to access a location.
        Returns list of item names required.
        """
        if not hasattr(location, 'access_rule') or location.access_rule is None:
            return []

        # Try to determine what items would make this location accessible
        # by testing against the current state
        needed_items = []
        current_items = set(state.inventory.keys())

        # Simulate adding different items and check if location becomes accessible
        for item_name in self._get_all_progressive_items(location.player):
            if item_name in current_items:
                continue

            test_state = state.copy()
            # Create a dummy item for testing
            test_item = Item(item_name, ItemClassification.progression, None, location.player)
            test_state.collect(test_item, True)

            if location.access_rule(test_state):
                needed_items.append(item_name)

        return needed_items

    def get_accessible_locations(self, state: CollectionState) -> List[Location]:
        """Get all currently accessible locations sorted by priority"""
        accessible = []
        for location in self.multiworld.get_locations():
            if not location.locked and location.access_rule and location.access_rule(state):
                accessible.append(location)
        return sorted(accessible, key=self._location_priority, reverse=True)

    def get_reachable_locations_by_priority(self, state: CollectionState) -> List[Location]:
        """Get all reachable locations sorted by accessibility priority"""
        return self.get_accessible_locations(state)

    def find_items_that_unlock(self, location: Location, state: CollectionState) -> Dict[str, int]:
        """Find which items would unlock this location and how many of each"""
        if location.access_rule is None or location.access_rule(state):
            return {}

        unlocking_items = {}
        for item_name in self._get_all_progressive_items(location.player):
            test_state = state.copy()
            test_item = Item(item_name, ItemClassification.progression, None, location.player)
            test_state.collect(test_item, True)

            if location.access_rule(test_state):
                unlocking_items[item_name] = unlocking_items.get(item_name, 0) + 1

        return unlocking_items

    def simulate_item_placement(self, item: Item, location: Location, state: CollectionState) -> bool:
        """Check if placing an item at a location is viable"""
        if item.code is None:
            return True  # Event items are always viable

        # Item should be placeable if it's an appropriate type for the location
        # and won't create immediate dead ends
        test_state = state.copy()
        test_state.collect(item, True)

        # Basic viability: item doesn't break accessibility
        # (More complex checks could be added here)
        return True

    def _location_priority(self, location: Location) -> int:
        """Return priority score for a location (higher = more important)"""
        if not location.item:
            return 0

        # Progression items are higher priority
        if location.item.classification == ItemClassification.progression:
            return 2
        elif location.item.classification == ItemClassification.useful:
            return 1
        else:  # filler/excluded
            return 0

    def _get_all_progressive_items(self, player: int) -> List[str]:
        """Get all possible item names that could be progression items"""
        items = set()
        for item in self.multiworld.itempool:
            if item.player == player:
                items.add(item.name)
        return sorted(list(items))

    def clear_cache(self):
        """Clear the requirement cache"""
        self._requirement_cache.clear()
