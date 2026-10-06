"""
MultiRogue Sub World - Meta-Check Management

This is a separate world type used within each mini-multiworld stage.
It manages meta-checks that can grant items to both:
1. The main MultiRogue world (stage completion bridging)
2. The sub-world itself (within-stage rewards)

When a client connects to a slot running MultiRogue in a main multiworld,
it also connects to a corresponding sub-world to handle stage meta-checks.

Architecture:
- Main MultiRogue world: Manages stage progression
- Sub world (one per stage): Manages meta-checks within that stage
- Meta-checks can send items to either world
"""

import logging
from typing import Dict, List

from BaseClasses import MultiWorld, Region, Location, Item
from worlds.AutoWorld import World, WebWorld

logger = logging.getLogger("MultiRogueSubWorld")


class MultiRogueSubItem(Item):
    """Item type for sub-world meta-checks."""
    game: str = "MultiRogue Sub"


class MultiRogueSubLocation(Location):
    """Location type for sub-world meta-checks."""
    game: str = "MultiRogue Sub"


class MultiRogueSubWeb(WebWorld):
    """WebHost integration for MultiRogue Sub World."""
    
    theme = "grass"
    tutorials = []
    
    # This is a sub-world and shouldn't appear in the main world list
    hidden = True


class MultiRogueSubWorld(World):
    """
    MultiRogue Sub World - Manages meta-checks within a stage.
    
    This world type is used internally by MultiRogue stages.
    It provides:
    - Meta-check locations (things to find within the stage)
    - Items that bridge to the main MultiRogue world
    - Items that reward the player within the stage
    
    Each stage gets its own instance of this world with unique
    locations and items for that stage's meta-checks.
    """
    
    game = "MultiRogue Sub"
    web = MultiRogueSubWeb()
    
    # ID ranges for sub-world
    BASE_ID = 2_000_000
    
    item_name_to_id = {}
    location_name_to_id = {}
    
    topology_present = False
    
    def __init__(self, multiworld: MultiWorld, player: int):
        super().__init__(multiworld, player)
        self.stage_num = 0
        self.meta_checks = []
        self.main_world_player = 1  # Default, should be set by stage generator
    
    def create_regions(self) -> None:
        """Create the meta-check region."""
        logger.debug(f"Creating regions for Stage {self.stage_num} sub-world")
        
        # Create region for meta-checks
        region = Region(f"Stage {self.stage_num} Checks", self.player, self.multiworld)
        
        # Add locations (these will be populated by the stage generator)
        # Locations are added here based on meta_checks list
        for idx, check_name in enumerate(self.meta_checks):
            loc_id = self.BASE_ID + (self.stage_num * 1000) + idx
            location = MultiRogueSubLocation(
                None,
                f"Stage {self.stage_num}: {check_name}",
                loc_id,
                self.player
            )
            location.parent_region = region
            region.locations.append(location)
            self.location_name_to_id[location.name] = loc_id
        
        self.multiworld.regions.append(region)
    
    def create_items(self) -> None:
        """Create items for this stage's meta-checks."""
        logger.debug(f"Creating items for Stage {self.stage_num} sub-world ({len(self.meta_checks)} checks)")
        
        # Create items for each meta-check
        # Some go back to main world, some stay in sub-world
        for idx, check_name in enumerate(self.meta_checks):
            item_id = self.BASE_ID + (self.stage_num * 1000) + idx
            
            # Determine if this is a "bridge" item (goes to main world) or local item
            # For now, all meta-checks are bridge items (grant items in main world)
            item_name = f"Stage {self.stage_num} Meta: {check_name}"
            
            item = MultiRogueSubItem(item_name, item_id, self.player)
            self.multiworld.itempool.append(item)
            
            if item_name not in self.item_name_to_id:
                self.item_name_to_id[item_name] = item_id
    
    def set_rules(self) -> None:
        """Set access rules for meta-checks."""
        # Meta-checks are typically accessible throughout the stage
        # No special gating needed (will be gated by the stage itself)
        logger.debug(f"Setting rules for Stage {self.stage_num} sub-world")
    
    def generate_basic(self) -> None:
        """No special generation needed for sub-world."""
        pass
    
    def fill_slot_data(self) -> Dict:
        """Provide slot data to the client."""
        return {
            "stage_num": self.stage_num,
            "main_world_player": self.main_world_player,
            "meta_checks": self.meta_checks,
        }


def create_sub_world_for_stage(
    stage_num: int,
    meta_checks: List[str],
    main_world_player: int
) -> MultiRogueSubWorld:
    """
    Factory function to create a configured sub-world instance for a stage.
    
    Args:
        stage_num: Which stage this sub-world is for
        meta_checks: List of meta-check names for this stage
        main_world_player: Player ID of the main MultiRogue world
    
    Returns:
        Configured MultiRogueSubWorld instance
    
    Note:
        This is typically called during MultiRogue generation to set up
        the sub-world infrastructure for each stage.
    """
    # Create a minimal multiworld for configuration
    multiworld = MultiWorld(players=1)
    sub_world = MultiRogueSubWorld(multiworld, player=1)
    
    sub_world.stage_num = stage_num
    sub_world.meta_checks = meta_checks
    sub_world.main_world_player = main_world_player
    
    logger.debug(f"Created sub-world for stage {stage_num} with {len(meta_checks)} meta-checks")
    
    return sub_world
