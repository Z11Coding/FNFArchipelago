from __future__ import annotations

import importlib.util
import sys
from typing import Any


def is_module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def is_module_running(name: str) -> bool:
    return name in sys.modules


def get_running_module(name: str) -> Any | None:
    return sys.modules.get(name)

def all_running_modules() -> list[str]:
    return list(sys.modules.keys())

def debug_running_modules() -> None:
    for name in all_running_modules():
        print(name)

def kill_running_module(name: str) -> None:
    if name in sys.modules:
        del sys.modules[name]
        importlib.invalidate_caches()
        print(f"Module {name} has been killed.")
        sys.modules.pop(name, None)
    else:
        print(f"Module {name} is not running. It could not be killed.")

