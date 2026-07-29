"""
Spoiler Dict Patcher - Automatically applies spoiler-free key labels to worlds.

Patches World.fill_slot_data to wrap return values in SpoilerDict.
Patches CommonClient to recognize and handle special_spoiler_data.

Usage:
    Simply import this module to enable automatic spoiler protection:
    from worlds.spoiler import apply_spoiler_protection_to_world
    
    # Or in a world's fill_slot_data:
    def fill_slot_data(self):
        slot_data = {...}
        return apply_spoiler_protection_to_world(
            slot_data, 
            self,
            key_labels={"real_key": "Spoiler-Free Label"}
        )
"""

import logging
from typing import Dict, Any, Optional, Mapping, Callable
import json
from .SpoilerDict import SpoilerDict

# Import CommonClient support (this initializes client-side patches)
try:
    from . import CommonClientSpoilerHandler
except ImportError:
    pass  # CommonClient may not be available in all contexts

logger = logging.getLogger("SpoilerDict Patcher")


def apply_spoiler_protection_to_world(
    slot_data: Dict[str, Any],
    world: Any,
    key_labels: Optional[Dict[str, str]] = None,
    protected_keys: Optional[list[str]] = None
) -> SpoilerDict:
    """
    Apply spoiler protection to a world's slot data.
    
    This function converts a regular dict to a SpoilerDict with spoiler-free labels.
    Can be called from a world's fill_slot_data method.
    
    Args:
        slot_data: The slot data dict to protect
        world: The world instance (for context/logging)
        key_labels: Optional mapping of real_key -> spoiler_free_label
                   If not provided, generic labels (???, ???_1, etc) will be generated
        protected_keys: Optional list of keys to specifically mark as needing protection
                       All other keys will be kept as-is (useful for partial protection)
    
    Returns:
        SpoilerDict with spoiler-free labels
    
    Example:
        def fill_slot_data(self):
            data = {
                "location_1": "item_a",
                "location_2": "item_b",
                "game_version": 1  # Not sensitive
            }
            return apply_spoiler_protection_to_world(
                data,
                self,
                key_labels={
                    "location_1": "First Area",
                    "location_2": "Second Area"
                }
            )
    """
    world_name = world.__class__.__name__ if hasattr(world, '__class__') else "Unknown"
    player = getattr(world, 'player', '?')
    
    # If key_labels not provided, all keys get generic labels
    if key_labels is None:
        key_labels = {}
        for idx, key in enumerate(slot_data.keys()):
            if idx == 0:
                key_labels[key] = "???"
            else:
                key_labels[key] = f"???_{idx}"
    
    logger.info(f"[Spoiler] Protecting slot data for {world_name} P{player}: {len(key_labels)} labels")
    
    # Add the real keys and values to a special field for the client
    spoiler_data = {
        "real_keys": {spoiler_free_label: real_key 
                     for real_key, spoiler_free_label in key_labels.items()},
        "real_items": dict(slot_data)  # Real key-value pairs
    }
    
    # Create the SpoilerDict
    spoiler_dict = SpoilerDict(real_data=slot_data, key_labels=key_labels)
    
    # Store the spoiler data in the dict itself (will be extracted before JSON serialization)
    spoiler_dict._spoiler_metadata = spoiler_data
    
    return spoiler_dict


def convert_dict_to_spoiler_dict(
    regular_dict: dict,
    key_labels: Optional[Dict[str, str]] = None
) -> SpoilerDict:
    """
    Convert a regular dict to a SpoilerDict.
    
    Args:
        regular_dict: The dict to convert
        key_labels: Optional mapping of real_key -> spoiler_free_label
    
    Returns:
        SpoilerDict instance
    """
    return SpoilerDict.from_dict(regular_dict, key_labels)


def extract_spoiler_metadata_for_slotdata(spoiler_dict: SpoilerDict) -> Dict[str, Any]:
    """
    Extract the spoiler metadata from a SpoilerDict for inclusion in slot_data.
    
    This is what gets added as "special_spoiler_data" in the Connected packet
    and is used by clients to map spoiler-free labels back to real keys.
    
    Args:
        spoiler_dict: The SpoilerDict instance
    
    Returns:
        Dict with real_keys and real_items for client-side reference
    """
    if hasattr(spoiler_dict, '_spoiler_metadata'):
        return spoiler_dict._spoiler_metadata
    
    # Fallback: reconstruct from the dict
    return {
        "real_keys": {spoiler_dict.get_label(k): k for k in spoiler_dict.revealed_keys()},
        "real_items": dict(spoiler_dict.revealed_items())
    }


