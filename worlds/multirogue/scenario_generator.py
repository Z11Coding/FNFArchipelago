"""
Scenario Generator for MultiRogue World

Generates partial-play save states (scenarios) for stages.
Scenarios represent mid-game states following sphere progression logic.
"""

import logging
from typing import List, Optional
from BaseClasses import MultiWorld, CollectionState

logger = logging.getLogger("MultiRogue")


class ScenarioMetadata:
    """Metadata about a generated scenario."""
    
    def __init__(self, stage_num: int, scenario_num: int):
        self.stage_num = stage_num
        self.scenario_num = scenario_num
        self.sphere = 0  # Which sphere this scenario is at
        self.completion_percentage = 0.0
        self.items_collected = 0
        self.locations_checked = 0


def calculate_spheres(multiworld: MultiWorld, player: int) -> List[set]:
    """
    Calculate reachability spheres for a player.
    
    Sphere 0: Locations reachable from start
    Sphere 1: Locations reachable after collecting sphere 0 items
    Etc.
    
    Args:
        multiworld: Generated MultiWorld
        player: Player ID
    
    Returns:
        List of sets, each containing location names in that sphere
    """
    spheres = []
    state = CollectionState(multiworld)
    
    locations = set(multiworld.get_locations(player))
    checked = set()
    
    while True:
        # Get all reachable unchecked locations
        reachable = multiworld.get_reachable_locations(state, player)
        current_sphere = {loc for loc in reachable if loc not in checked}
        
        if not current_sphere:
            break
        
        spheres.append(current_sphere)
        checked.update(current_sphere)
        
        # Collect items from sphere to unlock next sphere
        for loc in current_sphere:
            if loc.item:
                state.collect(loc.item, location=loc)
    
    logger.debug(f"Calculated {len(spheres)} spheres for player {player}")
    return spheres


def generate_scenario_for_stage(multiworld: MultiWorld, stage_num: int,
                               scenario_num: int, target_sphere: Optional[int] = None) -> Optional[ScenarioMetadata]:
    """
    Generate a scenario save state for a stage.
    
    Args:
        multiworld: Generated mini-multiworld
        stage_num: Stage number
        scenario_num: Scenario index within this stage
        target_sphere: Which sphere to generate at (None = random mid-game sphere)
    
    Returns:
        ScenarioMetadata on success, None on failure
    """
    if multiworld.players != 1:
        logger.warning(f"Scenario generation only supported for single-player stages")
        return None
    
    player = 1
    
    try:
        # Calculate spheres
        spheres = calculate_spheres(multiworld, player)
        
        if not spheres or len(spheres) < 2:
            logger.debug(f"Stage {stage_num}: Not enough spheres for scenario ({len(spheres)})")
            return None
        
        # Select target sphere (prefer mid-game)
        if target_sphere is None:
            # Pick a sphere in the middle (not start, not end)
            min_sphere = 1
            max_sphere = max(1, len(spheres) - 2)
            if min_sphere > max_sphere:
                logger.debug(f"Stage {stage_num}: Not enough spheres for meaningful scenario")
                return None
            target_sphere = min_sphere + (hash(f"{stage_num}_{scenario_num}") % (max_sphere - min_sphere + 1))
        
        if target_sphere >= len(spheres):
            logger.warning(f"Target sphere {target_sphere} >= {len(spheres)} available")
            return None
        
        # Collect items up to target sphere
        state = CollectionState(multiworld)
        items_collected = 0
        
        for sphere_idx in range(target_sphere + 1):
            for loc in spheres[sphere_idx]:
                if loc.item:
                    state.collect(loc.item, location=loc)
                    items_collected += 1
        
        # Create metadata
        metadata = ScenarioMetadata(stage_num, scenario_num)
        metadata.sphere = target_sphere
        metadata.items_collected = items_collected
        metadata.locations_checked = sum(len(spheres[i]) for i in range(target_sphere + 1))
        
        # Calculate completion percentage
        total_locations = len(list(multiworld.get_locations(player)))
        if total_locations > 0:
            metadata.completion_percentage = (metadata.locations_checked / total_locations) * 100
        
        logger.info(f"Generated scenario for stage {stage_num}: sphere {target_sphere}, "
                   f"{metadata.locations_checked} locations, {metadata.completion_percentage:.1f}% complete")
        
        return metadata
    
    except Exception as e:
        logger.error(f"Failed to generate scenario for stage {stage_num}: {e}")
        return None


def generate_scenarios_for_stage(multiworld: MultiWorld, stage_num: int,
                                scenario_count: int = 2) -> List[ScenarioMetadata]:
    """
    Generate multiple scenario save states for a stage.
    
    Args:
        multiworld: Generated mini-multiworld
        stage_num: Stage number
        scenario_count: How many scenarios to generate
    
    Returns:
        List of ScenarioMetadata
    """
    scenarios = []
    
    for scenario_num in range(scenario_count):
        metadata = generate_scenario_for_stage(multiworld, stage_num, scenario_num)
        if metadata is not None:
            scenarios.append(metadata)
    
    logger.info(f"Generated {len(scenarios)}/{scenario_count} scenarios for stage {stage_num}")
    return scenarios
