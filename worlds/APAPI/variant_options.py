from __future__ import annotations

"""Base option type accepting multiple YAML shapes."""

from typing import Any

from Options import Option


class VariantOption(Option[Any]):
    """Input: any shape. Output: VariantOption with that value."""

    default: Any = None

    def __init__(self, value: Any) -> None:
        self.value = value

    @classmethod
    def from_any(cls, data: Any) -> "VariantOption":
        """Input: raw data. Returns: instance."""
        return cls(data)

    @classmethod
    def get_option_name(cls, value: Any) -> str:
        """Input: value. Returns: string name."""
        return str(value)


__all__ = ["VariantOption"]
