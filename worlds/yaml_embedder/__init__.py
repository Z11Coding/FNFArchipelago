from typing import Dict, Any
import logging
import os
import gzip
import base64
import json
from worlds.AutoWorld import World
from BaseClasses import MultiWorld

try:
    from worlds.yaml_embedder.yaml_recreator import generate_format_metadata
    _has_yaml_recreator = True
except ImportError:
    _has_yaml_recreator = False

logger = logging.getLogger("YAML Embedder")


def set_player_files(player_files: Dict[int, str]) -> None:
    """Called to store player_files mapping."""
    global _player_files_cache
    _player_files_cache.clear()
    _player_files_cache.update(player_files)
    logger.info(f"[YAML Embedder] Got Player Files! - cached {len(player_files)} player file(s)")
    for player_id, yaml_str in player_files.items():
        yaml_size = len(yaml_str) if yaml_str else 0
        logger.info(f"[YAML Embedder]   P{player_id}: {yaml_size} chars")


def get_player_files() -> Dict[int, str]:
    """Called to retrieve player_files mapping."""
    global _player_files_cache
    logger.info(f"[YAML Embedder] Retrieved Player Files - {len(_player_files_cache)} cached player file(s)")
    return _player_files_cache.copy()


def _compress_yaml_metadata(yaml_string: str, options_dict: dict, formats_dict: dict = None) -> str:
    """Compress YAML metadata into a single base64-encoded gzip string.
    
    Args:
        yaml_string: The original YAML content
        options_dict: The slot options dict
        formats_dict: Optional format metadata dict
    
    Returns:
        Base64-encoded gzipped JSON containing all three pieces of data
    """
    try:
        # Build the metadata structure
        metadata = {
            "yaml": yaml_string,
            "options": options_dict,
            "formats": formats_dict or {}
        }
        
        # Convert to JSON
        json_str = json.dumps(metadata, separators=(',', ':'))
        
        # Compress with gzip
        compressed = gzip.compress(json_str.encode('utf-8'))
        
        # Encode as base64
        encoded = base64.b64encode(compressed).decode('ascii')
        
        original_size = len(yaml_string) + len(json.dumps(options_dict)) + (len(json.dumps(formats_dict)) if formats_dict else 0)
        compressed_size = len(encoded)
        ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
        logger.info(f"[YAML Embedder] Compressed: {original_size} → {compressed_size} bytes ({ratio:.1f}%)")
        
        return encoded
    except Exception as e:
        logger.error(f"[YAML Embedder] Failed to compress YAML metadata: {e}", exc_info=True)
        raise


def _decompress_yaml_metadata(compressed_string: str) -> Dict[str, Any]:
    """Decompress YAML metadata from a base64-encoded gzip string.
    
    Args:
        compressed_string: Base64-encoded gzipped JSON
    
    Returns:
        Dict with 'yaml', 'options', and 'formats' keys
    """
    try:
        # Decode from base64
        compressed = base64.b64decode(compressed_string.encode('ascii'))
        
        # Decompress with gzip
        json_str = gzip.decompress(compressed).decode('utf-8')
        
        # Parse JSON
        metadata = json.loads(json_str)
        
        return metadata
    except Exception as e:
        logger.error(f"[YAML Embedder] Failed to decompress YAML metadata: {e}", exc_info=True)
        raise


def _represent_yaml_with_randomization(yaml_dict: dict) -> dict:
    """Return YAML dict as-is, preserving the actual randomization structure.
    
    The randomization is already represented in the data:
    - Lists stay as lists (random choice)
    - Dicts with numeric values stay as weighted dicts
    - Scalar values stay as scalars
    
    No conversion needed - we return the structure unchanged.
    """
    return yaml_dict


