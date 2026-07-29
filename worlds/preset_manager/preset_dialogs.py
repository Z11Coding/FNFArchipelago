"""Kivy dialogs for preset selection and management in OptionsCreator."""

import logging
from typing import Callable, Optional, TYPE_CHECKING

from kvui import dp, MDBoxLayout, MDLabel, ResizableTextField
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText

if TYPE_CHECKING:
    from OptionsCreator import OptionsCreator

from .preset_manager import preset_manager
from .structures import Preset

logger = logging.getLogger("PresetManager")


def open_preset_selector_dialog(options_creator: 'OptionsCreator', game_name: str) -> None:
    """Open a modal dialog to select and apply a preset.
    
    Dialog flow:
    1. Select game (if not already selected)
    2. Select preset from list
    3. Preview changes
    4. Apply or cancel
    
    Args:
        options_creator: OptionsCreator instance
        game_name: Current game name to show presets for
    """
    try:
        collection = preset_manager.get_presets(game_name)
        if not collection:
            MDSnackbar(
                MDSnackbarText(text=f"No presets available for {game_name}"),
                y=dp(24),
                pos_hint={"center_x": 0.5},
                size_hint_x=0.5
            ).open()
            return
        
        # Get all presets
        presets = collection.get_all_presets()
        
        # Create dropdown menu items
        preset_items = []
        for preset in presets:
            preset_items.append({
                "text": f"{preset.name} - {preset.description[:50]}..." if preset.description else preset.name,
                "on_release": lambda p=preset: _on_preset_selected(options_creator, game_name, p)
            })
        
        # Create the main dialog
        dialog_content = MDBoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint_y=None,
            height=dp(200)
        )
        
        dialog_content.add_widget(
            MDLabel(text=f"Select a preset for {game_name}", size_hint_y=None, height=dp(30))
        )
        
        # Preset selector button
        preset_button = MDButton(
            MDButtonText(text="Choose Preset..."),
            size_hint_y=None,
            height=dp(50)
        )
        dialog_content.add_widget(preset_button)
        
        # Dropdown menu
        dropdown = MDDropdownMenu(caller=preset_button, items=preset_items)
        preset_button.bind(on_release=dropdown.open)
        
        # Create dialog
        dialog = MDDialog(
            title="Apply Preset",
            content=dialog_content,
            buttons=[
                MDButton(MDButtonText(text="Cancel"), on_release=lambda: dialog.dismiss())
            ]
        )
        
        dialog.open()
        
    except Exception as e:
        logger.error(f"[PRESET-MANAGER] Failed to open preset selector: {e}", exc_info=True)
        MDSnackbar(
            MDSnackbarText(text="Error opening preset selector"),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.5
        ).open()


def _on_preset_selected(options_creator: 'OptionsCreator', game_name: str, preset: Preset) -> None:
    """Handle preset selection.
    
    Shows a preview dialog before applying.
    """
    try:
        # Create preview dialog
        preview_content = MDBoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint_y=None,
            height=dp(300)
        )
        
        # Preset info
        preview_content.add_widget(
            MDLabel(
                text=f"Preset: {preset.name}",
                size_hint_y=None,
                height=dp(30)
            )
        )
        
        if preset.description:
            preview_content.add_widget(
                MDLabel(
                    text=preset.description,
                    size_hint_y=None,
                    height=dp(40)
                )
            )
        
        # Show options that will be changed
        options_text = "Options that will be applied:\n"
        for key, value in preset.options.items():
            options_text += f"  {key}: {value}\n"
        
        preview_content.add_widget(
            MDLabel(
                text=options_text,
                size_hint_y=None,
                height=dp(150)
            )
        )
        
        # Buttons: Apply or Cancel
        def apply_action():
            from .options_hook import apply_preset_to_options_creator
            apply_preset_to_options_creator(options_creator, preset)
            dialog.dismiss()
            MDSnackbar(
                MDSnackbarText(text=f"Applied preset '{preset.name}'"),
                y=dp(24),
                pos_hint={"center_x": 0.5},
                size_hint_x=0.5
            ).open()
        
        dialog = MDDialog(
            title=f"Apply Preset: {preset.name}",
            content=preview_content,
            buttons=[
                MDButton(MDButtonText(text="Cancel"), on_release=lambda: dialog.dismiss()),
                MDButton(MDButtonText(text="Apply"), on_release=apply_action)
            ]
        )
        
        dialog.open()
        
    except Exception as e:
        logger.error(f"[PRESET-MANAGER] Error in preset selection: {e}", exc_info=True)
        MDSnackbar(
            MDSnackbarText(text="Error applying preset"),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.5
        ).open()
