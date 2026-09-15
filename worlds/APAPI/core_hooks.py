from __future__ import annotations

"""Core hook registration and patching for APAPI."""

import logging
import threading
import time
from typing import Any, Callable

from .hard_patch import hard_patches, resolve_dotted_target
from .debug import dprint
from .soft_patch import soft_hooks


logger = logging.getLogger("APAPI")


CORE_HOOK_SPECS: dict[str, dict[str, Any]] = {
    "core.main": {
        "target": "Main.main",
        "before_return_type": type(None),
        "after_return_type": type(None),
    },
    "core.multiworld_init": {
        "target": "BaseClasses.MultiWorld.__init__",
        "before_return_type": type(None),
        "after_return_type": type(None),
    },
    "core.autoworld_call_single": {
        "target": "worlds.AutoWorld.call_single",
        "before_return_type": type(None),
        "after_return_type": type(None),
    },
    "core.autoworld_call_all": {
        "target": "worlds.AutoWorld.call_all",
        "before_return_type": type(None),
        "after_return_type": type(None),
    },
    "core.multiworld_get_spheres": {
        "target": "BaseClasses.MultiWorld.get_spheres",
        "before_return_type": type(None),
        "after_return_type": type(None),
    },
    "core.multiworld_get_sendable_spheres": {
        "target": "BaseClasses.MultiWorld.get_sendable_spheres",
        "before_return_type": type(None),
        "after_return_type": type(None),
    },
    "core.launcher_run_gui": {
        "target": "Launcher.run_gui",
        "before_return_type": type(None),
        "after_return_type": type(None),
    },
    "core.commonclient_default": {
        "target": "CommonClient.ClientCommandProcessor.default",
        "before_return_type": type(None),
        "after_return_type": type(None),
    },
}

CORE_HOOK_TARGETS: dict[str, str] = {name: spec["target"] for name, spec in CORE_HOOK_SPECS.items()}

_initialized = False
_worker_started = False
_patched_targets: set[str] = set()
_pending_before: dict[str, list[Callable[..., Any]]] = {}
_pending_after: dict[str, list[Callable[..., Any]]] = {}


def _make_soft_wrapper(hook_name: str) -> Callable[..., Any]:
    """Input: hook_name. Returns: wrapper callable."""
    def wrapper(next_callable: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        soft_hooks.run_before(hook_name, *args, **kwargs)
        result = next_callable(*args, **kwargs)
        soft_hooks.run_after(hook_name, *args, **kwargs)
        return result

    return wrapper


def initialize_core_hooks() -> None:
    """Input: None. Returns: None (installs core hooks)."""
    global _initialized
    global _worker_started

    if _initialized:
        dprint("init", "core hooks already initialized")
        return

    _patch_loaded_targets()
    dprint("init", f"core hooks initialized ({len(_patched_targets)}/{len(CORE_HOOK_SPECS)} targets patched)")
    if not _worker_started:
        worker = threading.Thread(target=_deferred_patch_worker, name="APAPI-PatchWorker", daemon=True)
        worker.start()
        _worker_started = True
        dprint("init", "deferred patch worker started")

    _initialized = True


def _patch_loaded_targets() -> None:
    """Input: None. Returns: None (patches loaded targets)."""
    for hook_name, spec in CORE_HOOK_SPECS.items():
        target_path = spec["target"]
        if target_path in _patched_targets:
            continue

        try:
            _, _, target = resolve_dotted_target(target_path, load_missing=False)
            soft_hooks.ensure_point(
                hook_name,
                target,
                before_return_type=spec.get("before_return_type"),
                after_return_type=spec.get("after_return_type"),
            )
            for callback in _pending_before.pop(hook_name, []):
                soft_hooks.register_before(hook_name, callback)
            for callback in _pending_after.pop(hook_name, []):
                soft_hooks.register_after(hook_name, callback)
            hard_patches.add_wrapper(target_path, _make_soft_wrapper(hook_name), load_missing=False)
            _patched_targets.add(target_path)
            dprint("hooks", f"core hook '{hook_name}' -> {target_path} patched successfully")
        except Exception:
            continue


def _deferred_patch_worker() -> None:
    """Input: None. Returns: None (retries patching in background)."""
    for _ in range(240):
        _patch_loaded_targets()
        if len(_patched_targets) == len(CORE_HOOK_SPECS):
            dprint("hooks", "all deferred core hook targets patched")
            return
        time.sleep(0.5)

    missing_targets = sorted({spec["target"] for spec in CORE_HOOK_SPECS.values()} - _patched_targets)
    if missing_targets:
        logger.warning("APAPI could not patch some deferred targets: %s", ", ".join(missing_targets))


def register_soft_before(hook_name: str, callback: Callable[..., Any]) -> None:
    """Input: hook_name, callback. Returns: None."""
    try:
        soft_hooks.register_before(hook_name, callback)
    except KeyError:
        if hook_name not in CORE_HOOK_TARGETS:
            raise
        _pending_before.setdefault(hook_name, []).append(callback)


def register_soft_after(hook_name: str, callback: Callable[..., Any]) -> None:
    """Input: hook_name, callback. Returns: None."""
    try:
        soft_hooks.register_after(hook_name, callback)
    except KeyError:
        if hook_name not in CORE_HOOK_TARGETS:
            raise
        _pending_after.setdefault(hook_name, []).append(callback)


def register_hard_wrapper(target_path: str, wrapper: Callable[..., Any]) -> None:
    """Input: target_path, wrapper. Returns: None."""
    hard_patches.add_wrapper(target_path, wrapper)


def list_core_hook_points() -> list[str]:
    """Returns: sorted hook point names."""
    return sorted(set(soft_hooks.list_points()) | set(CORE_HOOK_TARGETS))
