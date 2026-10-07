from __future__ import annotations

"""Generation progress bar using tqdm. Injected automatically by APAPI."""

import logging
import threading
import time
from typing import Any

from .debug import dprint

logger = logging.getLogger("APAPI.Progress")

try:
    from .tqdm import tqdm as _tqdm
    from .tqdm import trange as _trange
    HAS_TQDM = True
except Exception:
    try:
        from tqdm import tqdm as _tqdm
        from tqdm import trange as _trange
        HAS_TQDM = True
    except Exception:
        HAS_TQDM = False
        _tqdm = None  # type: ignore
        _trange = None  # type: ignore

from .generation import KNOWN_STAGES, on_stage

_progress_lock = threading.RLock()
_stage_bar: Any = None
_fill_bar: Any = None
_fill_bars: dict[str, Any] = {}
_start_time: float | None = None
_enabled = True
_initialized = False

# Console suspension: while > 0, tqdm rendering is held (monitor thread and
# update paths included) so prompts awaiting input are not erased or buried.
# Internal counters keep updating, so bars resume accurately.
_suspend_count = 0
_suspend_snapshot: dict[int, Any] = {}

# Deferred console output: while suspended, sub-warning console log records
# and console print() text are buffered in arrival order and replayed on
# resume, so background threads cannot print over a prompt awaiting input.
# File handlers are never touched (nothing is ever lost), WARNING+ always
# prints immediately, and logging/printing is never blocked.
_defer_lock = threading.Lock()
_deferred: list[Any] = []  # ("log", handler, record) | ("print", text)
_wrapped_handlers: dict[int, Any] = {}
_defer_dropped = 0
_DEFER_CAP = 1000


def _buffer_entry(entry: Any) -> None:
    global _defer_dropped
    try:
        with _defer_lock:
            _deferred.append(entry)
            while len(_deferred) > _DEFER_CAP:
                _deferred.pop(0)
                _defer_dropped += 1
    except Exception:
        pass


def _tracked_bars() -> list[Any]:
    seen: set[int] = set()
    out: list[Any] = []
    candidates: list[Any] = [_stage_bar, _fill_bar] + list(_fill_bars.values())
    try:
        candidates.append(_overall_fill_bar)
    except NameError:
        pass
    for bar in candidates:
        if bar is not None and id(bar) not in seen:
            seen.add(id(bar))
            out.append(bar)
    return out


def console_suspended() -> bool:
    """Returns: True while console output is suspended for a prompt."""
    return _suspend_count > 0


def suspend_console_output() -> None:
    """Hold all APAPI progress rendering (reentrant). Counters keep updating."""
    global _suspend_count
    with _progress_lock:
        _suspend_count += 1
        if _suspend_count > 1:
            return
        _suspend_snapshot.clear()
        for bar in _tracked_bars():
            try:
                _suspend_snapshot[id(bar)] = (bar, bool(getattr(bar, "disable", False)))
                bar.disable = True
            except Exception:
                continue
        _install_log_defer()


def resume_console_output() -> None:
    """Resume rendering after suspend_console_output (reentrant). Repaints once."""
    global _suspend_count
    with _progress_lock:
        if _suspend_count > 0:
            _suspend_count -= 1
        if _suspend_count > 0:
            return
        _remove_log_defer()
        snapshot = dict(_suspend_snapshot)
        _suspend_snapshot.clear()
        for _bid, (bar, prev) in snapshot.items():
            try:
                bar.disable = prev
            except Exception:
                continue
        for bar in _tracked_bars():
            try:
                if id(bar) not in snapshot:
                    bar.disable = False
            except Exception:
                pass
            try:
                bar.refresh()
            except Exception:
                pass


def _console_stream_handlers() -> dict[int, Any]:
    """Currently attached console (non-file stream) handlers, by id."""
    import logging as _logging
    found: dict[int, Any] = {}
    try:
        loggers: list[Any] = [_logging.root]
        try:
            manager_dict = _logging.Logger.manager.loggerDict
        except Exception:
            manager_dict = {}
        for logger_obj in list(manager_dict.values()):
            if isinstance(logger_obj, _logging.Logger):
                loggers.append(logger_obj)
        for logger_obj in loggers:
            try:
                handlers = list(logger_obj.handlers)
            except Exception:
                continue
            for handler in handlers:
                try:
                    if isinstance(handler, _logging.StreamHandler) \
                            and not isinstance(handler, _logging.FileHandler):
                        found[id(handler)] = handler
                except Exception:
                    continue
    except Exception:
        pass
    return found


