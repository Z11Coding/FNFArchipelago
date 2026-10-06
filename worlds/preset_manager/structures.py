"""Data structures for preset management."""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger("PresetManager")


@dataclass(frozen=True)
class Preset:
    """Immutable preset definition.
    
    Attributes:
        name: Display name of the preset
        description: Human-readable description
        options: Dict mapping option_key (internal name) to preset values
                 Values can be: simple types (int, str, bool), or weighted dicts for Choice options
                 Example: {"difficulty": 1, "mode": "hard", "randomization": {"option_1": 50, "option_2": 50}}
    """
    name: str
    description: str
    options: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Validate that options is a dict
        if not isinstance(self.options, dict):
            raise ValueError(f"Preset options must be a dict, got {type(self.options)}")


class PresetCollection:
    """Manages presets for a single game."""

    def __init__(self, game_name: str):
        self.game_name = game_name
        self._presets: Dict[str, Preset] = {}
        # Auto-generate default preset (will be populated when adding presets)
        self._default_preset_options: Dict[str, Any] = {}

    def add_preset(self, preset: Preset, overwrite_warning: bool = True) -> None:
        """Add a preset to the collection.
        
        If a preset with the same name exists, warn and overwrite.
        
        Args:
            preset: Preset object to add
            overwrite_warning: If True, log warning on duplicate name
        """
        if preset.name in self._presets and overwrite_warning:
            logger.warning(
                f"[PRESET-MANAGER] Duplicate preset name '{preset.name}' for game '{self.game_name}'. "
                f"Newest preset overrides previous one."
            )
        self._presets[preset.name] = preset

    def set_default_options(self, options: Dict[str, Any]) -> None:
        """Set the default option values for auto-generating the 'default' preset.
        
        Called after discovering all presets to generate a 'default' preset.
        """
        self._default_preset_options = options

    def _build_default_preset(self) -> Preset:
        """Build the default preset from World option defaults."""
        return Preset(
            name="default",
            description="Default options for this game",
            options=self._default_preset_options.copy()
        )

    def get_preset(self, name: str) -> Optional[Preset]:
        """Get a preset by name.
        
        Special case: "default" is always available, even if not explicitly added.
        """
        if name == "default":
            return self._build_default_preset()
        return self._presets.get(name)

    def get_all_presets(self) -> List[Preset]:
        """Get all presets including the auto-generated 'default'."""
        presets = [self._build_default_preset()]  # Always first
        presets.extend(sorted(self._presets.values(), key=lambda p: p.name))
        return presets

    def to_yaml_for_export(self, player_name: str) -> Dict[str, Any]:
        """Create a complete YAML export dict for a preset.
        
        Args:
            player_name: Name to use in the YAML
            
        Returns:
            Dict with keys: name, description, game, requires, <game_name>
        """
        return {
            "name": player_name,
            "description": f"Generated from Archipelago Preset Manager",
            "game": self.game_name,
            "requires": {},  # Version will be added by caller if needed
            self.game_name: {}  # Options will be populated by caller
        }

    def __repr__(self):
        return f"PresetCollection({self.game_name}, {len(self._presets)} presets)"