def _build_player_files_from_path(player_files_path: str, meta_file_path: str, weights_file_path: str) -> Dict[int, str]:
    """Replicate Generate.main's logic for building player_files dict from directory.
    
    Stores YAML representation with randomization marked but not applied,
    showing the {random: ...} or {random-weighted: ...} structure instead of picking values.
    """
    try:
        from Generate import read_weights_yamls, get_choice
        import Utils
        
        logger.info(f"[YAML Embedder] _build_player_files_from_path: scanning {player_files_path}")
        
        player_id = 1
        player_files: Dict[int, str] = {}
        weights_cache = {}
        
        # Scan directory
        for file in os.scandir(player_files_path):
            fname = file.name
            if file.is_file() and not fname.startswith(".") and not fname.lower().endswith(".ini") and \
                    os.path.join(player_files_path, fname) not in {meta_file_path, weights_file_path}:
                path = os.path.join(player_files_path, fname)
                logger.info(f"[YAML Embedder] Read {fname}")
                try:
                    weights_for_file = []
                    for doc_idx, yaml in enumerate(read_weights_yamls(path)):
                        if yaml is None:
                            logger.warning(f"[YAML Embedder] Empty YAML in {fname}")
                        else:
                            weights_for_file.append(yaml)
                    weights_cache[fname] = tuple(weights_for_file)
                    logger.info(f"[YAML Embedder] Read {len(weights_for_file)} docs from {fname}")
                except Exception as e:
                    logger.error(f"[YAML Embedder] Exception reading weights in file {fname}: {e}")
        
        logger.info(f"[YAML Embedder] Found {len(weights_cache)} YAML files")
        
        # Sort and build player_files mapping
        weights_cache = {key: value for key, value in sorted(weights_cache.items(), key=lambda k: k[0].casefold())}
        
        for filename, yaml_data in weights_cache.items():
            if filename not in {os.path.basename(meta_file_path), os.path.basename(weights_file_path)}:
                for yaml in yaml_data:
                    description = get_choice('description', yaml, 'No description specified')
                    logger.info(f"[YAML Embedder] P{player_id}: {filename}")
                    
                    # Represent randomization without applying it
                    yaml_with_randomization = _represent_yaml_with_randomization(yaml)
                    
                    # Store the YAML content as string representation
                    import yaml as yaml_module
                    yaml_str = yaml_module.dump(yaml_with_randomization, default_flow_style=False)
                    yaml_size = len(yaml_str)
                    player_files[player_id] = yaml_str
                    logger.info(f"[YAML Embedder] P{player_id}: {yaml_size} bytes")
                    player_id += 1
        
        logger.info(f"[YAML Embedder] Built {len(player_files)} player file(s)")
        return player_files
    except Exception as e:
        logger.error(f"[YAML Embedder] Failed to build: {e}")
        return {}


