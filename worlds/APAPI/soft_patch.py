from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import inspect
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union, get_type_hints


T = TypeVar("T")
ReturnAsType = Union[Type[list], Type[dict]]


def _is_mapping_type(tp: type) -> bool:
    try:
        return issubclass(tp, Mapping)
    except TypeError:
        return False


def _is_sequence_type(tp: type) -> bool:
    try:
        return issubclass(tp, Sequence)
    except TypeError:
        return False


class FuncStack(list, Generic[T]):
    """A function stack that can collect results and enforce return types."""

    def __init__(self, return_as: ReturnAsType = list, global_return_type: Optional[type] = None) -> None:
        super().__init__()
        if not (_is_sequence_type(return_as) or _is_mapping_type(return_as)):
            raise TypeError(
                "return_as must be a Sequence or Mapping type (list, dict, etc.), "
                f"got {return_as}"
            )
        self.return_as = return_as
        self.global_return_type = global_return_type
        self.func_type_constraints: Dict[Callable, Optional[type]] = {}

    def _extract_return_type(self, func: Callable) -> Optional[type]:
        try:
            hints = get_type_hints(func)
            return_type = hints.get("return")
            if return_type is not None and return_type is not type(None):
                return return_type
        except Exception:
            pass
        return None

    def push(self, func: Callable, return_type: Optional[type] = None) -> None:
        self.append(func)
        if return_type is not None:
            self.func_type_constraints[func] = return_type
        else:
            self.func_type_constraints[func] = self._extract_return_type(func)

    def pop(self) -> Optional[Callable]:
        if self:
            func = super().pop()
            self.func_type_constraints.pop(func, None)
            return func
        return None

    def __call__(self, *args: Any, **kwargs: Any) -> Union[List[Any], Dict[str, Any]]:
        is_mapping = _is_mapping_type(self.return_as)
        results = {} if is_mapping else []

        for i, func in enumerate(self):
            result = func(*args, **kwargs)
            expected_type = self.func_type_constraints.get(func) or self.global_return_type
            if expected_type and not isinstance(result, expected_type):
                func_name = getattr(func, "__name__", f"func_{i}")
                raise TypeError(
                    f"Function {func_name} returned {type(result).__name__}, "
                    f"expected {expected_type.__name__}"
                )

            if is_mapping:
                func_name = getattr(func, "__name__", f"func_{i}")
                results[func_name] = result
            else:
                results.append(result)

        return results

    def as_generator(self, *args: Any, **kwargs: Any) -> Any:
        for i, func in enumerate(self.copy()):
            result = func(*args, **kwargs)
            expected_type = self.func_type_constraints.get(func) or self.global_return_type
            if expected_type and not isinstance(result, expected_type):
                func_name = getattr(func, "__name__", f"func_{i}")
                raise TypeError(
                    f"Function {func_name} returned {type(result).__name__}, "
                    f"expected {expected_type.__name__}"
                )
            yield result

    def combine_to_single_function(self) -> Callable:
        functions_copy = list(self).copy()
        constraints_copy = dict(self.func_type_constraints).copy()
        return_as_type = self.return_as
        global_type = self.global_return_type

        def combined(*args: Any, **kwargs: Any) -> Union[List[Any], Dict[str, Any]]:
            is_mapping = _is_mapping_type(return_as_type)
            results = {} if is_mapping else []

            for i, func in enumerate(functions_copy):
                result = func(*args, **kwargs)
                expected_type = constraints_copy.get(func) or global_type
                if expected_type and not isinstance(result, expected_type):
                    func_name = getattr(func, "__name__", f"func_{i}")
                    raise TypeError(
                        f"Function {func_name} returned {type(result).__name__}, "
                        f"expected {expected_type.__name__}"
                    )

                if is_mapping:
                    func_name = getattr(func, "__name__", f"func_{i}")
                    results[func_name] = result
                else:
                    results.append(result)

            return results

        return combined


def _required_call_from_signature(signature: inspect.Signature) -> tuple[list[Any], dict[str, Any]]:
    sentinel = object()
    args: list[Any] = []
    kwargs: dict[str, Any] = {}

    for parameter in signature.parameters.values():
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            if parameter.default is inspect.Parameter.empty:
                args.append(sentinel)
        elif parameter.kind == inspect.Parameter.KEYWORD_ONLY:
            if parameter.default is inspect.Parameter.empty:
                kwargs[parameter.name] = sentinel

    return args, kwargs


def validate_hook_signature(target: Callable[..., Any], hook: Callable[..., Any]) -> None:
    """Validate that hook can be called with the target's required arguments."""
    target_sig = inspect.signature(target)
    hook_sig = inspect.signature(hook)
    args, kwargs = _required_call_from_signature(target_sig)
    try:
        hook_sig.bind(*args, **kwargs)
    except TypeError as exc:
        raise TypeError(
            f"Hook {getattr(hook, '__qualname__', repr(hook))} is not compatible with "
            f"target {getattr(target, '__qualname__', repr(target))}: {exc}"
        ) from exc


class SoftHookPoint:
    """A named soft hook point with before/after function stacks."""

    def __init__(
        self,
        name: str,
        target: Callable[..., Any],
        before_return_type: Optional[type] = None,
        after_return_type: Optional[type] = None,
    ) -> None:
        self.name = name
        self.target = target
        self.before = FuncStack(return_as=list, global_return_type=before_return_type)
        self.after = FuncStack(return_as=list, global_return_type=after_return_type)

    def register_before(self, hook: Callable[..., Any]) -> None:
        validate_hook_signature(self.target, hook)
        self.before.push(hook)

    def register_after(self, hook: Callable[..., Any]) -> None:
        validate_hook_signature(self.target, hook)
        self.after.push(hook)


class SoftHookRegistry:
    def __init__(self) -> None:
        self._points: dict[str, SoftHookPoint] = {}

    def ensure_point(
        self,
        name: str,
        target: Callable[..., Any],
        before_return_type: Optional[type] = None,
        after_return_type: Optional[type] = None,
    ) -> SoftHookPoint:
        point = self._points.get(name)
        if point is None:
            point = SoftHookPoint(
                name=name,
                target=target,
                before_return_type=before_return_type,
                after_return_type=after_return_type,
            )
            self._points[name] = point
        else:
            point.target = target
            if before_return_type is not None:
                point.before.global_return_type = before_return_type
            if after_return_type is not None:
                point.after.global_return_type = after_return_type
        return point

    def register_before(self, name: str, hook: Callable[..., Any]) -> None:
        point = self._points.get(name)
        if point is None:
            raise KeyError(f"Soft hook point {name} is not registered.")
        point.register_before(hook)

    def register_after(self, name: str, hook: Callable[..., Any]) -> None:
        point = self._points.get(name)
        if point is None:
            raise KeyError(f"Soft hook point {name} is not registered.")
        point.register_after(hook)

    def run_before(self, name: str, *args: Any, **kwargs: Any) -> List[Any]:
        point = self._points.get(name)
        if point is None:
            return []
        return point.before(*args, **kwargs)

    def run_after(self, name: str, *args: Any, **kwargs: Any) -> List[Any]:
        point = self._points.get(name)
        if point is None:
            return []
        return point.after(*args, **kwargs)

    def list_points(self) -> list[str]:
        return sorted(self._points)


soft_hooks = SoftHookRegistry()