def _make_deferring_emit(handler: Any, orig_emit: Any) -> Any:
    import logging as _logging

    def _emit(record: Any) -> None:
        try:
            if record.levelno >= _logging.WARNING:
                orig_emit(record)
                return
        except Exception:
            pass
        _buffer_entry(("log", handler, record))

    return _emit


def _install_log_defer() -> None:
    """Buffer sub-warning console records until resume (best effort)."""
    try:
        for hid, handler in _console_stream_handlers().items():
            try:
                if getattr(handler, "_apapi_defer_wrapped", False):
                    continue
                orig_emit = handler.emit
                handler.emit = _make_deferring_emit(handler, orig_emit)  # type: ignore[method-assign]
                handler._apapi_defer_wrapped = True  # type: ignore[attr-defined]
                with _defer_lock:
                    _wrapped_handlers[hid] = (handler, orig_emit)
            except Exception:
                continue
    except Exception:
        pass


def _remove_log_defer() -> None:
    """Restore console handlers and replay buffered records in order."""
    try:
        with _defer_lock:
            wrapped = list(_wrapped_handlers.values())
            _wrapped_handlers.clear()
            pending = list(_deferred)
            _deferred.clear()
        for handler, orig_emit in wrapped:
            try:
                handler.emit = orig_emit
            except Exception:
                continue
            try:
                handler._apapi_defer_wrapped = False  # type: ignore[attr-defined]
            except Exception:
                pass
        # Drain anything appended between snapshot and restore, then replay.
        try:
            with _defer_lock:
                pending.extend(_deferred)
                _deferred.clear()
        except Exception:
            pass
    except Exception:
        return
    by_orig: dict[int, Any] = {}
    for handler, orig_emit in wrapped:
        try:
            by_orig[id(handler)] = orig_emit
        except Exception:
            continue
    for entry in pending:
        try:
            if not isinstance(entry, tuple) or not entry:
                continue
            if entry[0] == "print":
                try:
                    import sys as _sys3
                    _stream = getattr(_sys3, "stdout", None)
                    if _stream is not None:
                        _stream.write(entry[1])
                except Exception:
                    pass
                continue
            _handler, _record = entry[1], entry[2]
            orig = by_orig.get(id(_handler))
            (orig or _handler.emit)(_record)
        except Exception:
            continue
    try:
        import sys as _sys4
        _sys4.stdout.flush()
    except Exception:
        pass


_orig_input: Any = None
_input_installed = False


def _apapi_input(prompt: str = "") -> str:
    """input() with APAPI console quiesced. Semantics identical to builtin."""
    suspend_console_output()
    try:
        try:
            import sys as _sys
            _sys.stdout.flush()
        except Exception:
            pass
        try:
            import sys as _sys2
            _sys2.stderr.flush()
        except Exception:
            pass
        try:
            import logging as _logging
            for _handler in list(_logging.root.handlers):
                try:
                    _handler.flush()
                except Exception:
                    continue
        except Exception:
            pass
        if _orig_input is None:
            raise RuntimeError("APAPI input override installed without an original input")
        return _orig_input(prompt)
    finally:
        resume_console_output()


def install_input_override() -> None:
    """Route builtins.input/print and pprint through console quiescing.

    Idempotent. Behavior is otherwise identical: same prompt handling, same
    return values, same exceptions (EOFError/OSError/RuntimeError propagate
    unchanged). Console print()/pprint() text and sub-warning console logs
    arriving while suspended are buffered and replayed in order on resume,
    so background threads cannot bury prompts awaiting input. Worlds calling
    input()/inputimeout()/print()/pprint() are covered with no code changes.
    """
    global _orig_input, _input_installed, _orig_print, _print_installed
    if _input_installed:
        try:
            _install_pprint_override()
        except Exception:
            pass
        return
    try:
        import builtins as _builtins
    except Exception:
        return
    try:
        current = _builtins.input
        if getattr(current, "__apapi_input_wrapped__", False):
            _input_installed = True
        else:
            _orig_input = current

            def _wrapped(prompt: str = "") -> str:
                return _apapi_input(prompt)

            _wrapped.__apapi_input_wrapped__ = True  # type: ignore[attr-defined]
            try:
                _wrapped.__name__ = "input"
            except Exception:
                pass
            _builtins.input = _wrapped  # type: ignore[assignment]
        current_print = _builtins.print
        if getattr(current_print, "__apapi_print_wrapped__", False):
            _print_installed = True
        else:
            _orig_print = current_print

            def _wrapped_print(*args: Any, sep: str = " ", end: str = "\n",
                               file: Any = None, flush: bool = False) -> None:
                _apapi_print(*args, sep=sep, end=end, file=file, flush=flush)

            _wrapped_print.__apapi_print_wrapped__ = True  # type: ignore[attr-defined]
            try:
                _wrapped_print.__name__ = "print"
            except Exception:
                pass
            _builtins.print = _wrapped_print  # type: ignore[assignment]
    except Exception:
        return
    _input_installed = True
    _print_installed = True
    try:
        _install_pprint_override()
    except Exception:
        pass


