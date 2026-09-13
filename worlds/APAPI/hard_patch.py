from __future__ import annotations

from collections.abc import Callable
import functools
import importlib
import sys
from typing import Any, Dict, List, Tuple

from .nested_hooks import wrap_runtime_local_function


Wrapper = Callable[[Callable[..., Any], Any], Any]


def resolve_dotted_target(target_path: str, load_missing: bool = True) -> tuple[object, str, Callable[..., Any]]:
    """
    Resolve a dotted target path (e.g. Main.main, BaseClasses.MultiWorld.__init__).

    Returns (owner, attribute_name, current_callable).
    """
    parts = target_path.split(".")
    if len(parts) < 2:
        raise ValueError(f"Invalid target path: {target_path}")

    module = None
    module_end = 0
    for i in range(len(parts), 0, -1):
        module_name = ".".join(parts[:i])
        if load_missing:
            try:
                module = importlib.import_module(module_name)
                module_end = i
                break
            except Exception:
                continue
        else:
            module = sys.modules.get(module_name)
            if module is not None:
                module_end = i
                break

    if module is None:
        raise ImportError(f"Could not import module from target path: {target_path}")

    owner: object = module
    attrs = parts[module_end:]
    if not attrs:
        raise ValueError(f"Target path must include an attribute: {target_path}")

    for attr_name in attrs[:-1]:
        owner = getattr(owner, attr_name)

    attribute_name = attrs[-1]
    current = getattr(owner, attribute_name)
    if not callable(current):
        raise TypeError(f"Target is not callable: {target_path}")
    return owner, attribute_name, current


class HardPatchRegistry:
    """Central wrapper-based patch registry for hard-patching callables."""

    def __init__(self) -> None:
        self._originals: Dict[str, Callable[..., Any]] = {}
        self._wrappers: Dict[str, List[Callable[..., Any]]] = {}
        self._before_hooks: Dict[str, List[Callable[..., Any]]] = {}
        self._after_hooks: Dict[str, List[Callable[..., Any]]] = {}
        self._targets: Dict[str, Tuple[object, str]] = {}

    def add_wrapper(self, target_path: str, wrapper: Callable[..., Any], load_missing: bool = True) -> None:
        owner, attribute_name, current = resolve_dotted_target(target_path, load_missing=load_missing)

        if target_path not in self._originals:
            self._originals[target_path] = current
            self._targets[target_path] = (owner, attribute_name)
            self._wrappers[target_path] = []
            self._before_hooks[target_path] = []
            self._after_hooks[target_path] = []

        self._wrappers[target_path].append(wrapper)
        rebuilt = self._build_callable(target_path)
        setattr(owner, attribute_name, rebuilt)

    def add_before(self, target_path: str, callback: Callable[..., Any], load_missing: bool = True) -> None:
        """Register a hard patch callback that runs before the target callable executes."""
        owner, attribute_name, current = resolve_dotted_target(target_path, load_missing=load_missing)

        if target_path not in self._originals:
            self._originals[target_path] = current
            self._targets[target_path] = (owner, attribute_name)
            self._wrappers[target_path] = []
            self._before_hooks[target_path] = []
            self._after_hooks[target_path] = []

        self._before_hooks[target_path].append(callback)
        rebuilt = self._build_callable(target_path)
        setattr(owner, attribute_name, rebuilt)

    def add_after(self, target_path: str, callback: Callable[..., Any], load_missing: bool = True) -> None:
        """Register a hard patch callback that runs after the target callable executes."""
        owner, attribute_name, current = resolve_dotted_target(target_path, load_missing=load_missing)

        if target_path not in self._originals:
            self._originals[target_path] = current
            self._targets[target_path] = (owner, attribute_name)
            self._wrappers[target_path] = []
            self._before_hooks[target_path] = []
            self._after_hooks[target_path] = []

        self._after_hooks[target_path].append(callback)
        rebuilt = self._build_callable(target_path)
        setattr(owner, attribute_name, rebuilt)

    def _build_callable(self, target_path: str) -> Callable[..., Any]:
        original = self._originals[target_path]
        wrappers = list(self._wrappers[target_path])
        before_hooks = list(self._before_hooks.get(target_path, []))
        after_hooks = list(self._after_hooks.get(target_path, []))

        @functools.wraps(original)
        def call_chain(*args: Any, **kwargs: Any) -> Any:
            def invoke_base(*inner_args: Any, **inner_kwargs: Any) -> Any:
                for before_hook in before_hooks:
                    before_hook(*inner_args, **inner_kwargs)

                result = original(*inner_args, **inner_kwargs)

                for after_hook in after_hooks:
                    updated = after_hook(result, *inner_args, **inner_kwargs)
                    if updated is not None:
                        result = updated

                return result

            def invoke(index: int, *inner_args: Any, **inner_kwargs: Any) -> Any:
                if index >= len(wrappers):
                    return invoke_base(*inner_args, **inner_kwargs)

                def next_callable(*next_args: Any, **next_kwargs: Any) -> Any:
                    return invoke(index + 1, *next_args, **next_kwargs)

                return wrappers[index](next_callable, *inner_args, **inner_kwargs)

            return invoke(0, *args, **kwargs)

        return call_chain

    def get_original(self, target_path: str) -> Callable[..., Any] | None:
        return self._originals.get(target_path)

    def unpatch(self, target_path: str) -> bool:
        if target_path not in self._originals:
            return False
        owner, attribute_name = self._targets[target_path]
        setattr(owner, attribute_name, self._originals[target_path])
        self._originals.pop(target_path, None)
        self._wrappers.pop(target_path, None)
        self._before_hooks.pop(target_path, None)
        self._after_hooks.pop(target_path, None)
        self._targets.pop(target_path, None)
        return True

    def list_targets(self) -> list[str]:
        return sorted(self._wrappers)


hard_patches = HardPatchRegistry()


def register_before_patch(target_path: str, callback: Callable[..., Any], load_missing: bool = True) -> None:
    hard_patches.add_before(target_path, callback, load_missing=load_missing)


def register_after_patch(target_path: str, callback: Callable[..., Any], load_missing: bool = True) -> None:
    hard_patches.add_after(target_path, callback, load_missing=load_missing)


def register_scoped_local_wrapper(
    target_path: str,
    local_name: str,
    local_wrapper_factory: Callable[[Callable[..., Any]], Callable[..., Any]],
    load_missing: bool = True,
) -> None:
    """
    Hard-patch a scoped local function declared inside a target function.

    Example target/local pair: Main.main / write_multidata
    """

    def scoped_wrapper(next_callable: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        patched_outer = wrap_runtime_local_function(next_callable, local_name, local_wrapper_factory)
        return patched_outer(*args, **kwargs)

    hard_patches.add_wrapper(target_path, scoped_wrapper, load_missing=load_missing)
