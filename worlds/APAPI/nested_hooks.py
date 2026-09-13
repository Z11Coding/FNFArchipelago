from __future__ import annotations

from collections.abc import Callable
import functools
import logging
import sys
from typing import Any


logger = logging.getLogger("APAPI")


def wrap_runtime_local_function(
    outer_function: Callable[..., Any],
    local_name: str,
    wrapper_factory: Callable[[Callable[..., Any]], Callable[..., Any]],
) -> Callable[..., Any]:
    """
    Experimental helper for patching a lexical local function at runtime.

    This is best-effort only. Python may not propagate writes to frame locals in all contexts.
    """

    @functools.wraps(outer_function)
    def wrapped_outer(*args: Any, **kwargs: Any) -> Any:
        previous_trace = sys.gettrace()
        patched_once = False

        def tracer(frame: Any, event: str, arg: Any) -> Any:
            nonlocal patched_once
            if patched_once or frame.f_code is not outer_function.__code__:
                return tracer

            if event in ("line", "call"):
                candidate = frame.f_locals.get(local_name)
                if callable(candidate) and not getattr(candidate, "__apapi_patched_local__", False):
                    wrapped_local = wrapper_factory(candidate)
                    setattr(wrapped_local, "__apapi_patched_local__", True)
                    frame.f_locals[local_name] = wrapped_local
                    patched_once = True

            return tracer

        sys.settrace(tracer)
        try:
            result = outer_function(*args, **kwargs)
        finally:
            sys.settrace(previous_trace)

        if not patched_once:
            logger.warning(
                "APAPI nested hook did not capture local function '%s' inside %s. "
                "This path is experimental and may require a different outer hook point.",
                local_name,
                getattr(outer_function, "__qualname__", repr(outer_function)),
            )
        return result

    return wrapped_outer
