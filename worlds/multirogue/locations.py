"""
MultiRogue World Locations

Defines the location types used in the main MultiRogue world.
Each location represents a stage completion or meta-check achievement.
"""

from typing import List, Dict
from BaseClasses import Location, LocationProgressType


# Base ID allocation for MultiRogue
# Ranges:
#   1000-1999: Stage completion locations
#   2000-2999: Meta-check locations
#   3000-3999: Reserved for future use
BASE_ID = 1_000_000  # High to avoid conflicts


class MultiRogueLocation(Location):
    """Base location type for MultiRogue world."""
    game: str = "MultiRogue"


def create_stage_locations(num_stages: int, base_id: int = BASE_ID) -> List[MultiRogueLocation]:
    """
    Create stage completion locations for the main world.
    
    One location per stage: completing stage N grants the item placed here.
    
    Args:
        num_stages: Number of stages
        base_id: Base ID for location allocation
    
    Returns:
        List of Location objects
    """
    locations = []
    for stage_num in range(num_stages):
        loc_name = f"Clear Stage {stage_num}"
        loc_id = base_id + 1000 + stage_num
        loc = MultiRogueLocation(None, loc_name, loc_id, None)
        loc.progress_type = LocationProgressType.DEFAULT
        locations.append(loc)
    return locations


def create_meta_check_locations(meta_checks_per_stage: Dict[int, List[str]], base_id: int = BASE_ID) -> List[MultiRogueLocation]:
    """
    Create meta-check placeholder locations.
    
    These represent items found within stages that, when collected,
    unlock locations in the main world.
    
    Args:
        meta_checks_per_stage: {stage_num: [list of meta-check names]}
        base_id: Base ID for location allocation
    
    Returns:
        List of Location objects
    """
    locations = []
    for stage_num, checks in meta_checks_per_stage.items():
        for check_idx, check_name in enumerate(checks):
            loc_name = f"Stage {stage_num} Meta: {check_name}"
            loc_id = base_id + 2000 + (stage_num * 10) + check_idx
            loc = MultiRogueLocation(None, loc_name, loc_id, None)
            loc.progress_type = LocationProgressType.DEFAULT
            locations.append(loc)
    return locations


def create_location_name_to_id_map(num_stages: int, meta_checks_per_stage: Dict[int, List[str]] = None, base_id: int = BASE_ID) -> Dict[str, int]:
    """
    Create a complete name-to-ID mapping for all locations.
    
    Args:
        num_stages: Number of stages
        meta_checks_per_stage: Optional {stage_num: [check_names]} for meta-checks
        base_id: Base ID for location allocation
    
    Returns:
        Dictionary mapping location names to their IDs
    """
    mapping = {}
    
    # Add stage completion locations
    for stage_num in range(num_stages):
        loc_name = f"Clear Stage {stage_num}"
        loc_id = base_id + 1000 + stage_num
        mapping[loc_name] = loc_id
    
    # Add meta-check locations if provided
    if meta_checks_per_stage:
        for stage_num, checks in meta_checks_per_stage.items():
            for check_idx, check_name in enumerate(checks):
                loc_name = f"Stage {stage_num} Meta: {check_name}"
                loc_id = base_id + 2000 + (stage_num * 10) + check_idx
                mapping[loc_name] = loc_id
    
    return mapping