def patch_slotdata_with_spoiler_data(slot_data: dict) -> dict:
    """
    Patch existing slot_data that contains SpoilerDict instances.
    
    Extracts spoiler metadata from any SpoilerDict values and adds them as
    "special_spoiler_data" for transmission to the client.
    
    This function modifies the slot_data dict in place.
    
    Args:
        slot_data: The slot data dict (may contain SpoilerDict instances)
    
    Returns:
        The modified slot_data dict
    """
    # Find all SpoilerDict instances in the slot_data
    spoiler_dicts_found = {}
    
    for key, value in slot_data.items():
        if isinstance(value, SpoilerDict):
            spoiler_dicts_found[key] = extract_spoiler_metadata_for_slotdata(value)
            logger.info(f"[Spoiler Patcher] Found SpoilerDict at slot_data['{key}']")
    
    # If we found any SpoilerDicts, add the metadata
    if spoiler_dicts_found:
        slot_data['special_spoiler_data'] = spoiler_dicts_found
        logger.info(f"[Spoiler Patcher] Added special_spoiler_data with {len(spoiler_dicts_found)} entries")
    
    return slot_data


# ============ Patch World.fill_slot_data ============
_original_world_getattribute = None


def _patch_world_fill_slot_data():
    """Patch World.__getattribute__ to intercept fill_slot_data calls."""
    from worlds import World
    global _original_world_getattribute
    
    if _original_world_getattribute is not None:
        logger.warning("[Spoiler Patcher] World already patched, skipping")
        return
    
    _original_world_getattribute = World.__getattribute__
    
    def _patched_world_getattribute(self, name: str):
        """Intercepts attribute access on World instances."""
        if name == 'fill_slot_data':
            original_method = _original_world_getattribute(self, name)
            
            def wrapped_fill_slot_data() -> Dict[str, Any]:
                result = original_method() if original_method else {}
                
                if not isinstance(result, dict):
                    result = {}
                
                # Add special_spoiler_data if there are any SpoilerDicts
                result = patch_slotdata_with_spoiler_data(result)
                
                return result
            
            return wrapped_fill_slot_data
        
        return _original_world_getattribute(self, name)
    
    World.__getattribute__ = _patched_world_getattribute
    logger.info("[Spoiler Patcher] Successfully patched World.__getattribute__")


# ============ Patch CommonClient to handle special_spoiler_data ============
_original_process_server_cmd = None


def _patch_common_client_slotdata():
    """Patch process_server_cmd to automatically handle special_spoiler_data in Connected."""
    import CommonClient
    import asyncio
    global _original_process_server_cmd
    
    if _original_process_server_cmd is not None:
        logger.warning("[Spoiler Patcher] CommonClient already patched, skipping")
        return
    
    _original_process_server_cmd = CommonClient.process_server_cmd
    
    async def _patched_process_server_cmd(ctx, args):
        """Patched process_server_cmd that auto-extracts special_spoiler_data."""
        # Call original handler first
        result = await _original_process_server_cmd(ctx, args)
        
        # Check if this is a Connected response with special_spoiler_data
        if isinstance(args, dict):
            # Initialize special_spoiler_data attribute if not present
            if not hasattr(ctx, 'special_spoiler_data'):
                ctx.special_spoiler_data = {}
            
            # Extract special_spoiler_data from slot_data if present
            if 'special_spoiler_data' in args:
                ctx.special_spoiler_data = args['special_spoiler_data']
                logger.info(f"[Spoiler Patcher] Auto-extracted special_spoiler_data from Connected: {len(ctx.special_spoiler_data)} entries")
        
        return result
    
    # Replace the function
    CommonClient.process_server_cmd = _patched_process_server_cmd
    logger.info("[Spoiler Patcher] Successfully patched process_server_cmd for automatic special_spoiler_data handling")


# ============ Apply patches on import ============
def initialize_spoiler_patcher():
    """Initialize all spoiler patcher patches."""
    try:
        _patch_world_fill_slot_data()
        _patch_common_client_slotdata()
        logger.info("[Spoiler Patcher] All patches initialized successfully")
    except Exception as e:
        logger.error(f"[Spoiler Patcher] Failed to initialize patches: {e}", exc_info=True)


# Initialize patches on module import
initialize_spoiler_patcher()


# ============ Export public API ============
__all__ = [
    'SpoilerDict',
    'apply_spoiler_protection_to_world',
    'convert_dict_to_spoiler_dict',
    'extract_spoiler_metadata_for_slotdata',
    'patch_slotdata_with_spoiler_data',
]
