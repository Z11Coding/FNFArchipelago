from __future__ import annotations

"""Compatibility shims for worlds written against older cores.

Each shim translates a removed core API to current equivalents (old
functionality mimicked on top of the new stuff). Shims live behind
MultiWorld.__getattr__, so they only run when something actually touches
the missing attribute: worlds that don't need them are completely
unaffected. Every shim logs once when it fires.

Toggle: host.yaml `apapi.compat.enabled` (default true).
"""

import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger("APAPI.Compat")

_fired: set[str] = set()
_installed = False
_forced: bool | None = None


def set_compat_enabled(enabled: bool | None) -> None:
    """Force compat on/off (None = follow host.yaml). Returns: None."""
    global _forced
    _forced = None if enabled is None else bool(enabled)


def _compat_enabled() -> bool:
    """Returns: True unless disabled via set_compat_enabled/host.yaml."""
    if _forced is not None:
        return _forced
    try:
        from .host_config import get_host_config
        value = get_host_config("apapi.compat.enabled", True)
        if isinstance(value, str):
            return value.strip().lower() not in ("0", "false", "no", "off")
        return bool(value)
    except Exception:
        return True


def _plando_items_compat(multiworld: Any) -> Dict[int, List[Dict[str, Any]]]:
    """Mimic pre-rewrite multiworld.plando_items ({pid: [block dicts]}).

    Removed in the Plando Rewrite; current data lives in
    multiworld.plando_item_blocks as PlandoItemBlock dataclasses. Old block
    dicts carried singular/plural item/location keys, from_pool/force/world/
    count/player: all are reproduced here so legacy readers keep working.
    Fresh containers are built per access so legacy in-place mutation (the
    old fill code did block['player'] = player) cannot corrupt live state.
    """
    blocks_by_player = getattr(multiworld, "plando_item_blocks", {}) or {}
    try:
        player_ids = list(getattr(multiworld, "player_ids", []) or [])
    except Exception:
        player_ids = []
    out: Dict[int, List[Dict[str, Any]]] = {}
    for pid in player_ids if player_ids else list(blocks_by_player):
        translated: List[Dict[str, Any]] = []
        for block in blocks_by_player.get(pid, []):
            items = list(getattr(block, "items", []) or [])
            locations = list(getattr(block, "locations", []) or [])
            try:
                worlds = set(getattr(block, "worlds", set()) or set())
            except Exception:
                worlds = set()
            try:
                count = dict(getattr(block, "count", {}) or {})
            except Exception:
                count = {}
            translated.append({
                "player": getattr(block, "player", pid),
                "items": items,
                "item": list(items),
                "locations": locations,
                "location": list(locations),
                "from_pool": bool(getattr(block, "from_pool", True)),
                "force": getattr(block, "force", "silent"),
                "world": worlds,
                "count": count,
            })
        out[pid] = translated
    return out


_COMPAT_ATTRS: Dict[str, Callable[[Any], Any]] = {
    "plando_items": _plando_items_compat,
}


def _multiworld_getattr(self: Any, name: str) -> Any:
    handler = _COMPAT_ATTRS.get(name)
    if handler is None or not _compat_enabled():
        raise AttributeError(f"{type(self).__name__} object has no attribute {name!r}")
    try:
        value = handler(self)
    except AttributeError:
        raise
    except Exception as exc:
        raise AttributeError(f"compat shim for {name!r} failed: {exc}") from exc
    if name not in _fired:
        _fired.add(name)
        logger.info(f"[APAPI:compat] serving legacy MultiWorld.{name} (translated to current APIs)")
    return value


def install_compat() -> None:
    """Input: None. Returns: None (installs the MultiWorld compat fallback once)."""
    global _installed
    if _installed:
        return
    try:
        from BaseClasses import MultiWorld
    except Exception:
        return
    try:
        prev = getattr(MultiWorld, "__getattr__", None)
        if getattr(prev, "_apapi_compat", False):
            _installed = True
            return

        if prev is not None:
            def _chained(self: Any, name: str, _prev: Any = prev) -> Any:
                try:
                    return _prev(self, name)
                except AttributeError:
                    return _multiworld_getattr(self, name)

            _chained._apapi_compat = True  # type: ignore
            MultiWorld.__getattr__ = _chained  # type: ignore
        else:
            _multiworld_getattr._apapi_compat = True  # type: ignore
            MultiWorld.__getattr__ = _multiworld_getattr  # type: ignore
    except Exception:
        return
    _installed = True


__all__ = [
    "install_compat",
    "set_compat_enabled",
]
