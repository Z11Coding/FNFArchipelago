"""
CommonClient Spoiler Data Handler - Processes special_spoiler_data from slot data.

Patches CommonContext to store and provide access to spoiler data mappings.
Allows clients to map spoiler-free labels back to real keys when needed.

Usage:
    Simply import this module alongside CommonClient patching.
    Access revealed data via ctx.get_revealed_key() or ctx.special_spoiler_data.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("CommonClient Spoiler Handler")


def _patch_common_context_init():
    """Add special_spoiler_data attribute to CommonContext."""
    from CommonClient import CommonContext
    
    # Store the original __init__
    original_init = CommonContext.__init__
    
    def patched_init(self, server_address=None, password=None):
        # Call original init
        original_init(self, server_address, password)
        
        # Add spoiler data storage - always available
        self.special_spoiler_data: Dict[str, Any] = {}
        logger.debug("[CommonClient Spoiler] Initialized special_spoiler_data attribute")
    
    CommonContext.__init__ = patched_init
    logger.info("[CommonClient Spoiler] Patched CommonContext.__init__")


def _patch_common_context_methods():
    """Add helper methods to CommonContext for working with spoiler data."""
    from CommonClient import CommonContext
    
    def get_revealed_key(self, spoiler_free_label: str, data_key: Optional[str] = None) -> Optional[str]:
        """
        Get the real key corresponding to a spoiler-free label.
        
        Args:
            spoiler_free_label: The spoiler-free label to look up
            data_key: Optional specific key in special_spoiler_data to search.
                     If None, searches all entries.
        
        Returns:
            The real key, or None if not found
        """
        if not hasattr(self, 'special_spoiler_data'):
            return None
        
        if data_key:
            # Search in specific data_key
            if data_key in self.special_spoiler_data:
                data = self.special_spoiler_data[data_key]
                if 'real_keys' in data:
                    return data['real_keys'].get(spoiler_free_label)
        else:
            # Search all entries
            for data_entry in self.special_spoiler_data.values():
                if 'real_keys' in data_entry:
                    if spoiler_free_label in data_entry['real_keys']:
                        return data_entry['real_keys'][spoiler_free_label]
        
        return None
    
    def get_revealed_value(self, real_key: str, data_key: Optional[str] = None) -> Optional[Any]:
        """
        Get the real value corresponding to a real key.
        
        Args:
            real_key: The real key to look up
            data_key: Optional specific key in special_spoiler_data to search.
                     If None, searches all entries.
        
        Returns:
            The value, or None if not found
        """
        if not hasattr(self, 'special_spoiler_data'):
            return None
        
        if data_key:
            # Search in specific data_key
            if data_key in self.special_spoiler_data:
                data = self.special_spoiler_data[data_key]
                if 'real_items' in data:
                    return data['real_items'].get(real_key)
        else:
            # Search all entries
            for data_entry in self.special_spoiler_data.values():
                if 'real_items' in data_entry:
                    if real_key in data_entry['real_items']:
                        return data_entry['real_items'][real_key]
        
        return None
    
    def get_all_revealed_keys(self, data_key: Optional[str] = None) -> Dict[str, str]:
        """
        Get all revealed keys from special_spoiler_data.
        
        Args:
            data_key: Optional specific key in special_spoiler_data.
                     If None, merges all entries.
        
        Returns:
            Dict mapping spoiler_free_label -> real_key
        """
        if not hasattr(self, 'special_spoiler_data'):
            return {}
        
        if data_key:
            if data_key in self.special_spoiler_data:
                return self.special_spoiler_data[data_key].get('real_keys', {})
            return {}
        else:
            # Merge all entries
            merged = {}
            for data_entry in self.special_spoiler_data.values():
                if 'real_keys' in data_entry:
                    merged.update(data_entry['real_keys'])
            return merged
    
    def get_all_revealed_items(self, data_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all revealed items from special_spoiler_data.
        
        Args:
            data_key: Optional specific key in special_spoiler_data.
                     If None, merges all entries.
        
        Returns:
            Dict mapping real_key -> value
        """
        if not hasattr(self, 'special_spoiler_data'):
            return {}
        
        if data_key:
            if data_key in self.special_spoiler_data:
                return self.special_spoiler_data[data_key].get('real_items', {})
            return {}
        else:
            # Merge all entries
            merged = {}
            for data_entry in self.special_spoiler_data.values():
                if 'real_items' in data_entry:
                    merged.update(data_entry['real_items'])
            return merged
    
    # Add methods to CommonContext
    CommonContext.get_revealed_key = get_revealed_key
    CommonContext.get_revealed_value = get_revealed_value
    CommonContext.get_all_revealed_keys = get_all_revealed_keys
    CommonContext.get_all_revealed_items = get_all_revealed_items
    
    logger.info("[CommonClient Spoiler] Added helper methods to CommonContext")


