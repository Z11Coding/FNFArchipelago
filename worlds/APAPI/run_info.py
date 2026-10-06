from __future__ import annotations

"""Run-state capture for spoiler/output flags."""

import logging
import sys
import threading
import time
from typing import Any

from .debug import dprint
from .hard_patch import hard_patches

logger = logging.getLogger("APAPI.RunInfo")

_lock = threading.RLock()
_worker_started = False
_captured: dict[str, Any] | None = None


def _capture_wrapper(next_callable: Any, *args: Any, **kwargs: Any) -> Any:
    """Input: next_callable, args. Returns: result (captures flags)."""
    global _captured
    raw_args: Any = args[0] if args else kwargs.get("args")
    try:
        with _lock:
            _captured = {
                "spoiler": int(getattr(raw_args, "spoiler", 0) or 0),
                "skip_output": bool(getattr(raw_args, "skip_output", False)),
                "spoiler_only": bool(getattr(raw_args, "spoiler_only", False)),
            }
        dprint("init", f"captured run flags {_captured}")
    except Exception as exc:
        logger.warning("[APAPI:runinfo] could not capture Main args: %s", exc)
    return next_callable(*args, **kwargs)


def _install_deferred() -> None:
    """Input: None. Returns: None (installs wrapper when Main loads)."""
    for _ in range(240):
        if "Main" in sys.modules:
            try:
                hard_patches.add_wrapper("Main.main", _capture_wrapper, load_missing=False)
                dprint("init", "Main.main args capture installed")
            except Exception as exc:
                logger.warning("[APAPI:runinfo] could not wrap Main.main: %s", exc)
            return
        time.sleep(0.5)
    dprint("init", "Main.main args capture skipped (Main never loaded)")


def ensure_run_info() -> None:
    """Input: None. Returns: None (starts worker, idempotent)."""
    global _worker_started
    if _worker_started:
        return
    worker = threading.Thread(target=_install_deferred, name="APAPI-RunInfo", daemon=True)
    worker.start()
    _worker_started = True


def get_run_flags() -> dict[str, Any] | None:
    """Returns: captured flags or None."""
    ensure_run_info()
    with _lock:
        return dict(_captured) if _captured is not None else None


def get_spoiler_level() -> int | None:
    """Returns: spoiler level or None."""
    flags: dict[str, Any] | None = get_run_flags()
    return int(flags["spoiler"]) if flags is not None else None


def is_output_enabled() -> bool | None:
    """Returns: False if skipped, True if enabled, None if unknown."""
    flags: dict[str, Any] | None = get_run_flags()
    if flags is None:
        return None
    return not (flags["skip_output"] or flags["spoiler_only"])


__all__ = ["ensure_run_info", "get_run_flags", "get_spoiler_level", "is_output_enabled"]
