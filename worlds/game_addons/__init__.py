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
inject_world_behavior(
    "TUNIC",
    "create_item",
    after=after_tunic_create_item,
    min_version=(4, 0, 0),
)

__all__ = ["GRASS_ACTUAL_FILLER_KEY", "GrassActualFiller", "after_tunic_create_item"]
