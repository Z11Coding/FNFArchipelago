from __future__ import annotations

import importlib
import importlib.util
import sys
from typing import Any, Callable

from .running import is_module_available, is_module_running, get_running_module


def patch_running_module(name: str, attr: str, wrapper: Callable[[Callable], Callable]) -> bool:
    mod = get_running_module(name)
    if mod is None:
        return False
    orig = getattr(mod, attr, None)
    if not callable(orig) or getattr(orig, "_apapi_patched", False):
        return False
    wrapped = wrapper(orig)
    setattr(mod, attr, wrapped)
    wrapped._apapi_patched = True  # type: ignore
    return True


def patch_available_module(name: str, attr: str, wrapper: Callable[[Callable], Callable]) -> bool:
    if not is_module_available(name):
        return False
    if is_module_running(name):
        return patch_running_module(name, attr, wrapper)
    try:
        from .hard_patch import hard_patches
        hard_patches.add_wrapper(f"{name}.{attr}", wrapper, load_missing=True)
        return True
    except Exception:
        return False


def ensure_patched(name: str, attr: str, wrapper: Callable[[Callable], Callable]) -> bool:
    if patch_running_module(name, attr, wrapper):
        return True
    return patch_available_module(name, attr, wrapper)