def _generate_annotated_yaml(original_yaml: str, slot_options: dict, options_obj: Any = None, game_name: str = None) -> str:
    """Generate YAML with annotations showing randomization changes.
    
    Compares original YAML with actual options to detect changes.
    Adds comments above changed options while preserving the full structure.
    
    Args:
        original_yaml: YAML string (from decompressed ap_slot_meta_yaml_info['yaml'])
        slot_options: Dict of actual selected values (from decompressed ap_slot_meta_yaml_info['options'])
        options_obj: The world's options object containing Option instances with mappings
        game_name: The game name key to look for in nested YAML structure
    
    Returns:
        YAML string with annotation comments for changed options
    """
    if not slot_options:
        return original_yaml
    
    try:
        import yaml as yaml_module
        
        # Parse original YAML
        original_data = yaml_module.safe_load(original_yaml)
        if not isinstance(original_data, dict):
            return original_yaml
        
        # Find the game options dict
        # First, check if there's a top-level 'game' field that tells us the game name
        metadata_keys = {'description', 'game', 'name', 'ap_slot_meta_yaml_info'}
        game_options_dict = None
        game_key_from_yaml = None
        
        # Try to get game name from top-level 'game' field
        if 'game' in original_data:
            yaml_game_value = original_data['game']
            # If game field is a string, use it as the key
            if isinstance(yaml_game_value, str):
                game_key_from_yaml = yaml_game_value
                if game_key_from_yaml in original_data and isinstance(original_data[game_key_from_yaml], dict):
                    game_options_dict = original_data[game_key_from_yaml]
            # If game field is a random list, we can't determine which game was selected from YAML alone
            # In this case, fall through to other methods
        
        # If we couldn't find via game field, find the first non-metadata dict key
        if game_options_dict is None:
            for key, value in original_data.items():
                if isinstance(value, dict) and key not in metadata_keys:
                    game_options_dict = value
                    game_key_from_yaml = key
                    break
        
        if game_options_dict is None:
            # If no nested structure found, assume flat (all top-level is options)
            game_options_dict = {k: v for k, v in original_data.items() if k not in metadata_keys}
        
        # Build a mapping of option names to their Option objects
        option_objects = {}
        try:
            if options_obj and hasattr(options_obj, '__dict__'):
                # Dataclass-like object - Option instances are attributes
                for key, value in options_obj.__dict__.items():
                    if not key.startswith('_'):
                        option_objects[key] = value
            elif options_obj and hasattr(options_obj, 'items'):
                # Dict-like object
                for key, value in options_obj.items():
                    option_objects[key] = value
            pass
        except Exception as e:
            pass
        
        # Find changed options by comparing with slot_options
        changed_options = {}
        
        # Debug: Log what keys are in slot_options
        pass
        
        for option_name, final_value in slot_options.items():
            # Skip the mapping dicts themselves (they won't be in game_options_dict anyway)
            if option_name.startswith("option_"):
                continue
                
            if option_name not in game_options_dict:
                continue
                
            original_value = game_options_dict[option_name]
            
            # Get the Option object to check for mapping
            option_obj = option_objects.get(option_name)
            
            # Try to find the mapping dict within the Option object
            mapping_dict = None
            if option_obj and hasattr(option_obj, 'options'):
                mapping_dict = option_obj.options
                logger.info(f"DEBUG: {option_name} has options attr: {type(mapping_dict)}")
            
            # If no mapping found yet, check for other attrs (but NOT valid_keys as primary)
            if mapping_dict is None and option_obj and hasattr(option_obj, '__dict__'):
                for attr_name in ['options_dict', 'option_mapping', 'values_dict']:
                    if hasattr(option_obj, attr_name):
                        potential_mapping = getattr(option_obj, attr_name)
                        if isinstance(potential_mapping, dict):
                            mapping_dict = potential_mapping
                            logger.info(f"DEBUG: {option_name} found mapping as {attr_name}")
                            break
            
            # Only use valid_keys as last resort fallback
            if mapping_dict is None and option_obj and hasattr(option_obj, 'valid_keys'):
                potential_mapping = getattr(option_obj, 'valid_keys')
                if isinstance(potential_mapping, (list, tuple)):
                    # If it's valid_keys, build a mapping from index
                    logger.info(f"DEBUG: {option_name} using valid_keys as fallback: {potential_mapping}")
                    mapping_dict = {str(k): i for i, k in enumerate(potential_mapping)}
                    logger.info(f"DEBUG: {option_name} converted valid_keys to mapping: {mapping_dict}")
            
            has_mapping = mapping_dict is not None and isinstance(mapping_dict, dict)
            logger.info(f"DEBUG: {option_name} - has_mapping={has_mapping}, original={repr(original_value)}, final={repr(final_value)}")
            if has_mapping:
                logger.info(f"DEBUG: {option_name} mapping keys: {list(mapping_dict.keys())}")
            
            # Detect if this was randomized
            was_randomized = False
            if isinstance(original_value, str):
                if original_value.lower() == 'random':
                    was_randomized = True
                    logger.info(f"DEBUG: {option_name} detected as randomized (string 'random')")
                elif 'random' in original_value.lower():
                    was_randomized = True
                    logger.info(f"DEBUG: {option_name} detected as randomized (string contains 'random')")
            elif isinstance(original_value, dict) and ('random' in original_value or 'random-weighted' in original_value):
                was_randomized = True
                logger.info(f"DEBUG: {option_name} detected as randomized (dict with random key)")
            
            # Skip if nothing changed
            if original_value == final_value:
                logger.info(f"DEBUG: {option_name} - skipping, no change")
                continue
            
            # Case 1: String-to-number format change via mapping (should be skipped)
            logger.info(f"DEBUG: {option_name} CHECK SKIP: not_randomized={not was_randomized}, has_mapping={has_mapping}, is_str={isinstance(original_value, str)}")
            if not was_randomized and has_mapping and isinstance(original_value, str):
                logger.info(f"DEBUG: {option_name} - checking if in mapping_dict...")
                logger.info(f"DEBUG: {option_name} - original_value='{original_value}', mapping keys={list(mapping_dict.keys())}")
                if original_value in mapping_dict:
                    mapped_val = mapping_dict[original_value]
                    logger.info(f"DEBUG: {option_name} - found in mapping: maps to {mapped_val}, final={final_value}, equal={mapped_val == final_value}")
                    if mapped_val == final_value:
                        logger.info(f"DEBUG: {option_name} - SKIPPING format change: '{original_value}' maps to {final_value}")
                        continue
                else:
                    logger.info(f"DEBUG: {option_name} - NOT in mapping dict")
            
            # For non-mapping string options, also check if it's a simple string-to-number format where the original == final when both are strings
            if (not was_randomized and isinstance(original_value, str) and isinstance(final_value, int)):
                # Try to parse the string as a number to see if they're the same
                try:
                    parsed_original = int(original_value)
                    if parsed_original == final_value:
                        logger.info(f"DEBUG: {option_name} - SKIPPING string-to-int format change: '{original_value}' == {final_value}")
                        continue
                except (ValueError, TypeError):
                    pass
            
            # Case 2: Randomized option (show with actual mapped name if available)
            if was_randomized:
                if has_mapping:
                    # Reverse-lookup: find the string key that maps to final_value
                    mapped_key_name = None
                    for key, value in mapping_dict.items():
                        if value == final_value:
                            mapped_key_name = key
                            break
                    
                    if mapped_key_name:
                        # For randomized options with mapping, show: random → actual_name (final_value)
                        changed_options[option_name] = {
                            "original": "random",
                            "new": f"{mapped_key_name} ({final_value})"
                        }
                        logger.info(f"DEBUG: {option_name} - ANNOTATE RANDOMIZED with mapped key: {mapped_key_name}")
                    else:
                        # Fallback if we can't reverse-lookup
                        changed_options[option_name] = {
                            "original": "random",
                            "new": final_value
                        }
                        logger.info(f"DEBUG: {option_name} - ANNOTATE RANDOMIZED (couldn't reverse-lookup mapped key, using value: {final_value})")
                else:
                    # Randomized but no mapping - just show the difference
                    changed_options[option_name] = {
                        "original": "random",
                        "new": final_value
                    }
                    logger.info(f"DEBUG: {option_name} - ANNOTATE RANDOMIZED without mapping (no mapping available)")
            else:
                # Case 3: Regular change (non-randomized, not a format change)
                changed_options[option_name] = {
                    "original": original_value,
                    "new": final_value
                }
                logger.info(f"DEBUG: {option_name} - ANNOTATE regular change")
        
        if not changed_options:
            return original_yaml
        
        # Add annotations to YAML, preserving indentation and structure
        lines = original_yaml.split('\n')
        annotated_lines = []
        
        for line in lines:
            # Check if this line defines a changed option (accounting for indentation)
            for option_name in changed_options.keys():
                stripped = line.strip()
                if stripped.startswith(f"{option_name}:"):
                    change_info = changed_options[option_name]
                    comment = f"# Randomized/Converted: {change_info['original']} → {change_info['new']}"
                    annotated_lines.append(comment)
                    break
            
            annotated_lines.append(line)
        
        return '\n'.join(annotated_lines)
    
    except Exception as e:
        logger.warning(f"[YAML Embedder] Error generating annotated YAML: {e}")
        return original_yaml



