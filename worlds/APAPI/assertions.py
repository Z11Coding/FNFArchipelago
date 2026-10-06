from __future__ import annotations

"""APAPI assertion decorators — deferred failure aggregation.

This module provides decorators that can be added to wrapper functions
and other APAPI-specific functions to assert conditions. If an assertion
isn't met, execution continues until all patches/pre_gen functions and
load retries have settled; at generation start (first ``call_all`` stage)
an aggregated error is raised showing how many errors happened, what
games errored, and why with proper stack traces.

Assertion kinds:
* ``assert_no_error`` / ``assert_not_error`` — function completes without
  raising (swallows exception, records failure, continues).
* ``assert_returns`` — function returns (including ``None``) without raising
  (effectively same as no_error, but explicit return semantic).
* ``assert_returns_not_none`` / ``assert_not_none`` — function returns a
  non-``None`` value; ``None`` is treated as failure.

Other assertion types can be added via :func:`make_assertion_decorator`
or :func:`register_assertion_kind`.

Integration:
* Failures are stored thread-safely in ``_failures``.
* :func:`check_and_raise` is called automatically at generation start
  (see :mod:`worlds.APAPI.generation` ``_wrap_call_all``) after
  ``wait_for_all_patches`` has settled. It can also be called manually.

Typical usage::

    from worlds.APAPI import assert_no_error, assert_returns_not_none

    @assert_no_error(game="Example Game")
    @classmethod
    def pre_gen(cls, yamls, ctx, multiworld=None):
        ...

    @assert_returns_not_none(game="Example Game")
    def my_wrapper(next_callable, *args, **kwargs):
        result = next_callable(*args, **kwargs)
        return result
"""

import enum
import functools
import inspect
import threading
import traceback
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import logging

logger = logging.getLogger("APAPI.Assertions")


class AssertionKind(str, enum.Enum):
    NO_ERROR = "no_error"
    RETURNS = "returns"
    RETURNS_NOT_NONE = "returns_not_none"
    CUSTOM = "custom"


@dataclass
class AssertionFailure:
    game: str | None
    func: str
    kind: str
    message: str
    exception: BaseException | None = None
    traceback_str: str = ""
    return_value: Any = None
    timestamp: float = field(default_factory=time.time)

    def format(self, index: int) -> str:
        header = f"[{index}] game={self.game or 'unknown'} func={self.func} kind={self.kind}"
        details = f"  message: {self.message}"
        tb = ""
        if self.traceback_str:
            tb = f"\n  traceback:\n" + "\n".join("    " + line for line in self.traceback_str.splitlines())
        elif self.exception is not None:
            tb = f"\n  exception: {self.exception!r}"
        rv = ""
        if self.kind in (AssertionKind.RETURNS_NOT_NONE, "returns_not_none"):
            rv = f"\n  return_value: {self.return_value!r}"
        return f"{header}\n{details}{tb}{rv}"


_failures: list[AssertionFailure] = []
_lock = threading.RLock()
_has_raised: bool = False
# ensure we only raise once per generation attempt
_raise_stage: str | None = None


class APAPIAssertionAggregateError(RuntimeError):
    """Raised when one or more APAPI assertions failed.

    Contains all failures and a formatted report.
    """

    def __init__(self, failures: list[AssertionFailure], report: str):
        self.failures = list(failures)
        self.report = report
        # Build rich message
        games = sorted({f.game for f in failures if f.game})
        games_str = ", ".join(games) if games else "unknown"
        super().__init__(
            f"APAPI assertions failed: {len(failures)} error(s) in {len(games)} game(s) [{games_str}]\n{report}"
        )


