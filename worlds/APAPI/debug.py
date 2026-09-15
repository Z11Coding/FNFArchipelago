from __future__ import annotations

"""Debug printing and hook timing for APAPI."""

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("APAPI.Debug")

SLOW_HOOK_THRESHOLD: float = 1.0

_enabled: bool = True
_refcount_debug: bool = False
_stats_lock = threading.RLock()
_hook_stats: dict[tuple[str, str], dict[str, Any]] = {}
_host_synced: bool = False


def _sync_from_host_config() -> None:
    """Sync _enabled from host.yaml (apapi.debug.enabled, default True)."""
    global _enabled, _host_synced
    # Avoid repeated disk reads after first successful sync unless forced.
    if _host_synced:
        return
    try:
        from pathlib import Path
        import yaml
        from Utils import user_path

        path = Path(user_path("host.yaml"))
        if not path.exists():
            _host_synced = True
            return
        with path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
        if not isinstance(data, dict):
            _host_synced = True
            return
        apapi_cfg = data.get("apapi", {})
        if not isinstance(apapi_cfg, dict):
            _host_synced = True
            return
        dbg_cfg = apapi_cfg.get("debug", None)
        enabled: Any = None
        if isinstance(dbg_cfg, dict):
            enabled = dbg_cfg.get("enabled", None)
        elif isinstance(dbg_cfg, bool):
            enabled = dbg_cfg
        if enabled is None:
            # legacy flat keys
            for _k in ("debug_messages", "enable_debug", "debug_enabled"):
                if _k in apapi_cfg:
                    enabled = apapi_cfg[_k]
                    break
        if enabled is not None:
            _enabled = bool(enabled)
        _host_synced = True
    except Exception:
        # Fail open (keep current _enabled, which defaults to True).
        _host_synced = True


def is_debug_enabled() -> bool:
    """Returns: True if debug printing is on (host.yaml apapi.debug.enabled, default True)."""
    # Lazily sync once so early imports honor host.yaml without requiring explicit init.
    if not _host_synced:
        _sync_from_host_config()
    return _enabled


def set_debug_enabled(enabled: bool) -> None:
    """Input: enabled flag. Returns: None (also marks host-synced so host file won't override)."""
    global _enabled, _host_synced
    _enabled = bool(enabled)
    _host_synced = True


def is_refcount_debug_enabled() -> bool:
    """Returns: True if refcount tracing is on."""
    return _refcount_debug


def set_refcount_debug_enabled(enabled: bool) -> None:
    """Input: enabled flag. Returns: None."""
    global _refcount_debug
    _refcount_debug = bool(enabled)


def dprint(tag: str, message: str) -> None:
    """Input: tag, message. Returns: None (logs if enabled via apapi.debug.enabled)."""
    if is_debug_enabled():
        logger.info("[APAPI:%s] %s", tag, message)


def record_hook_time(game: str, method: str, elapsed: float) -> None:
    """Input: game, method, elapsed. Returns: None (records timing)."""
    with _stats_lock:
        entry = _hook_stats.setdefault((game, method), {"calls": 0, "total": 0.0, "max": 0.0})
        entry["calls"] += 1
        entry["total"] += elapsed
        entry["max"] = max(entry["max"], elapsed)
    if elapsed > SLOW_HOOK_THRESHOLD:
        dprint("timing", f"{game}.{method} finished in {elapsed:.4f}s")
    if elapsed > SLOW_HOOK_THRESHOLD:
        logger.warning("[APAPI:timing] SLOW hook %s.%s took %.4fs (threshold %.1fs)",
                       game, method, elapsed, SLOW_HOOK_THRESHOLD)


@contextmanager
def hook_timer(game: str, method: str) -> Iterator[None]:
    """Input: game, method. Returns: context manager that times block."""
    start: float = time.perf_counter()
    try:
        yield
    finally:
        record_hook_time(game, method, time.perf_counter() - start)


def get_hook_stats() -> dict[tuple[str, str], dict[str, Any]]:
    """Returns: copy of per-hook timing stats."""
    with _stats_lock:
        return {key: dict(value) for key, value in _hook_stats.items()}


def dump_hook_stats() -> None:
    """Input: None. Returns: None (logs summary)."""
    stats: dict[tuple[str, str], dict[str, Any]] = get_hook_stats()
    if not stats:
        logger.info("[APAPI:timing] No hook executions recorded.")
        return
    logger.info("[APAPI:timing] Hook timing summary:")
    for (game, method), entry in sorted(stats.items()):
        calls: int = entry["calls"]
        total: float = entry["total"]
        logger.info("[APAPI:timing]   %s.%s: %d call(s), total %.4fs, avg %.4fs, max %.4fs",
                    game, method, calls, total, total / max(calls, 1), entry["max"])


def _referrer_owner(container: Any) -> str:
    """Input: container. Returns: owner label string."""
    import gc
    import types
    for parent in gc.get_referrers(container):
        if isinstance(parent, types.FrameType):
            continue
        if isinstance(parent, types.ModuleType) and parent.__dict__ is container:
            return f"module {parent.__name__} globals"
        if isinstance(parent, type):
            return f"class {parent.__name__}"
        obj_dict: Any = getattr(parent, "__dict__", None)
        if obj_dict is container and not isinstance(parent, type):
            return f"{type(parent).__name__} instance"
    return "unknown owner"


def dump_referrer_report(obj: Any, label: str = "object",
                         max_depth: int = 3, max_nodes: int = 40) -> None:
    """Input: obj, label, max_depth, max_nodes. Returns: None (logs referrers)."""
    import gc
    import types
    gc.collect()
    seen: set[int] = {id(obj)}
    lines: list[str] = []

    def describe(ref: Any) -> str:
        if isinstance(ref, types.ModuleType):
            return f"module {ref.__name__}"
        if isinstance(ref, dict):
            keys: list[str] = [str(key) for key in list(ref)[:5] if isinstance(key, str)]
            return f"dict of {_referrer_owner(ref)} keys={keys} len={len(ref)}"
        if isinstance(ref, (list, tuple)):
            return f"{type(ref).__name__} len={len(ref)}"
        if isinstance(ref, set):
            return f"set len={len(ref)}"
        if isinstance(ref, types.FrameType):
            return f"frame {ref.f_code.co_name}"
        detail: str = ""
        for attr in ("__name__", "game"):
            try:
                value: Any = getattr(ref, attr, None)
                if isinstance(value, str):
                    detail = f" {attr}={value!r}"
                    break
            except Exception:
                pass
        return f"{type(ref).__name__}{detail}"

    def visit(target: Any, depth: int) -> None:
        if depth > max_depth or len(lines) >= max_nodes:
            return
        for ref in gc.get_referrers(target):
            if id(ref) in seen or ref is lines or isinstance(ref, types.FrameType):
                continue
            seen.add(id(ref))
            lines.append("  " * depth + describe(ref))
            if depth < max_depth and isinstance(ref, (dict, list, tuple, set)):
                visit(ref, depth + 1)

    visit(obj, 0)
    logger.info("[APAPI:leak] referrers of %s (depth %d):", label, max_depth)
    for line in lines:
        logger.info("[APAPI:leak] %s", line)


__all__ = [
    "SLOW_HOOK_THRESHOLD",
    "dprint",
    "dump_hook_stats",
    "dump_referrer_report",
    "get_hook_stats",
    "hook_timer",
    "is_debug_enabled",
    "is_refcount_debug_enabled",
    "record_hook_time",
    "set_debug_enabled",
    "set_refcount_debug_enabled",
]