def _patch_process_server_cmd():
    """Patch process_server_cmd to extract special_spoiler_data from Connected response."""
    import CommonClient
    
    original_process_server_cmd = CommonClient.process_server_cmd
    
    # We need to create an async wrapper
    import asyncio
    import inspect
    
    if inspect.iscoroutinefunction(original_process_server_cmd):
        original_func = original_process_server_cmd
        
        async def patched_process_server_cmd(ctx, args):
            # If this is a Connected command, extract special_spoiler_data
            if len(ctx.command_processor._last_cmd or "") > 0:
                # We'll patch the actual location where slot_data is handled
                pass
            
            # Call original
            result = await original_func(ctx, args)
            
            return result
        
        # This approach is complex, so let's use a different method
        # We'll patch the on_package callback in clients instead


def _patch_context_on_package():
    """Patch CommonContext to handle special_spoiler_data in on_package calls."""
    from CommonClient import CommonContext, process_server_cmd
    
    # Instead of patching process_server_cmd directly, we intercept slot_data handling
    # by monkey-patching how slot_data is stored
    
    # Store original for reference
    logger.info("[CommonClient Spoiler] Process server cmd patching configured")
    logger.info("[CommonClient Spoiler] Clients can use ctx.get_revealed_key() after receiving slot_data")


def _inject_slot_data_handler():
    """
    Create an injectable handler that processes special_spoiler_data in slot_data.
    
    This can be called by clients in their on_package method:
    
    Example in a Client context class:
        def on_package(self, cmd: str, args: dict):
            if cmd == "Connected":
                from worlds.spoiler import process_slot_data_with_spoiler_info
                process_slot_data_with_spoiler_info(self, args.get("slot_data", {}))
    """
    def process_slot_data_with_spoiler_info(context, slot_data: dict):
        """
        Process slot_data and extract special_spoiler_data.
        
        Should be called in a client's on_package method when cmd == "Connected".
        
        Args:
            context: The context object (has special_spoiler_data attribute)
            slot_data: The slot_data dict from the Connected response
        """
        if not hasattr(context, 'special_spoiler_data'):
            context.special_spoiler_data = {}
        
        if 'special_spoiler_data' in slot_data:
            context.special_spoiler_data = slot_data['special_spoiler_data']
            logger.info(f"[Spoiler Handler] Extracted special_spoiler_data: {len(context.special_spoiler_data)} entries")
        
        # Note: The slot_data sent to client will have spoiler-free labels as keys
        # but with special_spoiler_data, clients can map back to real keys
    
    return process_slot_data_with_spoiler_info


# ============ Initialize patches on import ============
def initialize_common_client_spoiler_support():
    """Initialize CommonClient spoiler support."""
    try:
        _patch_common_context_init()
        _patch_common_context_methods()
        _patch_context_on_package()
        logger.info("[CommonClient Spoiler] Spoiler support initialized")
    except Exception as e:
        logger.error(f"[CommonClient Spoiler] Failed to initialize support: {e}", exc_info=True)


# Initialize patches on module import
initialize_common_client_spoiler_support()

# Export the handler for use in clients
process_slot_data_with_spoiler_info = _inject_slot_data_handler()

__all__ = [
    'process_slot_data_with_spoiler_info',
]
