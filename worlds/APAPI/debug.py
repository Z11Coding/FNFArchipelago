from __future__ import annotations

"""APAPI debug printer + hook timing.

Enabled by default. Disable with ``APAPI_DEBUG=0`` or ``set_debug_enabled(False)``.

Covers init events, hook success/failure, and stage begin/finish. Hook
finishes log only past the slow threshold (like AutoWorld._timed_call);
totals come from dump_hook_stats.
"""

import logging
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("APAPI.Debug")

#: Hooks slower than this (seconds) get a warning, mirroring AutoWorld._timed_call.
SLOW_HOOK_THRESHOLD: float = 1.0

_enabled: bool = os.environ.get("APAPI_DEBUG", "1") != "0"
_stats_lock = threading.RLock()
#: (game, method) -> {"calls": int, "total": float, "max": float}
_hook_stats: dict[tuple[str, str], dict[str, Any]] = {}


def is_debug_enabled() -> bool:
    """Return whether the APAPI debug printer is on."""
    return _enabled


def set_debug_enabled(enabled: bool) -> None:
    """Enable or disable the APAPI debug printer at runtime."""
    global _enabled
    _enabled = bool(enabled)


def dprint(tag: str, message: str) -> None:
    """Print a debug line (``[APAPI:<tag>] <message>``) when debugging is on."""
    if _enabled:
        logger.info("[APAPI:%s] %s", tag, message)


def record_hook_time(game: str, method: str, elapsed: float) -> None:
    """Record one hook execution; log only over-threshold finishes.

    Per-call lines are threshold-gated (high-frequency hooks like
    create_item would otherwise flood the log); the full table comes from
    :func:`dump_hook_stats`.
    """
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
    """Time a hook body and record it via :func:`record_hook_time`."""
    start: float = time.perf_counter()
    try:
        yield
    finally:
        record_hook_time(game, method, time.perf_counter() - start)


def get_hook_stats() -> dict[tuple[str, str], dict[str, Any]]:
    """Return a copy of the collected per-hook timing stats."""
    with _stats_lock:
        return {key: dict(value) for key, value in _hook_stats.items()}


def dump_hook_stats() -> None:
    """Log a summary table of hook timings (always logs, even if debug is off)."""
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
    """Best-effort owner label for a container holding a live object."""
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
    """Log what keeps ``obj`` alive (leak hunts; always logs when called).

    Walks ``gc.get_referrers`` a few levels, skipping frames and this
    report's own bookkeeping. Run with ``APAPI_REFCOUNT_DEBUG=1`` wired by
    callers (off by default: zero overhead otherwise).
    """
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
    "record_hook_time",
    "set_debug_enabled",
]