def remove_input_override() -> bool:
    """Restore the original builtins.input/print and pprint. Returns: True if removed."""
    global _orig_input, _input_installed, _orig_print, _print_installed
    global _orig_pprint, _orig_pp, _pprint_installed
    removed = False
    try:
        import builtins as _builtins
        current = _builtins.input
        if getattr(current, "__apapi_input_wrapped__", False) and _orig_input is not None:
            _builtins.input = _orig_input  # type: ignore[assignment]
            _orig_input = None
            _input_installed = False
            removed = True
    except Exception:
        pass
    try:
        import builtins as _builtins2
        current_print = _builtins2.print
        if getattr(current_print, "__apapi_print_wrapped__", False) and _orig_print is not None:
            _builtins2.print = _orig_print  # type: ignore[assignment]
            _orig_print = None
            _print_installed = False
            removed = True
    except Exception:
        pass
    try:
        import pprint as _pprint_mod
        current_pprint = getattr(_pprint_mod, "pprint", None)
        if getattr(current_pprint, "__apapi_pprint_wrapped__", False) and _orig_pprint is not None:
            _pprint_mod.pprint = _orig_pprint  # type: ignore[assignment]
            _orig_pprint = None
            removed = True
        current_pp = getattr(_pprint_mod, "pp", None)
        if current_pp is not None and getattr(current_pp, "__apapi_pprint_wrapped__", False) \
                and _orig_pp is not None:
            _pprint_mod.pp = _orig_pp  # type: ignore[assignment]
            _orig_pp = None
            removed = True
    except Exception:
        pass
    _pprint_installed = False
    return removed


_orig_print: Any = None
_print_installed = False


def _apapi_print(*args: Any, sep: str = " ", end: str = "\n",
                 file: Any = None, flush: bool = False) -> None:
    """print() with console output held while suspended. Semantics identical.

    Only output aimed at the live console (stdout/stderr) is deferred;
    writes to files or replaced streams pass straight through. Deferred
    text replays verbatim on resume.
    """
    try:
        import sys as _sys
        stream = file if file is not None else _sys.stdout
        try:
            is_console = stream is not None and (stream is _sys.stdout or stream is _sys.stderr)
        except Exception:
            is_console = False
        if is_console and console_suspended():
            try:
                text = sep.join(str(o) for o in args) + end if end else sep.join(str(o) for o in args)
                _buffer_entry(("print", text))
                return None
            except Exception:
                pass
    except Exception:
        pass
    if _orig_print is None:
        raise RuntimeError("APAPI print override installed without an original print")
    return _orig_print(*args, sep=sep, end=end, file=file, flush=flush)


_orig_pprint: Any = None
_orig_pp: Any = None
_pprint_installed = False


def _pprint_target_is_console(stream: Any) -> bool:
    try:
        import sys as _sys
        if stream is None:
            stream = _sys.stdout
        return stream is not None and (stream is _sys.stdout or stream is _sys.stderr)
    except Exception:
        return False