def _infer_game_from_args(args: tuple[Any, ...], func: Callable[..., Any] | None = None) -> str | None:
    """Try to infer game name from first arg (cls/instance) or func qualname."""
    try:
        if args:
            # check cls / self with 'game' attribute
            first = args[0]
            # handle wrapper case where first is next_callable
            # need to check other args for world-like objects
            candidates = list(args)
            if func is not None:
                try:
                    # for wrappers, try to detect multiworld/world objects later args
                    pass
                except Exception:
                    pass
            for cand in candidates:
                try:
                    g = getattr(cand, "game", None)
                    if isinstance(g, str) and g:
                        return g
                    # class with .game
                    if hasattr(cand, "game") and isinstance(getattr(cand, "game"), str):
                        return getattr(cand, "game")
                except Exception:
                    continue
                try:
                    # check if cand is a class with game attr
                    if inspect.isclass(cand) and hasattr(cand, "game"):
                        gv = getattr(cand, "game")
                        if isinstance(gv, str):
                            return gv
                except Exception:
                    continue
            # also try first arg if it's a type
            try:
                if inspect.isclass(first) and hasattr(first, "game"):
                    gv = getattr(first, "game")
                    if isinstance(gv, str):
                        return gv
            except Exception:
                pass
    except Exception:
        pass
    # fallback: try func's module / qualname for hint
    try:
        if func is not None:
            qn = getattr(func, "__qualname__", "") or getattr(func, "__name__", "")
            # if qualname contains game hint, not reliable
            pass
    except Exception:
        pass
    return None


def record_failure(
    *,
    game: str | None,
    func: str,
    kind: str | AssertionKind,
    message: str,
    exception: BaseException | None = None,
    traceback_str: str | None = None,
    return_value: Any = None,
) -> AssertionFailure:
    """Record a failure thread-safely and return the record."""
    kind_str = kind.value if isinstance(kind, enum.Enum) else str(kind)
    if traceback_str is None and exception is not None:
        try:
            traceback_str = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        except Exception:
            traceback_str = f"{exception!r}"
    elif traceback_str is None:
        # capture current stack for non-exception failures (e.g., returns_not_none)
        try:
            traceback_str = "".join(traceback.format_stack(limit=12))
        except Exception:
            traceback_str = ""
    rec = AssertionFailure(
        game=game,
        func=func,
        kind=kind_str,
        message=message,
        exception=exception,
        traceback_str=traceback_str or "",
        return_value=return_value,
    )
    with _lock:
        _failures.append(rec)
    logger.warning("[APAPI:assert] %s failed for %s (%s): %s", kind_str, func, game or "unknown", message)
    if traceback_str:
        logger.debug("[APAPI:assert] traceback for %s:\n%s", func, traceback_str)
    return rec


def get_failures() -> list[AssertionFailure]:
    with _lock:
        return list(_failures)


def clear_failures() -> None:
    global _has_raised
    with _lock:
        _failures.clear()
        _has_raised = False


def get_failure_count() -> int:
    with _lock:
        return len(_failures)


def _is_fill_like(failure: AssertionFailure) -> bool:
    try:
        if failure.exception is not None and type(failure.exception).__name__ == "FillError":
            return True
    except Exception:
        pass
    try:
        msg = f"{failure.message} {failure.traceback_str}".lower()
        if "fillerror" in msg or "no more spots to place" in msg or "unplaced items" in msg:
            return True
    except Exception:
        pass
    return False


def format_fill_section_for_failure(failure: AssertionFailure) -> str:
    """Run the fill analyzer for a fill-like failure. Never raises."""
    try:
        pre_attached = getattr(failure.exception, "apapi_fill_diagnosis", None) if failure.exception is not None else None
        if isinstance(pre_attached, str) and pre_attached.strip():
            return pre_attached
    except Exception:
        pass
    try:
        from .fill_analyzer import diagnose_and_format, is_enabled
        if not is_enabled():
            return ""
        mw = None
        try:
            from .multiworld_api import get_current_multiworld
            mw = get_current_multiworld()
        except Exception:
            mw = None
        text = diagnose_and_format(mw, failure.exception)
        # cache on the exception so re-renders reuse it
        try:
            if failure.exception is not None and text:
                setattr(failure.exception, "apapi_fill_diagnosis", text)
        except Exception:
            pass
        return text
    except Exception as e:
        return f"(APAPI fill analyzer failed: {e})"


