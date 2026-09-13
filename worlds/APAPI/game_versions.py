from __future__ import annotations

"""Version-aware helpers for APAPI consumers.

Custom worlds evolve outside this repo (e.g. TUNIC has newer versions
elsewhere). These helpers let add-on worlds gate behavior on the loaded
world's version without importing that world directly.
"""

from typing import Any

from worlds.AutoWorld import AutoWorldRegister
from Utils import Version


def get_world_version(game: str) -> Version | None:
    """Return the loaded world's ``world_version``, or None if unknown."""
    world_type = AutoWorldRegister.world_types.get(game)
    if world_type is None:
        return None
    version = getattr(world_type, "world_version", None)
    if isinstance(version, Version):
        return version
    try:
        return Version(*version) if isinstance(version, (tuple, list)) else None
    except Exception:
        return None


def check_world_version(
    game: str,
    min_version: str | tuple[int, int, int] | Version | None = None,
    max_version: str | tuple[int, int, int] | Version | None = None,
) -> bool:
    """True if the loaded ``game`` world version is within [min, max]."""

    def _coerce(value: Any) -> Version | None:
        if value is None:
            return None
        if isinstance(value, Version):
            return value
        if isinstance(value, (tuple, list)):
            return Version(*value)
        if isinstance(value, str):
            parts = [int(p) for p in value.split(".")]
            while len(parts) < 3:
                parts.append(0)
            return Version(*parts[:3])
        raise TypeError(f"Unsupported version spec: {value!r}")

    current = get_world_version(game)
    if current is None:
        return False
    low, high = _coerce(min_version), _coerce(max_version)
    if low is not None and current < low:
        return False
    if high is not None and current > high:
        return False
    return True


def is_game_loaded(game: str) -> bool:
    return game in AutoWorldRegister.world_types


__all__ = ["check_world_version", "get_world_version", "is_game_loaded"]