def _apapi_pprint(object: Any, stream: Any = None, indent: int = 1, width: int = 80,
                  depth: Any = None, *, compact: bool = False, sort_dicts: bool = True,
                  underscore_numbers: bool = False) -> None:
    """pprint.pprint() with console output held while suspended. Semantics identical."""
    try:
        if _pprint_target_is_console(stream) and console_suspended():
            try:
                import pprint as _pprint_mod
                text = _pprint_mod.pformat(
                    object, indent=indent, width=width, depth=depth,
                    compact=compact, sort_dicts=sort_dicts,
                    underscore_numbers=underscore_numbers) + "\n"
                _buffer_entry(("print", text))
                return None
            except Exception:
                pass
    except Exception:
        pass
    if _orig_pprint is None:
        raise RuntimeError("APAPI pprint override installed without an original pprint")
    return _orig_pprint(object, stream=stream, indent=indent, width=width, depth=depth,
                        compact=compact, sort_dicts=sort_dicts,
                        underscore_numbers=underscore_numbers)


def _apapi_pp(object: Any, stream: Any = None, indent: int = 1, width: int = 80,
              depth: Any = None, *, compact: bool = False, sort_dicts: bool = False,
              underscore_numbers: bool = False) -> None:
    """pprint.pp() with console output held while suspended. Semantics identical."""
    try:
        if _pprint_target_is_console(stream) and console_suspended():
            try:
                import pprint as _pprint_mod
                text = _pprint_mod.pformat(
                    object, indent=indent, width=width, depth=depth,
                    compact=compact, sort_dicts=sort_dicts,
                    underscore_numbers=underscore_numbers) + "\n"
                _buffer_entry(("print", text))
                return None
            except Exception:
                pass
    except Exception:
        pass
    if _orig_pp is None:
        raise RuntimeError("APAPI pp override installed without an original pp")
    return _orig_pp(object, stream=stream, indent=indent, width=width, depth=depth,
                    compact=compact, sort_dicts=sort_dicts,
                    underscore_numbers=underscore_numbers)


def _install_pprint_override() -> None:
    """Route pprint.pprint/pp through console quiescing (idempotent)."""
    global _orig_pprint, _orig_pp, _pprint_installed
    if _pprint_installed:
        return
    try:
        import pprint as _pprint_mod
    except Exception:
        return
    try:
        current = getattr(_pprint_mod, "pprint", None)
        if getattr(current, "__apapi_pprint_wrapped__", False):
            _pprint_installed = True
        elif current is not None:
            _orig_pprint = current

            def _wrapped_pprint(object: Any, stream: Any = None, indent: int = 1,
                                width: int = 80, depth: Any = None, *, compact: bool = False,
                                sort_dicts: bool = True, underscore_numbers: bool = False) -> None:
                return _apapi_pprint(object, stream=stream, indent=indent, width=width,
                                     depth=depth, compact=compact, sort_dicts=sort_dicts,
                                     underscore_numbers=underscore_numbers)

            _wrapped_pprint.__apapi_pprint_wrapped__ = True  # type: ignore[attr-defined]
            try:
                _wrapped_pprint.__name__ = "pprint"
            except Exception:
                pass
            _pprint_mod.pprint = _wrapped_pprint  # type: ignore[assignment]
        current_pp = getattr(_pprint_mod, "pp", None)
        if current_pp is not None and not getattr(current_pp, "__apapi_pprint_wrapped__", False):
            _orig_pp = current_pp

            def _wrapped_pp(object: Any, stream: Any = None, indent: int = 1,
                            width: int = 80, depth: Any = None, *, compact: bool = False,
                            sort_dicts: bool = False, underscore_numbers: bool = False) -> None:
                return _apapi_pp(object, stream=stream, indent=indent, width=width,
                                 depth=depth, compact=compact, sort_dicts=sort_dicts,
                                 underscore_numbers=underscore_numbers)

            _wrapped_pp.__apapi_pprint_wrapped__ = True  # type: ignore[attr-defined]
            try:
                _wrapped_pp.__name__ = "pp"
            except Exception:
                pass
            _pprint_mod.pp = _wrapped_pp  # type: ignore[assignment]
    except Exception:
        return
    _pprint_installed = True


def is_progress_enabled() -> bool:
    """Return True if progress bar should show."""
    if not _enabled:
        return False
    if not HAS_TQDM:
        return False
    # Disable if output is not a tty and not forced? Keep simple: always try.
    return True


def set_progress_enabled(enabled: bool) -> None:
    """Enable or disable progress bar."""
    global _enabled
    _enabled = bool(enabled)


def _get_tqdm():
    if not HAS_TQDM or _tqdm is None:
        return None
    return _tqdm


