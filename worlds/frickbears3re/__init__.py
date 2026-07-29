"""Five Nights at Frickbear's 3 Archipelago World.

This module implements the Five Nights at Frickbear's 3 randomizer for Archipelago,
allowing players to randomize animatronic rescues, location unlocks, and item progression.
"""

from typing import Any, Mapping

from worlds.AutoWorld import World

from . import items, locations, regions, rules, web_world
from . import options as frickbears_options


class Frickbears3ReWorld(World):
    """Five Nights at Frickbear's 3 Archipelago World.
    
    A fangame where you must salvage animatronics from multiple locations across 5 nights.
    Unlock salvage locations, salvage animatronics, acquire shop upgrades, and pursue different endings.
    """
    
    game = "Five Nights at Frickbear's 3"
    display_name = "Five Nights at Frickbear's 3"
    web = web_world.WebWorld()
    
    options_dataclass = frickbears_options.Frickbears3ReOptions
    options: frickbears_options.Frickbears3ReOptions
    
    item_name_to_id = items.ITEM_NAME_TO_ID
    location_name_to_id = locations.LOCATION_NAME_TO_ID
    
    origin_region_name = "Overworld"
    
    def create_regions(self) -> None:
        """Create all regions and locations for the world."""
        regions.create_and_connect_regions(self)
        locations.create_all_locations(self)
    
    def set_rules(self) -> None:
        """Set progression rules for item placement."""
        rules.set_all_rules(self)
    
    def create_items(self) -> None:
        """Create all items for the world."""
        items.create_all_items(self)
    
    def create_item(self, name: str) -> items.Frickbears3ReItem:
        """Create an individual item by name."""
        return items.create_item_with_correct_classification(self, name)
    
    def get_filler_item_name(self) -> str:
        """Get a filler item name for infinite filler."""
        return items.get_random_filler_item_name(self)
    
    def fill_slot_data(self) -> Mapping[str, Any]:
        """Provide game-specific data to the client."""
        return self.options.as_dict(
            "death_link",
        )
