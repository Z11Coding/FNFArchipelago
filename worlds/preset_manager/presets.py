"""Built-in presets for games.

This module defines default presets that can be extended by adding entries to the dicts below.
"""

from typing import Dict, Any

# Format: {game_name: {preset_name: {option_key: value}}}
# This dict can be populated with built-in presets that will be loaded automatically.
# Example:
# BUILTIN_PRESETS = {
#     "Bomb Rush Cyberfunk": {
#         "Easy": {
#             "difficulty": 0,
#             "skip_intro": True,
#         },
#         "Hard": {
#             "difficulty": 2,
#             "skip_intro": False,
#         },
#     }
# }

BUILTIN_PRESETS: Dict[str, Dict[str, Dict[str, Any]]] = {
    # Add built-in presets here
}