def _ensure_stage_bar():
    global _stage_bar, _start_time
    if _stage_bar is not None:
        return _stage_bar
    if not is_progress_enabled():
        return None
    tqdm = _get_tqdm()
    if tqdm is None:
        return None
    try:
        _stage_bar = tqdm(
            total=len(KNOWN_STAGES),
            desc="Generating",
            unit="stage",
            dynamic_ncols=True,
            leave=True,
            position=0,
            disable=console_suspended(),
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}] {postfix}",
        )
        _start_time = time.perf_counter()
        dprint("progress", "stage bar created")
    except Exception as exc:
        logger.debug("APAPI progress stage bar failed: %s", exc)
        _stage_bar = None
    return _stage_bar


def _update_stage(stage: str) -> None:
    with _progress_lock:
        bar = _ensure_stage_bar()
        if bar is None:
            return
        try:
            # Find index of stage
            try:
                idx = KNOWN_STAGES.index(stage)
                # Update to idx+1
                bar.n = idx + 1
                bar.set_postfix_str(stage)
                bar.refresh()
            except ValueError:
                bar.set_postfix_str(stage)
                bar.update(1)
            dprint("progress", f"stage {stage} -> {bar.n}/{bar.total}")
        except Exception as exc:
            logger.debug("APAPI progress stage update failed: %s", exc)


def _close_stage_bar():
    global _stage_bar, _overall_fill_bar, _fill_bar
    with _progress_lock:
        if _stage_bar is not None:
            try:
                _stage_bar.close()
            except Exception:
                pass
            _stage_bar = None
        for name, bar in list(_fill_bars.items()):
            try:
                bar.close()
            except Exception:
                pass
        _fill_bars.clear()
        if _fill_bar is not None:
            try:
                _fill_bar.close()
            except Exception:
                pass
            _fill_bar = None
        if _overall_fill_bar is not None:
            try:
                _overall_fill_bar.close()
            except Exception:
                pass
            _overall_fill_bar = None
            _fill_bars.clear()


def _ensure_fill_bar(name: str, total: int):
    if not is_progress_enabled():
        return None
    tqdm = _get_tqdm()
    if tqdm is None:
        return None
    with _progress_lock:
        if name in _fill_bars:
            bar = _fill_bars[name]
            # Update total if changed
            try:
                if bar.total != total:
                    bar.total = total
                    bar.refresh()
            except Exception:
                pass
            return bar
        try:
            bar = tqdm(
                total=total,
                desc=f"Fill:{name}",
                unit="item",
                dynamic_ncols=True,
                leave=False,
                position=2,
                disable=console_suspended(),
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}] {postfix}",
            )
            _fill_bars[name] = bar
            dprint("progress", f"fill bar {name} total {total}")
            return bar
        except Exception as exc:
            logger.debug("APAPI progress fill bar failed: %s", exc)
            return None


def _update_fill(name: str, placed: int, total: int):
    if not is_progress_enabled():
        return
    bar = _ensure_fill_bar(name, total)
    if bar is None:
        return
    try:
        with _progress_lock:
            bar.n = placed
            bar.total = total
            bar.set_postfix_str(f"{placed}/{total}")
            bar.refresh()
            if placed >= total:
                bar.close()
                _fill_bars.pop(name, None)
    except Exception as exc:
        logger.debug("APAPI progress fill update failed: %s", exc)


def _on_stage_callback(multiworld: Any, *args: Any, stage: str | None = None, **kwargs: Any) -> None:
    # This is called via on_stage which passes multiworld as first arg, but we need stage name
    # on_stage registers per stage, so we can use a closure to capture stage
    pass


def _install_stage_hooks():
    # Register for each known stage
    for stage in KNOWN_STAGES:
        def make_cb(s: str):
            def cb(multiworld: Any, *a: Any, **kw: Any) -> None:
                _update_stage(s)
                if s == "generate_output":
                    # Close after a short delay to let fill bars finish
                    def delayed_close():
                        time.sleep(0.5)
                        _close_stage_bar()
                    threading.Thread(target=delayed_close, daemon=True).start()
            return cb
        on_stage(stage, make_cb(stage))
    dprint("progress", f"stage hooks installed for {len(KNOWN_STAGES)} stages")


