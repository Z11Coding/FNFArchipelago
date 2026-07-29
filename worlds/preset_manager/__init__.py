"""Preset Manager - Utility APWorld for managing option presets."""

import logging
import sys

from worlds.LauncherComponents import Component, Type, components
from Utils import local_path

logger = logging.getLogger("PresetManager")

# Import preset manager to ensure it's initialized
try:
    from .preset_manager import preset_manager
    print(f"[PRESET-MANAGER] Initialized with {len(preset_manager.get_all_games())} games")
except Exception as e:
    print(f"[PRESET-MANAGER] Failed to initialize preset_manager: {e}")
    import traceback
    traceback.print_exc()
    preset_manager = None


# Attempt to patch OptionsCreator at module level
try:
    from .options_hook import patch_options_creator
    patch_options_creator()
    print("[PRESET-MANAGER] Successfully patched OptionsCreator")
except ImportError:
    print("[PRESET-MANAGER] options_hook module not available")
except Exception as e:
    print(f"[PRESET-MANAGER] Failed to patch OptionsCreator: {e}")
    import traceback
    traceback.print_exc()


# Register Launcher component
def _launcher_main(*args):
    """Launcher entry point for Preset Manager."""
    from worlds.LauncherComponents import launch
    from .launcher_ui import main_ui
    world_path = local_path("worlds/preset_manager")
    launch(main_ui, name="Preset Manager", args=(world_path,))

# Register as a Launcher tool component
components.append(
    Component(
        display_name="Preset Manager",
        func=_launcher_main,
        component_type=Type.TOOL,
        description="Manage and apply option presets for games",
        cli=False
    )
)

print("[PRESET-MANAGER] Preset Manager initialized successfully")


