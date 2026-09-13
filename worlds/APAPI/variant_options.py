from __future__ import annotations

"""Generic multi-shape option base for APAPI consumers.

Archipelago YAML rolling calls ``Option.from_any(raw)`` with the raw YAML
value, so an option can accept several shapes (scalar, list, or dict) as
long as it validates them. Worlds define their *own* concrete options
(e.g. Mystery Game's maps in ``worlds/mystery_game/options.py``); this
module only provides the shared base. Generate.py already tolerates these:
unknown shapes raise OptionError, missing keys fall back to ``default``.
"""

from typing import Any

from Options import Option


class VariantOption(Option[Any]):
    """Accept any of several shapes; subclasses define ``verify``."""

    default: Any = None

    def __init__(self, value: Any) -> None:
        self.value = value

    @classmethod
    def from_any(cls, data: Any) -> "VariantOption":
        return cls(data)

    @classmethod
    def get_option_name(cls, value: Any) -> str:
        return str(value)


__all__ = ["VariantOption"]