# ============ Patch MultiWorld ============
_original_multiworld_init = MultiWorld.__init__


def _patched_multiworld_init(self, players: int):
    """Patched MultiWorld.__init__ that adds player_files dict."""
    _original_multiworld_init(self, players)
    # Add dict to store YAML data by player ID
    self.player_files: Dict[int, str] = {}
    
    # Immediately populate from cache if available
    # This ensures fill_slot_data has access to YAML during generation
    global _player_files_cache
    if _player_files_cache:
        self.player_files.update(_player_files_cache)
        logger.info(f"[YAML Embedder] MultiWorld.__init__ patched - populated player_files dict with {len(_player_files_cache)} cached file(s)")
    else:
        logger.info(f"[YAML Embedder] MultiWorld.__init__ patched - added player_files dict (cache empty)")


MultiWorld.__init__ = _patched_multiworld_init
logger.info("[YAML Embedder] Successfully patched MultiWorld.__init__")


# ============ Patch Main.main to retrieve/build player_files ============
def _patch_main_function():
    """Patches Main.main() to build and inject player_files into multiworld after creation."""
    try:
        from Main import main as original_main
        
        def patched_main(args, seed=None, baked_server_options=None):
            """Wrapped Main.main that builds and injects player_files into multiworld."""
            logger.info("[YAML Embedder] patched Main.main() called")
            logger.info(f"[YAML Embedder] player_files_path: {args.player_files_path}")
            
            # Build player_files dict from the same args that Generate.main used
            logger.info("[YAML Embedder] Building player_files from player directory...")
            player_files = _build_player_files_from_path(
                args.player_files_path,
                args.meta_file_path,
                args.weights_file_path
            )
            logger.info(f"[YAML Embedder] Built {len(player_files)} player file(s)")
            
            if player_files:
                set_player_files(player_files)
            
            logger.info("[YAML Embedder] Calling original Main.main()...")
            multiworld = original_main(args, seed, baked_server_options)
            logger.info(f"[YAML Embedder] Main.main() returned, multiworld has {multiworld.players} player(s)")
            
            # Inject player_files into multiworld
            if hasattr(multiworld, 'player_files'):
                if player_files:
                    multiworld.player_files.update(player_files)
                    logger.info(f"[YAML Embedder] INJECTED {len(player_files)} player file(s) into multiworld.player_files")
                    logger.info(f"[YAML Embedder] multiworld.player_files now contains: {list(multiworld.player_files.keys())}")
                else:
                    logger.warning("[YAML Embedder] No player_files were built (will be empty)")
            else:
                logger.error("[YAML Embedder] multiworld doesn't have player_files attribute - patching may have failed!")
            
            # Ask user if they want to save randomized YAML files
            try:
                response = input("\n[YAML Embedder] Save randomized YAML files to output folder? (yes/no): ").strip().lower()
                if response in ('yes', 'y'):
                    pass
            except Exception as e:
                logger.error(f"[YAML Embedder] Error during YAML save prompt: {e}")

            return multiworld
        
        # Patch the Main module
        import Main
        Main.main = patched_main
        logger.info("[YAML Embedder] Successfully patched Main.main")
    except Exception as e:
        logger.error(f"[YAML Embedder] Failed to patch Main.main: {e}")


