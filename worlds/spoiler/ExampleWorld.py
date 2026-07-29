"""
Example implementation of SpoilerDict in a world.

This demonstrates different patterns for using the spoiler protection system.
"""

from typing import Dict, Any, Mapping
from worlds import World
from worlds.spoiler import apply_spoiler_protection_to_world, SpoilerDict


class ExampleSpoilerWorld(World):
    """
    Example world showing how to use SpoilerDict for spoiler protection.
    
    This world demonstrates:
    1. Basic spoiler protection with automatic labels
    2. Custom labels for sensitive data
    3. Partial protection (only some keys)
    """
    
    game = "Example Game"
    
    def fill_slot_data(self) -> Dict[str, Any]:
        """Fill slot data with spoiler protection."""
        slot_data = {
            # Sensitive locations that should be hidden
            "secret_location_1": "magic_sword",
            "secret_location_2": "healing_potion",
            "secret_location_3": "ancient_tome",
            
            # Non-sensitive metadata
            "version": 1,
            "difficulty": "normal",
            "seed_id": self.multiworld.seed,
        }
        
        # Define spoiler-free labels for sensitive keys
        key_labels = {
            "secret_location_1": "???",
            "secret_location_2": "???_1", 
            "secret_location_3": "???_2",
        }
        
        # Apply protection
        return apply_spoiler_protection_to_world(
            slot_data,
            self,
            key_labels=key_labels
        )


class AdvancedSpoilerWorld(World):
    """
    Advanced world showing custom spoiler labels with semantic meaning.
    
    Uses labels that give hints about content without spoiling exact details.
    """
    
    game = "Advanced Game"
    
    def fill_slot_data(self) -> Dict[str, Any]:
        """Fill slot data with semantic spoiler-free labels."""
        slot_data = {
            "dungeon_1_reward": "boss_key",
            "dungeon_2_reward": "master_sword",
            "hidden_treasure": "ancient_relic",
            "npc_gift_location": "magic_ring",
            
            # Non-sensitive
            "game_version": 2,
            "patch_date": "2024-01-01",
        }
        
        # Use semantic labels that don't spoil exact content
        key_labels = {
            "dungeon_1_reward": "Dungeon Prize",
            "dungeon_2_reward": "Legendary Item",
            "hidden_treasure": "Secret",
            "npc_gift_location": "Quest Reward",
        }
        
        return apply_spoiler_protection_to_world(
            slot_data,
            self,
            key_labels=key_labels
        )


class ManualSpoilerDictWorld(World):
    """
    World that manually creates and uses SpoilerDict.
    
    This approach gives maximum control over label generation.
    """
    
    game = "Manual Game"
    
    def fill_slot_data(self) -> Dict[str, Any]:
        """Fill slot data using manual SpoilerDict creation."""
        # Create actual data
        real_data = {
            "location_a": "item_x",
            "location_b": "item_y",
            "game_state": "active",
        }
        
        # Create labels
        labels = {
            "location_a": "Place 1",
            "location_b": "Place 2",
        }
        
        # Create SpoilerDict manually
        spoiler_dict = SpoilerDict(real_data=real_data, key_labels=labels)
        
        # Can still modify it like a normal dict
        spoiler_dict["difficulty"] = "hard"
        
        # Add to a wrapper dict and protect
        return apply_spoiler_protection_to_world(
            dict(spoiler_dict),
            self,
            key_labels=labels  # Pass labels again for outer protection
        )


# ============ Example Client Usage ============

def example_client_usage():
    """
    Example of how to use spoiler data in a client.
    
    This shows patterns that can be used in actual client implementations.
    """
    # Note: No need to manually call process_slot_data_with_spoiler_info()
    # The system automatically extracts special_spoiler_data on Connected!
    
    # Simulated context after Connected packet
    class MockContext:
        def __init__(self):
            self.special_spoiler_data = {
                "real_keys": {
                    "???": "secret_location_1",
                    "???_1": "secret_location_2",
                    "???_2": "secret_location_3",
                },
                "real_items": {
                    "secret_location_1": "magic_sword",
                    "secret_location_2": "healing_potion",
                    "secret_location_3": "ancient_tome",
                }
            }
            
            # Simulate the helper methods (these are added by CommonClientSpoilerHandler)
            def get_all_revealed_keys(self):
                for data_entry in self.special_spoiler_data.values():
                    if 'real_keys' in data_entry:
                        return data_entry['real_keys']
                return {}
            
            def get_revealed_value(self, real_key):
                for data_entry in self.special_spoiler_data.values():
                    if 'real_items' in data_entry:
                        if real_key in data_entry['real_items']:
                            return data_entry['real_items'][real_key]
                return None
            
            # Bind methods
            self.get_all_revealed_keys = get_all_revealed_keys.__get__(self)
            self.get_revealed_value = get_revealed_value.__get__(self)
    
    ctx = MockContext()
    
    print("=== Using Revealed Keys (Automatic!) ===")
    
    # Map all labels to real keys
    all_keys = ctx.get_all_revealed_keys()
    print(f"Label mappings: {all_keys}")
    
    # Get all real items
    for spoiler_label, real_key in all_keys.items():
        value = ctx.get_revealed_value(real_key)
        print(f"{spoiler_label} ({real_key}) = {value}")


if __name__ == "__main__":
    example_client_usage()
