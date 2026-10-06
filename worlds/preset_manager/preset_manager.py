"""Preset Manager - singleton for loading and managing option presets across all worlds."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Type

from worlds.AutoWorld import AutoWorldRegister, World
from Utils import user_path, local_path

from .structures import Preset, PresetCollection

logger = logging.getLogger("PresetManager")


class PresetManager:
    """Singleton for managing option presets across all games."""

    _instance: Optional['PresetManager'] = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize PresetManager. Safe to call multiple times."""
        if PresetManager._initialized:
            return
        
        self._collections: Dict[str, PresetCollection] = {}
        self._load_all_presets()
        PresetManager._initialized = True

    def _load_all_presets(self) -> None:
        """Load presets from all registered worlds."""
        logger.info("[PRESET-MANAGER] Loading presets from all worlds...")
        
        for game_name, world_cls in AutoWorldRegister.world_types.items():
            try:
                collection = PresetCollection(game_name)
                
                # Discover presets from multiple sources with priority
                presets_found = 0
                
                # Priority 1: World.world_presets (new system)
                presets_found += self._load_from_world_presets(world_cls, collection)
                
                # Priority 2: World.options_dataclass.preset_collections (Options class)
                presets_found += self._load_from_options_presets(world_cls, collection)
                
                # Priority 3: WebWorld.options_presets (legacy system)
                presets_found += self._load_from_legacy_options_presets(world_cls, collection)
                
                # Priority 4: Load user presets from JSON storage
                presets_found += self._load_user_presets_for_collection(game_name, collection)
                
                # Always add auto-generated default preset
                self._add_default_preset(world_cls, collection)
                
                self._collections[game_name] = collection
                if presets_found > 0:
                    logger.info(f"[PRESET-MANAGER] Loaded {presets_found} preset(s) for {game_name}")
            except Exception as e:
                logger.error(f"[PRESET-MANAGER] Failed to load presets for {game_name}: {e}", exc_info=True)

    def _load_from_world_presets(self, world_cls: Type[World], collection: PresetCollection) -> int:
        """Load presets from World.world_presets attribute.
        
        Returns:
            Number of presets loaded
        """
        if not hasattr(world_cls, 'world_presets'):
            return 0
        
        world_presets = world_cls.world_presets
        count = 0
        
        # Handle: Dict[str, Dict[str, Any]] format
        if isinstance(world_presets, dict):
            for preset_name, preset_options in world_presets.items():
                if isinstance(preset_options, dict):
                    preset = Preset(
                        name=preset_name,
                        description=f"Preset for {world_cls.game}",
                        options=preset_options.copy()
                    )
                    collection.add_preset(preset)
                    count += 1
        
        # Handle: Dict[str, Preset] format
        elif isinstance(world_presets, dict):
            for preset_name, preset_obj in world_presets.items():
                if isinstance(preset_obj, Preset):
                    collection.add_preset(preset_obj)
                    count += 1
        
        # Handle: List[Preset] format
        elif isinstance(world_presets, list):
            for preset_obj in world_presets:
                if isinstance(preset_obj, Preset):
                    collection.add_preset(preset_obj)
                    count += 1
        
        return count

    def _load_from_options_presets(self, world_cls: Type[World], collection: PresetCollection) -> int:
        """Load presets from World.options_dataclass.preset_collections attribute.
        
        Returns:
            Number of presets loaded
        """
        try:
            options_dataclass = getattr(world_cls, 'options_dataclass', None)
            if not options_dataclass:
                return 0
            
            preset_collections = getattr(options_dataclass, 'preset_collections', None)
            if not preset_collections:
                return 0
            
            count = 0
            
            # Handle: Dict[str, Dict[str, Any]] format
            if isinstance(preset_collections, dict):
                for preset_name, preset_options in preset_collections.items():
                    if isinstance(preset_options, dict):
                        preset = Preset(
                            name=preset_name,
                            description=f"Preset for {world_cls.game}",
                            options=preset_options.copy()
                        )
                        collection.add_preset(preset)
                        count += 1
            
            # Handle: List[Preset] format
            elif isinstance(preset_collections, list):
                for preset_obj in preset_collections:
                    if isinstance(preset_obj, Preset):
                        collection.add_preset(preset_obj)
                        count += 1
            
            return count
        except Exception as e:
            logger.debug(f"[PRESET-MANAGER] No preset_collections in {world_cls.game} options: {e}")
            return 0

    def _load_from_legacy_options_presets(self, world_cls: Type[World], collection: PresetCollection) -> int:
        """Load presets from WebWorld.options_presets (legacy system).
        
        Converts legacy format to new Preset objects.
        
        Returns:
            Number of presets loaded
        """
        try:
            web = getattr(world_cls, 'web', None)
            if not web:
                return 0
            
            options_presets = getattr(web, 'options_presets', None)
            if not options_presets or not isinstance(options_presets, dict):
                return 0
            
            count = 0
            for preset_name, preset_options in options_presets.items():
                if isinstance(preset_options, dict):
                    preset = Preset(
                        name=preset_name,
                        description=f"Preset for {world_cls.game}",
                        options=preset_options.copy()
                    )
                    collection.add_preset(preset)
                    count += 1
            
            return count
        except Exception as e:
            logger.debug(f"[PRESET-MANAGER] No legacy options_presets for {world_cls.game}: {e}")
            return 0

    def _add_default_preset(self, world_cls: Type[World], collection: PresetCollection) -> None:
        """Generate the default preset from World option defaults.
        
        This preset is always available and represents the default values.
        """
        try:
            # Create a temporary instance to get default values
            default_options = {}
            
            options_dataclass = getattr(world_cls, 'options_dataclass', None)
            if options_dataclass and hasattr(options_dataclass, 'type_hints'):
                for option_name, option_type in options_dataclass.type_hints.items():
                    if hasattr(option_type, 'default'):
                        default_options[option_name] = option_type.default
            
            collection.set_default_options(default_options)
        except Exception as e:
            logger.debug(f"[PRESET-MANAGER] Could not generate default preset for {world_cls.game}: {e}")

    def _load_user_presets_for_collection(self, game_name: str, collection: PresetCollection) -> int:
        """Load user presets from JSON storage for a specific game.
        
        Returns:
            Number of presets loaded
        """
        presets_file = self._get_user_presets_path()
        
        if not presets_file.exists():
            return 0
        
        try:
            with open(presets_file, 'r') as f:
                presets_data = json.load(f)
            
            if game_name not in presets_data:
                return 0
            
            count = 0
            for preset_data in presets_data[game_name]:
                preset = Preset(
                    name=preset_data.get('name', 'Unknown'),
                    description=preset_data.get('description', ''),
                    options=preset_data.get('options', {})
                )
                collection.add_preset(preset, overwrite_warning=False)
                count += 1
            
            return count
        except Exception as e:
            logger.debug(f"[PRESET-MANAGER] Failed to load user presets for {game_name}: {e}")
            return 0

    def get_preset(self, game_name: str, preset_name: str) -> Optional[Preset]:
        """Get a preset by game and name.
        
        Args:
            game_name: Name of the game
            preset_name: Name of the preset
            
        Returns:
            Preset object or None if not found
        """
        collection = self._collections.get(game_name)
        if collection:
            return collection.get_preset(preset_name)
        return None

    def get_presets(self, game_name: str) -> Optional[PresetCollection]:
        """Get all presets for a game.
        
        Args:
            game_name: Name of the game
            
        Returns:
            PresetCollection object or None if game not found
        """
        return self._collections.get(game_name)

    def get_all_games(self) -> List[str]:
        """Get list of all games with presets."""
        return sorted(self._collections.keys())

    def save_user_preset(self, game_name: str, preset: Preset) -> None:
        """Save a user-created preset to persistent storage.
        
        Args:
            game_name: Name of the game
            preset: Preset object to save
        """
        presets_file = self._get_user_presets_path()
        
        # Load existing presets
        presets_data = {}
        if presets_file.exists():
            try:
                with open(presets_file, 'r') as f:
                    presets_data = json.load(f)
            except Exception as e:
                logger.error(f"[PRESET-MANAGER] Failed to read presets file: {e}")
                presets_data = {}
        
        # Add/update preset
        if game_name not in presets_data:
            presets_data[game_name] = []
        
        # Remove if exists (to update)
        presets_data[game_name] = [
            p for p in presets_data[game_name] 
            if p.get('name') != preset.name
        ]
        
        # Add new preset
        presets_data[game_name].append({
            'name': preset.name,
            'description': preset.description,
            'options': preset.options
        })
        
        # Save
        presets_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(presets_file, 'w') as f:
                json.dump(presets_data, f, indent=2)
            logger.info(f"[PRESET-MANAGER] Saved user preset '{preset.name}' for {game_name}")
        except Exception as e:
            logger.error(f"[PRESET-MANAGER] Failed to save preset: {e}")

    def delete_user_preset(self, game_name: str, preset_name: str) -> None:
        """Delete a user-created preset from persistent storage.
        
        Args:
            game_name: Name of the game
            preset_name: Name of the preset to delete
        """
        if preset_name == "default":
            logger.warning("[PRESET-MANAGER] Cannot delete the 'default' preset")
            return
        
        presets_file = self._get_user_presets_path()
        
        if not presets_file.exists():
            return
        
        try:
            with open(presets_file, 'r') as f:
                presets_data = json.load(f)
            
            if game_name in presets_data:
                presets_data[game_name] = [
                    p for p in presets_data[game_name]
                    if p.get('name') != preset_name
                ]
                
                with open(presets_file, 'w') as f:
                    json.dump(presets_data, f, indent=2)
                logger.info(f"[PRESET-MANAGER] Deleted user preset '{preset_name}' for {game_name}")
        except Exception as e:
            logger.error(f"[PRESET-MANAGER] Failed to delete preset: {e}")

    def load_user_presets_for_game(self, game_name: str) -> None:
        """Load user presets from storage for a specific game.
        
        Call this to refresh user presets after they've been modified.
        """
        collection = self._collections.get(game_name)
        if not collection:
            logger.warning(f"[PRESET-MANAGER] No collection for game: {game_name}")
            return
        
        count = self._load_user_presets_for_collection(game_name, collection)
        if count > 0:
            logger.info(f"[PRESET-MANAGER] Reloaded {count} user preset(s) for {game_name}")

    def _get_user_presets_path(self) -> Path:
        """Get path to user presets JSON file."""
        return Path(user_path()) / "custom_worlds" / "preset_manager" / "presets.json"

    def validate_preset(self, world_cls: Type[World], preset: Preset) -> tuple[bool, List[str]]:
        """Validate a preset against a World's options.
        
        Args:
            world_cls: World class to validate against
            preset: Preset to validate
            
        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        errors = []
        
        try:
            options_dataclass = getattr(world_cls, 'options_dataclass', None)
            if not options_dataclass or not hasattr(options_dataclass, 'type_hints'):
                # Can't validate, assume okay
                return True, []
            
            type_hints = options_dataclass.type_hints
            
            for option_key, preset_value in preset.options.items():
                if option_key not in type_hints:
                    errors.append(f"Unknown option: {option_key}")
                else:
                    option_type = type_hints[option_key]
                    # Basic validation: check if option exists
                    # More detailed validation would require instantiating the option
                    if not hasattr(option_type, 'default'):
                        errors.append(f"Invalid option type: {option_key}")
            
            return len(errors) == 0, errors
        except Exception as e:
            logger.debug(f"[PRESET-MANAGER] Validation error for {world_cls.game}: {e}")
            return False, [str(e)]


# Create singleton instance
preset_manager = PresetManager()
