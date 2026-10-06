from __future__ import annotations

"""Game Addons pack (NOT a world — adds no slot of its own).

Everything injection-related (waiting for games to load, patching, option
value plumbing) is handled exclusively by APAPI's injection API. This
package only declares *what* to add, so new add-ons are two calls:

1. :func:`worlds.APAPI.inject_option` — injects the setting so it acts
   native to the target game's own options (YAML template included).
2. :func:`worlds.APAPI.inject_world_behavior` — injects the behavior check
   into the target world itself.
"""

from worlds.APAPI import inject_option, inject_world_behavior

from .options import GRASS_ACTUAL_FILLER_KEY, GrassActualFiller
from .tunic_patch import after_tunic_create_item

# 1. The setting, native to TUNIC.
inject_option(
    GRASS_ACTUAL_FILLER_KEY,
    GrassActualFiller,
    games=["TUNIC"],
    group_name="Game Addons",
)

# 2. The behavior check, inside TunicWorld.create_item (the choke point all
# Grass flows through, including the local-fill path that skips the pool).
# Uses sync_existing so already-created TUNIC worlds (e.g., via midgen) get the patch immediately.
inject_world_behavior(
    "TUNIC",
    "create_item",
    after=after_tunic_create_item,
    min_version=(4, 0, 0),
    sync_existing=True,
)

# 3. Options Creator YAML import button (APAPI hard_patch → direct fallback).
#    No core edits: the patch injects an "Import YAML" button next to Export,
#    validates the chosen YAML, switches to its game, and syncs widgets.
#    Skipped entirely during generation (Generate/Main) — no GUI needed.
#    Uploader (end-of-generation confirmation) is explicitly allowed.
try:
    from worlds.APAPI.launch_context import should_skip_gui_patch
    _skip_yaml_import = should_skip_gui_patch()
except Exception:
    _skip_yaml_import = False
if not _skip_yaml_import:
    try:
        from .options_creator_yaml_import import init_yaml_import_patch
        init_yaml_import_patch()
    except Exception as _e:
        import logging as _logging
        _logging.getLogger("APAPI.GameAddons").debug(
            "YAML import patch not installed: %s", _e, exc_info=True
        )
else:
    import logging as _logging
    _logging.getLogger("APAPI.GameAddons").info(
        "Skipping YAML import button patch during generation (no GUI)"
    )

__all__ = ["GRASS_ACTUAL_FILLER_KEY", "GrassActualFiller", "after_tunic_create_item"]