def report_fill_error(exc: BaseException, multiworld=None) -> str:
    """Analyze a FillError and show it via APAPI's own error-output channel.

    Runs the fill analyzer, attaches the text to ``exc`` as
    ``apapi_fill_diagnosis``, prints it in the same banner style as
    ``check_and_raise``, and returns the formatted text. Never raises.
    """
    try:
        from .fill_analyzer import diagnose_and_format, attach_diagnosis_to_exception, is_enabled
        text = ""
        try:
            if is_enabled():
                if multiworld is None:
                    try:
                        from .multiworld_api import get_current_multiworld
                        multiworld = get_current_multiworld()
                    except Exception:
                        multiworld = None
                text = diagnose_and_format(multiworld, exc)
        except Exception as e:
            text = f"(APAPI fill analyzer failed: {e})"
        try:
            attach_diagnosis_to_exception(exc, text)
        except Exception:
            pass
        if text:
            try:
                print("\n" + "=" * 78)
                print("[APAPI FILL ERROR] what is preventing the fill")
                print("=" * 78)
                print(text)
                print("=" * 78 + "\n")
            except Exception:
                pass
            try:
                logger.error("[APAPI:assert] fill diagnosis:\n%s", text)
            except Exception:
                pass
        return text
    except Exception:
        return ""


def format_report(failures: list[AssertionFailure] | None = None) -> str:
    if failures is None:
        failures = get_failures()
    if not failures:
        return "No APAPI assertion failures."
    lines: list[str] = []
    lines.append(f"APAPI assertions: {len(failures)} failure(s) across {len({f.game for f in failures if f.game})} game(s)")
    # group by game
    by_game: dict[str, list[AssertionFailure]] = {}
    for f in failures:
        key = f.game or "unknown"
        by_game.setdefault(key, []).append(f)
    lines.append(f"Games errored: {', '.join(sorted(by_game.keys()))}")
    lines.append("")
    for idx, failure in enumerate(failures, 1):
        lines.append(failure.format(idx))
        lines.append("")
        # If this failure looks like a fill failure, append the fill-analyzer
        # diagnosis inline so APAPI's own error output shows *why* the fill failed.
        try:
            if _is_fill_like(failure):
                section = format_fill_section_for_failure(failure)
                if section:
                    lines.append("  --- APAPI fill analyzer: what is preventing the fill ---")
                    lines.extend("  " + l for l in section.splitlines())
                    lines.append("")
        except Exception:
            pass
    return "\n".join(lines)


def check_and_raise(*, stage: str | None = None, clear_after: bool = False) -> None:
    """If any failures recorded, raise aggregated error.

    Intended to be called after patches/pre_gen and load retries have
    settled, at generation start. The generation gate waits first, then
    this raises.
    """
    global _has_raised, _raise_stage
    with _lock:
        if not _failures:
            return
        if _has_raised:
            # don't raise twice in same generation
            return
        # ensure patches settled before raising (short wait)
        try:
            from .generation_gate import wait_for_all_patches

            # quick poll; don't block long here because gate already waited
            wait_for_all_patches(timeout=2.0)
        except Exception:
            pass
        report = format_report(list(_failures))
        failures_copy = list(_failures)
        _has_raised = True
        _raise_stage = stage or "unknown"
        # log before raising
        logger.error("[APAPI:assert] raising aggregate error at stage %s: %s", _raise_stage, report)
        # print to stderr as well for visibility
        try:
            print("\n" + "=" * 78)
            print("[APAPI ASSERTION FAILURES]")
            print("=" * 78)
            print(report)
            print("=" * 78 + "\n")
        except Exception:
            pass
        err = APAPIAssertionAggregateError(failures_copy, report)
        # optionally attach first traceback as cause?
        raise err
    if clear_after:
        clear_failures()