# Apply patches on import
logger.info("[YAML Embedder] Initializing patches...")
_patch_main_function()
logger.info("[YAML Embedder] Patches initialized")


# ============ Patch World fill_slot_data ============
_original_world_getattribute = World.__getattribute__


def _patched_world_getattribute(self, name: str):
    """Intercepts all attribute access on World instances."""
    # If someone is accessing fill_slot_data, wrap it
    if name == 'fill_slot_data':
        original_method = _original_world_getattribute(self, name)
        
        def wrapped_fill_slot_data() -> Dict[str, Any]:
            # Call the original fill_slot_data with no arguments
            result = original_method() if original_method else {}
            
            # Ensure result is a dict
            if not isinstance(result, dict):
                result = {}
            
            world_name = "Unknown"
            player = "?"
            player_name = "Unknown"
            
            # Get world and player info
            try:
                world_name = _original_world_getattribute(self, '__class__').__name__
                player = _original_world_getattribute(self, 'player')
                multiworld: MultiWorld = _original_world_getattribute(self, 'multiworld')
                
                # Get player name from multiworld
                if hasattr(multiworld, 'player_name') and isinstance(multiworld.player_name, dict):
                    player_name = multiworld.player_name.get(player, f"Player {player}")
                elif hasattr(multiworld, 'get_player_name'):
                    player_name = multiworld.get_player_name(player)
                else:
                    player_name = f"Player {player}"
            except Exception as e:
                logger.debug(f"[YAML Embedder] Failed to get player info: {e}")
            
            # Add top-level slot data fields (these go first)
            try:
                if 'name' not in result:
                    result['name'] = player_name
                    logger.info(f"[YAML Embedder] Added slot name: {player_name}")
                if 'game' not in result:
                    result['game'] = world_name
                    logger.info(f"[YAML Embedder] Added game: {world_name}")
                if 'description' not in result:
                    result['description'] = f"Archipelago slot for {player_name}"
                    logger.info(f"[YAML Embedder] Added description")
            except Exception as e:
                logger.warning(f"[YAML Embedder] Failed to add top-level fields: {e}")
            
            # Build world options dict for compression (but don't add to result)
            slot_options_for_compression = {}
            try:
                world_name = _original_world_getattribute(self, '__class__').__name__
                player = _original_world_getattribute(self, 'player')
                options_obj = _original_world_getattribute(self, 'options')
                
                # Options can be a dataclass or dict-like - handle both
                if hasattr(options_obj, '__dict__'):
                    # Dataclass-like object
                    slot_options_for_compression = {
                        key: value.value if hasattr(value, 'value') else value
                        for key, value in options_obj.__dict__.items()
                        if not key.startswith('_')
                    }
                elif hasattr(options_obj, 'items'):
                    # Dict-like object
                    slot_options_for_compression = {
                        option_name: option.value if hasattr(option, 'value') else option
                        for option_name, option in options_obj.items()
                    }
                else:
                    logger.warning(f"[YAML Embedder] Options object type unknown: {type(options_obj)}")
                    slot_options_for_compression = {}
                
                logger.info(f"[YAML Embedder] Built options for compression for {world_name} P{player}: {len(slot_options_for_compression)} keys")
            except Exception as e:
                logger.warning(f"[YAML Embedder] Failed to build options for {world_name} P{player}: {e}")
            
            # Add the YAML that created this world (compressed into single key)
            try:
                multiworld: MultiWorld = _original_world_getattribute(self, 'multiworld')
                player = _original_world_getattribute(self, 'player')
                world_name = _original_world_getattribute(self, '__class__').__name__
                
                # Debug: check multiworld state
                has_player_files = hasattr(multiworld, 'player_files')
                player_in_dict = player in (multiworld.player_files if has_player_files else {})
                logger.info(f"[YAML Embedder] fill_slot_data called for {world_name} P{player}: has_player_files={has_player_files}, player_in_dict={player_in_dict}")
                
                # Look up YAML by player ID
                if has_player_files and player_in_dict:
                    yaml_data = multiworld.player_files[player]
                    yaml_size = len(yaml_data) if yaml_data else 0
                    logger.info(f"[YAML Embedder] Found yaml_data for {world_name} P{player}: {yaml_size} chars")
                    
                    if yaml_data:
                        # Generate format metadata if yaml_recreator is available
                        formats_metadata = None
                        if _has_yaml_recreator:
                            try:
                                formats_metadata = generate_format_metadata(yaml_data)
                                logger.info(f"[YAML Embedder] Generated format metadata for {world_name} P{player}")
                            except Exception as e:
                                logger.warning(f"[YAML Embedder] Failed to generate format metadata: {e}")
                        
                        # Get options that were already added to result
                        slot_options = result.get('ap_slot_options', {})
                        
                        # Compress all three pieces into one key
                        try:
                            compressed_meta = _compress_yaml_metadata(yaml_data, slot_options, formats_metadata)
                            result['ap_slot_meta_yaml_info'] = compressed_meta
                            logger.info(f"[YAML Embedder] INJECTED ap_slot_meta_yaml_info (compressed) into slot_data for {world_name} P{player}")
                        except Exception as e:
                            logger.error(f"[YAML Embedder] Failed to compress YAML metadata: {e}", exc_info=True)
                            raise
                    else:
                        logger.warning(f"[YAML Embedder] yaml_data is empty for {world_name} P{player}")
                else:
                    if not has_player_files:
                        logger.warning(f"[YAML Embedder] multiworld does NOT have player_files attribute for {world_name} P{player}")
                    else:
                        logger.warning(f"[YAML Embedder] Player {player} NOT in multiworld.player_files for {world_name} (available: {list(multiworld.player_files.keys())})")
            except Exception as e:
                logger.error(f"[YAML Embedder] Failed to add ap_slot_meta_yaml_info for {world_name} P{player}: {e}", exc_info=True)

            logger.info(f"[YAML Embedder] fill_slot_data FINAL result keys for {world_name} P{player}: {list(result.keys())}")
            
            return result
        
        return wrapped_fill_slot_data
    
    # For all other attributes, use the original behavior
    return _original_world_getattribute(self, name)


World.__getattribute__ = _patched_world_getattribute
logger.info("[YAML Embedder] Successfully patched World.__getattribute__")


# ============ Launcher Component Registration ============
try:
    from worlds.LauncherComponents import Component, components, Type as ComponentType
    
    def _launch_yaml_viewer(*args):
        """Launch the YAML Viewer application."""
        try:
            from worlds.yaml_embedder.YAMLViewerClient import launch as yaml_viewer_launch
            from worlds.LauncherComponents import launch
            logger.info("[YAML Embedder] Launching YAML Viewer...")
            launch(yaml_viewer_launch, name="YAML Viewer", args=args)
        except Exception as e:
            logger.error(f"[YAML Embedder] Failed to launch YAML Viewer: {e}")
    
    components.append(
        Component(
            "YAML Viewer",
            func=_launch_yaml_viewer,
            component_type=ComponentType.MISC,
            supports_uri=False,
            description="Download and view slot YAML files from Archipelago servers."
        )
    )
    logger.info("[YAML Embedder] YAML Viewer registered in Archipelago Launcher")
except ImportError:
    logger.debug("[YAML Embedder] LauncherComponents not available, skipping launcher registration")
