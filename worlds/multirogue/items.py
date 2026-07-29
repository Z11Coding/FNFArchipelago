"""
MultiRogue World Items

Defines the item types used in the MultiRogue world and stages.
"""

from typing import Dict
from BaseClasses import Item, ItemClassification

# Base ID for MultiRogue items (must not conflict with other worlds)
BASE_ITEM_ID = 1_000_000

# Item ID assignments
ITEM_IDS = {
    "Stage Clear": BASE_ITEM_ID + 1,
    "Meta-Check": BASE_ITEM_ID + 2,
    "Stage Reward": BASE_ITEM_ID + 3,
    "Coins": BASE_ITEM_ID + 4,
}


class MultiRogueItem(Item):
    """Base item type for MultiRogue world."""
    game: str = "MultiRogue"


# Item definitions
ITEMS = {
    # Stage progression items
    "Stage Clear": {"id": ITEM_IDS["Stage Clear"], "classification": ItemClassification.progression, "quantity": 50},
    
    # Meta-check items (collected from within stages, grant main world locations)
    "Meta-Check": {"id": ITEM_IDS["Meta-Check"], "classification": ItemClassification.progression, "quantity": 100},
    
    # Bridge items (rewards for completing stages, sent to main world)
    "Stage Reward": {"id": ITEM_IDS["Stage Reward"], "classification": ItemClassification.useful, "quantity": 50},
    
    # Filler
    "Coins": {"id": ITEM_IDS["Coins"], "classification": ItemClassification.filler, "quantity": 100},
}


def get_item_pool(multiworld, player: int, num_stages: int) -> Dict[str, int]:
    """
    Calculate the item pool for the given configuration.
    
    Args:
        multiworld: The MultiWorld object
        player: Player ID
        num_stages: Number of stages to generate
    
    Returns:
        Dictionary of {item_name: quantity}
    """
    pool = {}
    
    # Add stage clear items (one per stage)
    pool["Stage Clear"] = num_stages
    
    # Add stage rewards (one per stage)
    pool["Stage Reward"] = num_stages
    
    # Add filler to reach total location count (will be adjusted during fill)
    pool["Coins"] = num_stages * 2  # Starting estimate
    
    return pool


def get_item_by_name(item_name: str) -> Dict:
    """Get item definition by name."""
    return ITEMS.get(item_name, {})


def create_item_name_to_id_map() -> Dict[str, int]:
    """Create name to ID mapping for all items."""
    return {name: data["id"] for name, data in ITEMS.items()}