def _decorator_factory(
    kind: AssertionKind | str,
    check_fn: Callable[[Any, BaseException | None, Any], tuple[bool, str | None]],
    *,
    default_message: str | None = None,
) -> Callable[..., Any]:
    """Create a decorator that records failure per check_fn.

    check_fn(result, exception, return_value) -> (passed, message_if_failed)
    For exception case, exception is not None and result is sentinel.
    """

    def make_decorator(_func: Callable[..., Any] | None = None, *, game: str | None = None, message: str | None = None):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            fname = getattr(func, "__qualname__", getattr(func, "__name__", str(func)))
            # preserve classmethod/staticmethod handling: if func is classmethod wrap underlying

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                inferred_game = game
                if inferred_game is None:
                    inferred_game = _infer_game_from_args(args, func)
                # try to also infer from kwargs for wrappers that pass multiworld
                if inferred_game is None:
                    for v in kwargs.values():
                        try:
                            g = getattr(v, "game", None)
                            if isinstance(g, str) and g:
                                inferred_game = g
                                break
                        except Exception:
                            continue
                # capture before call stack for later if needed
                try:
                    result = func(*args, **kwargs)
                    exc: BaseException | None = None
                except BaseException as e:  # noqa: BLE001
                    # assertion about no_error / returns will fail on exception
                    tb_str = traceback.format_exc()
                    # ask check_fn if this exception counts as failure
                    # For no_error kind, any exception is failure
                    passed, msg = check_fn(None, e, None)
                    if not passed:
                        fail_msg = message or msg or default_message or f"{kind} failed: {type(e).__name__}: {e}"
                        record_failure(
                            game=inferred_game,
                            func=fname,
                            kind=kind,
                            message=fail_msg,
                            exception=e,
                            traceback_str=tb_str,
                            return_value=None,
                        )
                    # swallow to allow continuation (deferred raise later)
                    # Return None to keep pipeline moving; caller may expect something but None is safe
                    return None
                else:
                    # no exception — check return value if needed
                    passed, msg = check_fn(result, None, result)
                    if not passed:
                        tb_str = "".join(traceback.format_stack(limit=10))
                        fail_msg = message or msg or default_message or f"{kind} failed: returned {result!r}"
                        record_failure(
                            game=inferred_game,
                            func=fname,
                            kind=kind,
                            message=fail_msg,
                            exception=None,
                            traceback_str=tb_str,
                            return_value=result,
                        )
                    return result

            # mark for introspection
            try:
                wrapper._apapi_assertion_kind = kind  # type: ignore[attr-defined]
                wrapper._apapi_assertion_game = game  # type: ignore[attr-defined]
            except Exception:
                pass
            return wrapper

        if _func is not None and callable(_func) and not isinstance(_func, (str,)):
            # used as @decorator without args
            return decorator(_func)  # type: ignore[return-value]
        return decorator

    return make_decorator


# Specific decorators

# 1. assert_no_error — fails if function raised
def _check_no_error(result: Any, exc: BaseException | None, return_value: Any) -> tuple[bool, str | None]:
    if exc is not None:
        return False, f"expected no error but got {type(exc).__name__}: {exc}"
    return True, None


assert_no_error = _decorator_factory(AssertionKind.NO_ERROR, _check_no_error, default_message="assert_no_error failed")
assert_not_error = assert_no_error
assert_no_exception = assert_no_error
assert_no_raise = assert_no_error

# alias for external distinct naming
def assert_not_ending_in_error(_func=None, *, game=None, message=None):
    return assert_no_error(_func, game=game, message=message) if _func is not None else assert_no_error(game=game, message=message)

# 2. assert_returns — fails if raised (allows None return)
def _check_returns(result: Any, exc: BaseException | None, return_value: Any) -> tuple[bool, str | None]:
    if exc is not None:
        return False, f"expected return (including None) but raised {type(exc).__name__}: {exc}"
    # in Python everything returns, so if we got here we succeeded
    return True, None


assert_returns = _decorator_factory(AssertionKind.RETURNS, _check_returns, default_message="assert_returns failed")
assert_return = assert_returns
assert_has_return = assert_returns
# allow usage as @assert_returns_not_none? separate


# 3. assert_returns_not_none — fails if raised or returned None
def _check_returns_not_none(result: Any, exc: BaseException | None, return_value: Any) -> tuple[bool, str | None]:
    if exc is not None:
        return False, f"expected non-None return but raised {type(exc).__name__}: {exc}"
    if result is None:
        return False, "expected non-None return but got None"
    return True, None


assert_returns_not_none = _decorator_factory(
    AssertionKind.RETURNS_NOT_NONE, _check_returns_not_none, default_message="assert_returns_not_none failed"
)
assert_not_none = assert_returns_not_none
assert_returns_value = assert_returns_not_none
assert_has_non_none_return = assert_returns_not_none