def _wrap_log_fill(next_callable, *args: Any, **kwargs: Any) -> Any:
    # Wrap _log_fill_progress(name, placed, total) - update dedicated fill bar
    try:
        name = args[0] if len(args) > 0 else kwargs.get("name", "Unknown")
        placed = args[1] if len(args) > 1 else kwargs.get("placed", 0)
        total = args[2] if len(args) > 2 else kwargs.get("total_items", kwargs.get("total", 0))
        _update_fill(str(name), int(placed), int(total))
        # Also update overall item fill bar
        _update_overall_fill(int(placed), int(total), str(name))
    except Exception:
        pass
    return next_callable(*args, **kwargs)


_overall_fill_bar: Any = None
_overall_fill_total: int = 0
_overall_fill_placed: int = 0


def _ensure_overall_fill_bar(total: int) -> Any:
    global _overall_fill_bar, _overall_fill_total
    if not is_progress_enabled():
        return None
    tqdm = _get_tqdm()
    if tqdm is None:
        return None
    with _progress_lock:
        if _overall_fill_bar is not None:
            try:
                if _overall_fill_bar.total != total and total > 0:
                    _overall_fill_bar.total = total
                    _overall_fill_bar.refresh()
            except Exception:
                pass
            return _overall_fill_bar
        try:
            import sys as _sys
            _overall_fill_total = total
            _overall_fill_bar = tqdm(
                total=total if total > 0 else 100,
                desc="Filling items",
                unit="item",
                dynamic_ncols=True,
                leave=True,
                position=1,
                file=_sys.stderr,
                disable=True if console_suspended() else False,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}] {postfix}",
            )
            dprint("progress", f"overall fill bar total {total}")
            # Also log normally so user sees it even without debug
            logger.info("[APAPI:progress] Filling items bar created total %s", total)
            return _overall_fill_bar
        except Exception as exc:
            logger.debug("APAPI progress overall fill bar failed: %s", exc)
            return None


def _update_overall_fill(placed: int, total: int, name: str = "") -> None:
    bar = _ensure_overall_fill_bar(total if total > 0 else 100)
    if bar is None:
        return
    try:
        with _progress_lock:
            # For per-step updates, we want to show overall progress
            # Use max of placed across steps, but also handle multiple concurrent fills
            # Simple: set n to placed, but ensure it doesn't go backwards
            if placed > _overall_fill_bar.n:  # type: ignore
                bar.n = placed
            bar.set_postfix_str(name)
            bar.refresh()
            if placed >= total and total > 0:
                # Don't close immediately, keep for next fill step
                pass
    except Exception as exc:
        logger.debug("APAPI progress overall fill update failed: %s", exc)


def _wrap_fill_restrictive(next_callable, *args: Any, **kwargs: Any) -> Any:
    # Wrap Fill.fill_restrictive to show dedicated item filling bar
    name = kwargs.get("name", "Unknown")
    # Also ensure overall bar
    if len(args) >= 4:
        try:
            locations = args[2]
            item_pool = args[3]
            total = min(len(locations), len(item_pool)) if hasattr(locations, "__len__") and hasattr(item_pool, "__len__") else 0
            if total > 0:
                _ensure_fill_bar(str(name), total)
                _ensure_overall_fill_bar(total)
        except Exception:
            pass
    # Suppress AP's "Placed X at Y" debug spam during this fill
    # BaseClasses.push_item logs at DEBUG, but generation sets root to DEBUG, so it floods.
    # Temporarily raise that logger's level or patch.
    result = next_callable(*args, **kwargs)
    with _progress_lock:
        bar = _fill_bars.pop(str(name), None)
        if bar is not None:
            try:
                bar.n = bar.total
                bar.refresh()
                bar.close()
            except Exception:
                pass
    return result


def _wrap_distribute(next_callable, *args: Any, **kwargs: Any) -> Any:
    # Wrap distribute_items_restrictive to ensure stage bar is visible and overall fill bar exists
    bar = _ensure_stage_bar()
    if bar is not None:
        try:
            bar.set_postfix_str("distribute_items_restrictive")
            bar.refresh()
        except Exception:
            pass
    # Estimate total for overall bar from multiworld
    try:
        multiworld = args[0] if args else None
        if multiworld is not None and hasattr(multiworld, "get_unfilled_locations"):
            total_locs = len(multiworld.get_unfilled_locations())
            if total_locs > 0:
                _ensure_overall_fill_bar(total_locs)
    except Exception:
        pass
    return next_callable(*args, **kwargs)


_placed_filter_installed = False
_placed_filter: Any = None

