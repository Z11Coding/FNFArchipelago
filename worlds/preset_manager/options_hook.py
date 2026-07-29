"""Hook to integrate Preset Manager into OptionsCreator."""

import logging
from typing import TYPE_CHECKING

from kvui import dp, MDButton, MDButtonText, MDLabel, MDBoxLayout

if TYPE_CHECKING:
    from OptionsCreator import OptionsCreator

logger = logging.getLogger("PresetManager")


def patch_options_creator() -> None:
    """Patch OptionsCreator to add Preset Manager integration.
    
    This function patches the OptionsCreator class to:
    1. Add a "Presets" button to the toolbar
    2. Hook into the build() method to initialize preset functionality
    
    Should be called at import time before OptionsCreator is instantiated.
    """
    try:
        from OptionsCreator import OptionsCreator
        from .preset_dialogs import open_preset_selector_dialog
        
        # Store original build method
        original_build = OptionsCreator.build
        
        def patched_build(self):
            """Patched build method that adds Presets button."""
            # Call original build
            container = original_build(self)
            
            # Add Presets button to the player options toolbar (top area)
            try:
                # The main_layout has a top section with Export button, add Presets next to it
                if hasattr(self, 'main_layout') and hasattr(self.main_layout, 'children'):
                    # Find the button layout (where Export button is)
                    for child in self.main_layout.children:
                        if isinstance(child, MDBoxLayout):
                            # Check if this contains the export button area
                            for subchild in child.children:
                                if (isinstance(subchild, MDButton) and 
                                    hasattr(subchild, 'children') and 
                                    any(isinstance(c, MDButtonText) and c.text == "Export" for c in subchild.children)):
                                    # Found export button, add presets button after it
                                    preset_button = MDButton(
                                        MDButtonText(text="Presets"),
                                        on_release=lambda btn: self._on_presets_clicked(),
                                        size_hint_x=None,
                                        width=dp(100),
                                    )
                                    child.add_widget(preset_button)
                                    logger.info("[PRESET-MANAGER] Added Presets button to OptionsCreator")
                                    break
            except Exception as e:
                logger.warning(f"[PRESET-MANAGER] Could not add Presets button to toolbar: {e}")
            
            return container
        
        def on_presets_clicked(self):
            """Handle Presets button click."""
            if not self.current_game or self.current_game == "None":
                from kvui import MDSnackbar, MDSnackbarText
                MDSnackbar(
                    MDSnackbarText(text="Please select a game first"),
                    y=dp(24),
                    pos_hint={"center_x": 0.5},
                    size_hint_x=0.5
                ).open()
                return
            
            # Open preset selector dialog
            open_preset_selector_dialog(self, self.current_game)
        
        # Patch the methods
        OptionsCreator.build = patched_build
        OptionsCreator._on_presets_clicked = on_presets_clicked
        
        logger.info("[PRESET-MANAGER] Successfully patched OptionsCreator")
        
    except Exception as e:
        logger.error(f"[PRESET-MANAGER] Failed to patch OptionsCreator: {e}", exc_info=True)


def apply_preset_to_options_creator(options_creator: 'OptionsCreator', preset) -> None:
    """Apply a preset's options to the OptionsCreator instance.
    
    Args:
        options_creator: OptionsCreator instance to apply preset to
        preset: Preset object with options to apply
    """
    from .preset_manager import preset_manager
    from worlds.AutoWorld import AutoWorldRegister
    
    try:
        # Get the world class for current game
        world_cls = AutoWorldRegister.world_types.get(options_creator.current_game)
        if not world_cls:
            logger.error(f"[PRESET-MANAGER] Unknown game: {options_creator.current_game}")
            return
        
        # Validate preset
        is_valid, errors = preset_manager.validate_preset(world_cls, preset)
        if not is_valid:
            logger.warning(f"[PRESET-MANAGER] Preset validation errors: {errors}")
        
        # Apply each option from the preset
        for option_key, preset_value in preset.options.items():
            if option_key in options_creator.options:
                options_creator.options[option_key] = preset_value
                logger.debug(f"[PRESET-MANAGER] Applied {option_key} = {preset_value}")
            else:
                logger.warning(f"[PRESET-MANAGER] Option {option_key} not found in current game options")
        
        logger.info(f"[PRESET-MANAGER] Applied preset '{preset.name}' to {options_creator.current_game}")
        
    except Exception as e:
        logger.error(f"[PRESET-MANAGER] Failed to apply preset: {e}", exc_info=True)
