"""
MultiRogue World for Archipelago

A roguelike/roguelite world implementation that generates multiple mini-multiworlds
as "stages" with increasing difficulty. Players must complete these stages to progress,
with optional meta-checks providing item bridges to the main world.
"""

import logging
from typing import Dict, List, Optional

from BaseClasses import MultiWorld, Region
from worlds.AutoWorld import World, WebWorld
from .options import MultiRogueOptions
from .items import MultiRogueItem, get_item_pool, create_item_name_to_id_map
from .locations import (
    MultiRogueLocation,
    create_stage_locations,
    create_meta_check_locations,
    create_location_name_to_id_map,
    BASE_ID,
)
from .cache_manager import get_cache_manager
from .stage_generator import generate_all_stages
from .output_packer import MultiRogueOutput, write_output_file

logger = logging.getLogger("MultiRogue")


class MultiRogueWeb(WebWorld):
    """WebHost integration for MultiRogue."""
    
    theme = "grass"
    tutorials = []
    bug_report_page = "https://github.com/ArchipelagoMW/Archipelago/issues"


class MultiRogueWorld(World):
    """
    MultiRogue World - A roguelike/roguelite Archipelago world.
    
    Generates multiple mini-multiworlds (stages) with increasing difficulty.
    Each stage is independently playable and completable for progression.
    """
    
    game = "MultiRogue"
    web = MultiRogueWeb()
    options_dataclass = MultiRogueOptions
    
    item_name_to_id = create_item_name_to_id_map()
    location_name_to_id: Dict[str, int] = {}
    
    topology_present = False
    
    def __init__(self, multiworld: MultiWorld, player: int):
        super().__init__(multiworld, player)
        self.stages_generated = False
        self.stage_data_list: List[object] = []
        self.stage_metadata: Dict[str, object] = {}
        self.meta_checks_per_stage: Dict[int, List[str]] = {}
    
    def generate_early(self) -> None:
        """
        Read options and initialize cache.
        
        Ensures game complexity cache is populated for all games that might be used.
        """
        logger.info(f"MultiRogue: Starting generation with {self.options.num_stages.value} stages")
        
        # Initialize cache manager
        cache_manager = get_cache_manager()
        logger.debug("Cache manager initialized")
        
        # Log configuration
        logger.info(f"  Difficulty curve: {self.options.difficulty_curve.current_key}")
        logger.info(f"  Goal stages: {self.options.goal_completion_count.value}")
        logger.info(f"  Max retries: {self.options.max_retries.value}")
        
        if self.options.game_whitelist.value:
            logger.info(f"  Game whitelist: {self.options.game_whitelist.value}")
        if self.options.game_blacklist.value:
            logger.info(f"  Game blacklist: {self.options.game_blacklist.value}")
    
    def create_regions(self) -> None:
        """
        Create the main region for the MultiRogue world.
        
        Contains locations for each stage completion and meta-checks.
        """
        logger.info("Creating regions for MultiRogue")
        
        # Create main region
        menu_region = Region("Menu", self.player, self.multiworld)
        stage_locations = create_stage_locations(self.options.num_stages.value, BASE_ID)
        
        for loc in stage_locations:
            loc.parent_region = menu_region
            menu_region.locations.append(loc)
        
        self.multiworld.regions.append(menu_region)
        
        # Update location_name_to_id mapping with stage locations
        self.location_name_to_id.update(
            create_location_name_to_id_map(
                self.options.num_stages.value,
                self.meta_checks_per_stage,
                BASE_ID,
            )
        )
    
    def create_items(self) -> None:
        """
        Create the item pool for the main world.
        
        Items include:
        - "Stage Clear" items (one per stage)
        - "Stage Reward" items (bonus items for clearing stages)
        - "Meta-Check" items (from stage meta-checks)
        - Filler items
        """
        logger.info("Creating items for MultiRogue")
        
        num_stages = self.options.num_stages.value
        pool_dict = get_item_pool(self.multiworld, self.player, num_stages)
        
        for item_name, quantity in pool_dict.items():
            item_id = self.item_name_to_id[item_name]
            for _ in range(quantity):
                item = MultiRogueItem(item_name, item_id, self.player)
                self.multiworld.itempool.append(item)
        
        logger.info(f"Created {len(self.multiworld.itempool)} items")
    
    def set_rules(self) -> None:
        """
        Set access rules for locations.
        
        For now, all stage locations are accessible immediately
        (no gating logic). Gating can be added later via progression_gating option.
        """
        logger.info("Setting rules for MultiRogue")
        # TODO: Implement progression gating if needed
    
    def generate_basic(self) -> None:
        """
        Generate all mini-multiworlds (stages).
        
        This is where the core generation logic happens:
        - Determine available games
        - Generate each stage with appropriate difficulty
        - Collect stage data for output packing
        """
        logger.info("Generating stages for MultiRogue")
        
        # Generate all stages
        stages, success = generate_all_stages(self.multiworld, self.options)
        
        if not success:
            raise Exception("Failed to generate all stages for MultiRogue world")
        
        self.stage_data_list = stages
        self.stages_generated = True
        
        logger.info(f"Successfully generated {len(stages)} stages")
    
    def generate_output(self, output_directory: str) -> None:
        """
        Generate the final output file (.apmrmw).
        
        Packs all stage data, metadata, and the main multiworld data
        into a single compressed file.
        """
        logger.info("Generating output for MultiRogue")
        
        if not self.stages_generated:
            logger.error("Stages were not generated before output!")
            return
        
        # Create output structure
        output = MultiRogueOutput(self.multiworld.seed, "0.5.0")  # TODO: Get AP version
        output.num_stages = len(self.stage_data_list)
        output.difficulty_curve = self.options.difficulty_curve.current_key
        output.goal_info = {
            "goal_stages": self.options.goal_completion_count.value,
            "is_multiplayer": self.multiworld.players > 1,
            "main_world_player": self.player,
        }
        output.stage_list = self.stage_data_list
        output.stage_metadata = self.stage_metadata
        
        # TODO: Serialize main multidata and spoiler
        
        # Write to file
        from pathlib import Path
        output_path = Path(output_directory)
        write_output_file(output, output_path)
        
        logger.info("Output file created successfully")
    
    def fill_slot_data(self) -> Dict:
        """
        Provide slot data to the client.
        
        This data is sent to the client and can be used for
        game-specific information.
        """
        return {
            "num_stages": self.options.num_stages.value,
            "goal_stages": self.options.goal_completion_count.value,
        }