def _ensure_placed_filter() -> None:
    # Install a single filter that makes "Placed ..." and "Checking if ..." respect proper level
    # They are DEBUG level but should only show when APAPI debug is on or loglevel is DEBUG
    global _placed_filter_installed, _placed_filter
    if _placed_filter_installed:
        return
    import logging as _logging
    class _ProperLevelFilter(_logging.Filter):
        def filter(self, record: _logging.LogRecord) -> bool:
            try:
                msg = record.getMessage()
                if (msg.startswith("Placed ") and " at " in msg) or msg.startswith("Checking if ") and "is required to beat" in msg:
                    try:
                        from .debug import is_debug_enabled
                        if not is_debug_enabled():
                            # Check effective level - if root is INFO, suppress DEBUG
                            # Use record.levelno to check
                            if record.levelno <= _logging.DEBUG:
                                return False
                    except Exception:
                        pass
                    # Also check if root's effective level is INFO, suppress DEBUG
                    try:
                        if _logging.getLogger().getEffectiveLevel() > _logging.DEBUG:
                            return False
                    except Exception:
                        pass
            except Exception:
                pass
            return True
    _placed_filter = _ProperLevelFilter()
    try:
        _logging.getLogger().addFilter(_placed_filter)
        _logging.getLogger("BaseClasses").addFilter(_placed_filter)
        _placed_filter_installed = True
        dprint("progress", "installed Placed/Checking if proper level filter")
    except Exception as exc:
        logger.debug("APAPI progress filter install failed: %s", exc)

def _wrap_push_item(next_callable, *args: Any, **kwargs: Any) -> Any:
    _ensure_placed_filter()
    result = next_callable(*args, **kwargs)
    try:
        with _progress_lock:
            if _overall_fill_bar is not None:
                _overall_fill_bar.update(1)
                try:
                    _overall_fill_bar.set_postfix_str(f"{_overall_fill_bar.n}/{_overall_fill_bar.total}")
                    _overall_fill_bar.refresh()
                except Exception:
                    pass
            else:
                _ensure_overall_fill_bar(100)
                if _overall_fill_bar is not None:
                    _overall_fill_bar.update(1)
    except Exception:
        pass
    return result


def _wrap_create_playthrough(next_callable, *args: Any, **kwargs: Any) -> Any:
    _ensure_placed_filter()
    return next_callable(*args, **kwargs)


def _install_debug_level_tracer() -> None:
    import logging as _logging
    import traceback as _tb
    orig_setLevel = _logging.Logger.setLevel
    orig_basicConfig = _logging.basicConfig
    try:
        import Utils as _Utils
        orig_init_logging = _Utils.init_logging
    except Exception:
        orig_init_logging = None  # type: ignore
    _seen: set[str] = set()
    def _should_log(stack: str) -> bool:
        if "progress.py" in stack and ("_wrap" in stack or "_traced" in stack):
            return False
        key = stack.split("File")[-1][:200] if "File" in stack else stack[:200]
        if key in _seen:
            return False
        _seen.add(key)
        return True
    def _traced_setLevel(self: _logging.Logger, level: int) -> None:
        try:
            stack = "".join(_tb.format_stack(limit=10))
            if _should_log(stack):
                lvl_name = _logging.getLevelName(level)
                logger.info("[APAPI:progress] setLevel %s on %s by:\n%s", lvl_name, getattr(self, "name", "root"), stack)
                dprint("progress", f"setLevel {lvl_name} on {getattr(self, 'name', 'root')}")
        except Exception:
            pass
        return orig_setLevel(self, level)
    def _traced_basicConfig(*a: Any, **kw: Any) -> Any:
        try:
            lvl = kw.get("level", None)
            if lvl is None and a and isinstance(a[0], int):
                lvl = a[0]
            stack = "".join(_tb.format_stack(limit=10))
            if _should_log(stack):
                lvl_name = _logging.getLevelName(lvl) if isinstance(lvl, int) else str(lvl)
                logger.info("[APAPI:progress] basicConfig level=%r", lvl_name)
                dprint("progress", f"basicConfig level={lvl_name}")
        except Exception:
            pass
        return orig_basicConfig(*a, **kw)
    def _traced_init_logging(name: str, loglevel: Any = _logging.INFO, *a: Any, **kw: Any) -> Any:
        try:
            lvl = kw.get("loglevel", loglevel)
            stack = "".join(_tb.format_stack(limit=10))
            if _should_log(stack):
                lvl_name = str(lvl)
                try:
                    if isinstance(lvl, str):
                        mapped = _Utils.loglevel_mapping.get(lvl.lower(), lvl) if '_Utils' in locals() and hasattr(_Utils, "loglevel_mapping") else lvl
                        lvl_name = _logging.getLevelName(mapped) if isinstance(mapped, int) else str(mapped)
                    else:
                        lvl_name = _logging.getLevelName(lvl) if isinstance(lvl, int) else str(lvl)
                except Exception:
                    lvl_name = str(lvl)
                logger.info("[APAPI:progress] Utils.init_logging for %s level=%r (%s)", name, loglevel, lvl_name)
                dprint("progress", f"Utils.init_logging for {name} level={loglevel!r}")
        except Exception:
            pass
        if orig_init_logging is not None:
            return orig_init_logging(name, loglevel, *a, **kw)
        return None
    try:
        _logging.Logger.setLevel = _traced_setLevel  # type: ignore[method-assign, assignment]
        _logging.basicConfig = _traced_basicConfig  # type: ignore[assignment]
        if orig_init_logging is not None:
            _Utils.init_logging = _traced_init_logging  # type: ignore[assignment]
        try:
            cur_level = _logging.getLogger().level
            cur_name = _logging.getLevelName(cur_level)
            logger.info("[APAPI:progress] tracer installed, current root level %s (%s)", cur_level, cur_name)
        except Exception:
            pass
        dprint("progress", "installed level tracer (deduped, skips own wrappers)")
    except Exception as exc:
        logger.debug("APAPI progress debug tracer failed: %s", exc)
    except Exception as exc:
        logger.debug("APAPI progress debug tracer failed: %s", exc)


