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
                disable=False,
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


__all__ = ["initialize_progress", "is_progress_enabled", "set_progress_enabled"]
