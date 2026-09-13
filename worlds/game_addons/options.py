from __future__ import annotations

"""Option classes injected into other games by game_addons.

These are NOT a world of their own: :mod:`worlds.game_addons` injects them
into the target game's own options (e.g. TUNIC) after world loading
completes, so they appear in that game's YAML template and behave like
native options of that game.
"""

from Options import Toggle


class GrassActualFiller(Toggle):
    """Make grass have actual filler.

    When enabled on a TUNIC slot with Grass Randomizer on, most of that
    slot's "Grass" filler is replaced with real TUNIC filler items (money,
    berries, bombs, ...), keeping Grass only as a chance instead of filling
    the whole pool.
    """
    internal_name = "grass_actual_filler"
    display_name = "Make Grass Have Actual Filler"
    default = False


#: Options-dataclass field key used when injecting into TUNIC.
GRASS_ACTUAL_FILLER_KEY: str = "grass_actual_filler"