def initialize_progress() -> None:
    """Install progress hooks. Idempotent, called automatically from APAPI.__init__."""
    global _initialized
    try:
        _install_debug_level_tracer()
    except Exception:
        pass
    try:
        _ensure_placed_filter()
    except Exception:
        pass
    if _initialized:
        return
    if not is_progress_enabled():
        dprint("progress", "progress disabled (no tqdm or disabled)")
        _initialized = True
        return
    try:
        _install_stage_hooks()
    except Exception as exc:
        logger.debug("APAPI progress stage hooks failed: %s", exc)
    try:
        from .hard_patch import hard_patches
        # Hook Fill progress logging and dedicated item filling bar
        hard_patches.add_wrapper("Fill._log_fill_progress", _wrap_log_fill, load_missing=True)
        hard_patches.add_wrapper("Fill.fill_restrictive", _wrap_fill_restrictive, load_missing=True)
        hard_patches.add_wrapper("Fill.distribute_items_restrictive", _wrap_distribute, load_missing=True)
        hard_patches.add_wrapper("Fill.remaining_fill", _wrap_fill_restrictive, load_missing=True)
        # Patch both debug spams to use proper level (only show when APAPI debug or loglevel DEBUG)
        hard_patches.add_wrapper("BaseClasses.MultiWorld.push_item", _wrap_push_item, load_missing=True)
        hard_patches.add_wrapper("BaseClasses.Spoiler.create_playthrough", _wrap_create_playthrough, load_missing=True)
        dprint("progress", "fill hooks installed (including Placed/Checking if proper level)")
    except Exception as exc:
        logger.debug("APAPI progress fill hooks failed: %s", exc)
    # Also hook Main.main to ensure bar is created early and closed at end
    try:
        from .core_hooks import register_soft_before, register_soft_after
        def _before_main(*a: Any, **kw: Any) -> None:
            _ensure_stage_bar()
            if _stage_bar is not None:
                try:
                    _stage_bar.n = 0
                    _stage_bar.refresh()
                except Exception:
                    pass
        def _after_main(*a: Any, **kw: Any) -> None:
            _close_stage_bar()
        register_soft_before("core.main", _before_main)
        register_soft_after("core.main", _after_main)
        dprint("progress", "main hooks installed")
    except Exception as exc:
        logger.debug("APAPI progress main hooks failed: %s", exc)
    _initialized = True
    dprint("progress", "progress initialized")


__all__ = ["initialize_progress", "is_progress_enabled", "set_progress_enabled",
           "suspend_console_output", "resume_console_output", "console_suspended",
           "install_input_override", "remove_input_override"]
