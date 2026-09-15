from __future__ import annotations

"""Generation stage tracking via AutoWorld call wrappers."""

from collections.abc import Callable
import functools
import logging
import time
from typing import Any

from .debug import dprint, dump_hook_stats
from .hard_patch import hard_patches

logger = logging.getLogger("APAPI")

KNOWN_STAGES = [
    "assert_generate",
    "generate_early",
    "create_regions",
    "create_items",
    "set_rules",
    "connect_entrances",
    "generate_basic",
    "pre_fill",
    "post_fill",
    "generate_output",
    "fill_slot_data",
    "extend_hint_information",
    "modify_multidata",
]

StageCallback = Callable[..., None]

_current_stage: str | None = None
_stage_listeners: dict[str, list[StageCallback]] = {}
_patched = False


def get_current_stage(default: str | None = None) -> str | None:
    """Input: default. Returns: current stage or default."""
    return _current_stage if _current_stage is not None else default


def on_stage(stage: str, callback: StageCallback) -> None:
    """Input: stage, callback. Returns: None (registers listener)."""
    _stage_listeners.setdefault(stage, []).append(callback)
    dprint("stages", f"listener registered for stage '{stage}'")


def _notify_stage(stage: str, multiworld: Any, *args: Any) -> None:
    """Input: stage, multiworld, args. Returns: None (fires listeners)."""
    for callback in list(_stage_listeners.get(stage, [])):
        try:
            callback(multiworld, *args)
        except Exception as exc:
            logger.warning("APAPI stage listener for %s failed: %s", stage, exc)


def _wrap_call_all(next_callable: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Input: next_callable, args. Returns: result (tracks stage)."""
    global _current_stage
    method_name = args[1] if len(args) >= 2 else kwargs.get("method_name")
    multiworld = args[0] if args else kwargs.get("multiworld")
    previous = _current_stage
    if isinstance(method_name, str):
        _current_stage = method_name
        if multiworld is not None:
            _notify_stage(method_name, multiworld, *args[2:], **kwargs)
    start: float = time.perf_counter()
    if isinstance(method_name, str):
        dprint("stages", f"stage '{method_name}' begun")
    try:
        return next_callable(*args, **kwargs)
    finally:
        if isinstance(method_name, str):
            elapsed: float = time.perf_counter() - start
            dprint("stages", f"stage '{method_name}' finished in {elapsed:.4f}s")
            if method_name == "generate_output":
                dump_hook_stats()
        _current_stage = previous


def _wrap_call_single(next_callable: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Input: next_callable, args. Returns: result (tracks stage)."""
    global _current_stage
    method_name = args[1] if len(args) >= 2 else kwargs.get("method_name")
    previous = _current_stage
    if isinstance(method_name, str):
        _current_stage = method_name
    try:
        return next_callable(*args, **kwargs)
    finally:
        _current_stage = previous


def initialize_stage_tracking() -> None:
    """Input: None. Returns: None (installs wrappers, idempotent)."""
    global _patched
    if _patched:
        dprint("init", "stage tracking already initialized")
        return
    try:
        hard_patches.add_wrapper("worlds.AutoWorld.call_all", _wrap_call_all, load_missing=False)
        hard_patches.add_wrapper("worlds.AutoWorld.call_single", _wrap_call_single, load_missing=False)
        dprint("init", "stage tracking initialized")
    except Exception as exc:
        dprint("init", f"stage tracking deferred ({exc})")
        try:
            hard_patches.add_wrapper("worlds.AutoWorld.call_all", _wrap_call_all, load_missing=True)
            hard_patches.add_wrapper("worlds.AutoWorld.call_single", _wrap_call_single, load_missing=True)
            dprint("init", "stage tracking initialized (lazy)")
        except Exception as exc2:
            logger.warning("APAPI stage tracking could not install: %s", exc2)
            return
    _patched = True


__all__ = [
    "KNOWN_STAGES",
    "StageCallback",
    "get_current_stage",
    "initialize_stage_tracking",
    "on_stage",
]
