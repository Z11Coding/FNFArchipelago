from __future__ import annotations

"""TUNIC-side behavior for the game_addons grass option.

Pure behavior only: no waiting, no patching, no version checks — APAPI's
injection API owns all of that. This module just answers "what should
happen inside TUNIC's world when the option is on".

Installed via ``inject_world_behavior("TUNIC", "create_item", after=...)``.
``create_item`` is the choke point: EVERY Grass item (pool, local-fill,
pre-locked) is created through it, so a per-item chance here diversifies
all paths, including the 95% local-fill path that never sits in the pool.
"""

import logging
from typing import Any, TYPE_CHECKING

from worlds.APAPI.debug import dprint

if TYPE_CHECKING:
    from worlds.AutoWorld import World

from .options import GRASS_ACTUAL_FILLER_KEY

logger = logging.getLogger("APAPI.GameAddons")

#: Fraction of Grass to keep when the option is on; the rest becomes filler.
GRASS_KEEP_CHANCE: float = 0.15


def _pick_filler(tunic_world: "World") -> str | None:
    """A real TUNIC filler item name (never Grass), or None."""
    try:
        from worlds.tunic.items import filler_items as tunic_filler
        if tunic_filler:
            return tunic_world.random.choice(list(tunic_filler))
    except Exception:
        pass
    try:
        return tunic_world.get_filler_item_name()
    except Exception:
        return None


def _filler_enabled(tunic_world: "World") -> bool:
    try:
        options: Any = getattr(tunic_world, "options", None)
        return bool(getattr(options, GRASS_ACTUAL_FILLER_KEY, False)) and bool(
            getattr(options, "grass_randomizer", False))
    except Exception:
        return False


def after_tunic_create_item(result: Any, world: "World", name: str,
                            *args: Any, **kwargs: Any) -> Any:
    """After-hook for ``TunicWorld.create_item``: diversify Grass at creation."""
    if name != "Grass" or not _filler_enabled(world):
        return None
    if world.random.random() < GRASS_KEEP_CHANCE:
        return None
    filler_name: str | None = _pick_filler(world)
    if not filler_name or filler_name == "Grass":
        return None
    try:
        # Re-enters this hook, but filler names pass straight through.
        return world.create_item(filler_name)
    except Exception as exc:
        logger.warning("[GameAddons] Could not create %s: %s", filler_name, exc)
        return None


__all__ = ["GRASS_KEEP_CHANCE", "after_tunic_create_item"]