# Generic helper for future kinds
def make_assertion_decorator(
    kind: str,
    predicate: Callable[[Any, BaseException | None], bool],
    failure_message: str | Callable[[Any, BaseException | None], str] | None = None,
) -> Callable[..., Any]:
    """Create a custom assertion decorator.

    predicate(result, exception) -> True if passed.
    For success, exception is None; for exception case, result is None.
    """

    def _check(result: Any, exc: BaseException | None, return_value: Any) -> tuple[bool, str | None]:
        try:
            ok = predicate(result if exc is None else None, exc)
        except BaseException as e:  # noqa: BLE001
            return False, f"predicate error: {e}"
        if ok:
            return True, None
        try:
            msg = failure_message(result if exc is None else None, exc) if callable(failure_message) else failure_message  # type: ignore[call-arg]
        except Exception:
            msg = str(failure_message) if failure_message else f"custom assertion {kind} failed"
        return False, msg or f"custom assertion {kind} failed"

    return _decorator_factory(kind, _check, default_message=f"assert {kind} failed")


# Utilities to expose
def register_assertion_kind(kind: str, check_fn: Callable[[Any, BaseException | None], bool], message: str | None = None) -> Callable[..., Any]:
    """Register a new assertion kind and return its decorator."""
    return make_assertion_decorator(kind, check_fn, message)


# Manual helpers
def assert_condition(condition: bool, *, game: str | None = None, func: str = "manual", kind: str = "manual", message: str = "manual assertion failed") -> None:
    if not condition:
        tb = "".join(traceback.format_stack(limit=10))
        record_failure(game=game, func=func, kind=kind, message=message, exception=None, traceback_str=tb)


# Gate helper: install check at generation start
_installed_gate = False


def install_assertion_gate() -> None:
    """Install deferred raise at generation start.

    This patches ``worlds.AutoWorld.call_all`` to check failures before
    the first real stage. Idempotent.
    """
    global _installed_gate
    if _installed_gate:
        return
    try:
        from .hard_patch import hard_patches

        def _gate_wrapper(next_callable: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            method_name = args[1] if len(args) >= 2 else kwargs.get("method_name")
            if isinstance(method_name, str) and method_name in (
                "assert_generate",
                "generate_early",
                "create_regions",
            ):
                if get_failure_count() > 0:
                    try:
                        from .generation_gate import wait_for_all_patches
                        wait_for_all_patches(timeout=2.0)
                    except Exception:
                        pass
                    check_and_raise(stage=method_name)
            return next_callable(*args, **kwargs)

        hard_patches.add_wrapper("worlds.AutoWorld.call_all", _gate_wrapper, load_missing=True)
        _installed_gate = True
        logger.debug("APAPI assertion gate installed on call_all")
    except Exception as exc:
        logger.warning("APAPI could not install assertion gate: %s", exc)


# Ensure gate installed on import if possible
try:
    install_assertion_gate()
except Exception:
    pass

# Also install a Main.main after-check as secondary gate
try:
    from .hard_patch import hard_patches as _hp2

    def _main_after_wrapper(next_callable: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        result = next_callable(*args, **kwargs)
        # After Main.main finishes, if there were failures that didn't get raised (e.g., generation didn't reach call_all),
        # try to raise now — but only if generation was supposed to happen and failures exist.
        # On success with no failures, clear any stale state for next generation in same process.
        try:
            if get_failure_count() > 0:
                check_and_raise(stage="Main.main:post")
            else:
                # clean slate for webhost / multi-generation process
                try:
                    # don't clear if _has_raised is still True from a pending deferred raise that was never triggered
                    # (should not happen when count==0)
                    if get_failure_count() == 0:
                        # reset gate for next generation
                        global _has_raised
                        with _lock:
                            _has_raised = False
                except Exception:
                    pass
        except APAPIAssertionAggregateError:
            raise
        except Exception:
            pass
        return result

    try:
        _hp2.add_wrapper("Main.main", _main_after_wrapper, load_missing=True)
    except Exception:
        pass
except Exception:
    pass


__all__ = [
    "AssertionKind",
    "AssertionFailure",
    "APAPIAssertionAggregateError",
    "record_failure",
    "get_failures",
    "clear_failures",
    "get_failure_count",
    "format_report",
    "check_and_raise",
    "assert_no_error",
    "assert_not_error",
    "assert_no_exception",
    "assert_no_raise",
    "assert_not_ending_in_error",
    "assert_returns",
    "assert_return",
    "assert_has_return",
    "assert_returns_not_none",
    "assert_not_none",
    "assert_returns_value",
    "assert_has_non_none_return",
    "make_assertion_decorator",
    "register_assertion_kind",
    "assert_condition",
    "install_assertion_gate",
    "report_fill_error",
    "format_fill_section_for_failure",
]
