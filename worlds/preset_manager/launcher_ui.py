"""Launcher UI for Preset Manager."""

import logging
from kvui import ScrollBox, MainLayout, MDLabel, MDBoxLayout, dp, ToggleButton
from kivymd.uix.button import MDButton, MDButtonText

from worlds.AutoWorld import AutoWorldRegister, World
from .preset_manager import preset_manager
from .structures import Preset

logger = logging.getLogger("PresetManager")


def main_ui(world_path):
    """Main UI entry point for Preset Manager Launcher component.
    
    Args:
        world_path: Path to the preset_manager world (provided by launcher)
    """
    from kvui import ThemedApp
    
    class PresetManagerApp(ThemedApp):
        """Launcher app for managing and applying presets."""
        
        base_title = "Archipelago Preset Manager"
        
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.current_game = None
            self.current_preset = None
        
        def build(self):
            """Build the preset manager UI."""
            self.set_colors()
            
            main_layout = MainLayout(cols=1, orientation="tb-lr", padding=dp(10), spacing=dp(10))
            
            # Title
            title = MDLabel(text="Preset Manager", size_hint_y=None, height=dp(40))
            main_layout.add_widget(title)
            
            # Game selector section
            game_section = MDBoxLayout(orientation="vertical", size_hint_y=None, height=dp(200), spacing=dp(5))
            game_section.add_widget(MDLabel(text="Select a Game:", size_hint_y=None, height=dp(30)))
            
            game_scroll = ScrollBox()
            
            def on_game_selected(game_btn):
                """Handle game button click."""
                self.current_game = game_btn.game_name
                # Update preset selector
                self._update_preset_selector(main_layout)
            
            # Create game buttons
            for game_name in sorted(preset_manager.get_all_games()):
                game_btn = ToggleButton(
                    MDButtonText(text=game_name),
                    size_hint_y=None,
                    height=dp(50)
                )
                game_btn.game_name = game_name
                game_btn.bind(on_release=on_game_selected)
                game_scroll.layout.add_widget(game_btn)
            
            game_section.add_widget(game_scroll)
            main_layout.add_widget(game_section)
            
            # Preset selector section (will be updated when game is selected)
            self.preset_section = MDBoxLayout(orientation="vertical", size_hint_y=None, height=dp(200), spacing=dp(5))
            self.preset_section.add_widget(MDLabel(text="Select a Preset:", size_hint_y=None, height=dp(30)))
            self.preset_scroll = ScrollBox()
            self.preset_section.add_widget(self.preset_scroll)
            main_layout.add_widget(self.preset_section)
            
            # Action buttons
            buttons_layout = MDBoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
            
            apply_btn = MDButton(
                MDButtonText(text="Apply Preset"),
                on_release=self._on_apply_preset
            )
            buttons_layout.add_widget(apply_btn)
            
            close_btn = MDButton(
                MDButtonText(text="Close"),
                on_release=lambda x: self.stop()
            )
            buttons_layout.add_widget(close_btn)
            
            main_layout.add_widget(buttons_layout)
            
            return main_layout
        
        def _update_preset_selector(self, main_layout):
            """Update preset selector after game selection."""
            if not self.current_game:
                return
            
            # Clear and rebuild preset scroll
            self.preset_scroll.layout.clear_widgets()
            
            collection = preset_manager.get_presets(self.current_game)
            if not collection:
                return
            
            def on_preset_selected(preset_btn):
                """Handle preset button click."""
                self.current_preset = preset_btn.preset
            
            # Create preset buttons
            for preset in collection.get_all_presets():
                preset_btn = ToggleButton(
                    MDButtonText(text=f"{preset.name} - {preset.description[:30]}..." if preset.description else preset.name),
                    size_hint_y=None,
                    height=dp(50)
                )
                preset_btn.preset = preset
                preset_btn.bind(on_release=on_preset_selected)
                self.preset_scroll.layout.add_widget(preset_btn)
        
        def _on_apply_preset(self, button):
            """Handle apply preset button click - generates and saves YAML."""
            if not self.current_game:
                logger.warning("[PRESET-MANAGER] No game selected")
                return
            
            if not self.current_preset:
                logger.warning("[PRESET-MANAGER] No preset selected")
                return
            
            # Validate preset
            world_cls = AutoWorldRegister.world_types.get(self.current_game)
            if not world_cls:
                logger.error(f"[PRESET-MANAGER] Unknown game: {self.current_game}")
                return
            
            is_valid, errors = preset_manager.validate_preset(world_cls, self.current_preset)
            if errors:
                logger.warning(f"[PRESET-MANAGER] Preset validation warnings: {errors}")
            
            # Generate YAML structure
            import Utils
            from pathlib import Path
            import threading
            
            def save_yaml():
                """Background thread to save YAML file."""
                try:
                    # Create YAML structure
                    yaml_data = {
                        "name": f"{self.current_preset.name}_{self.current_game}",
                        "description": self.current_preset.description or f"Preset: {self.current_preset.name}",
                        "game": self.current_game,
                        self.current_game: self.current_preset.options.copy()
                    }
                    
                    # Get default save location (Players folder)
                    default_filename = Utils.get_file_safe_name(f"{self.current_preset.name}.yaml")
                    
                    # Show save dialog
                    try:
                        file_path = Utils.save_filename(
                            "Save Preset YAML As...",
                            [("YAML", [".yaml"])],
                            default_filename
                        )
                    except Exception:
                        logger.error("[PRESET-MANAGER] Could not open save dialog")
                        return
                    
                    if not file_path:
                        logger.info("[PRESET-MANAGER] Save cancelled by user")
                        return
                    
                    # Save YAML file
                    with open(file_path, 'w') as f:
                        f.write(Utils.dump(yaml_data, sort_keys=False))
                    
                    logger.info(f"[PRESET-MANAGER] Preset saved to {file_path}")
                except Exception as e:
                    logger.error(f"[PRESET-MANAGER] Failed to save preset: {e}", exc_info=True)
            
            # Run in background thread to avoid blocking UI
            threading.Thread(target=save_yaml, daemon=True).start()
    
    app = PresetManagerApp()
    app.run()
