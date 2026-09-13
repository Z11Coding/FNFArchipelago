from __future__ import annotations

"""Run code after all AP worlds finish loading.

Problem: import order between world folders is alphabetical-ish and
undefined for the task at hand (``worlds/APAPI`` loads before
``worlds/tunic``, for example). Code that patches another world at import
time therefore races: the target may not exist yet, so the hook silently
never applies depending on who loaded first.

Solution: queue the work and run it once loading is done.

- :func:`on_worlds_loaded` fires after ``worlds/__init__.py`` finishes
  importing every loose world folder (detected via the
  ``network_data_package`` attribute it sets at the end of the load loop).
- :func:`when_game_available` fires with the world's class as soon as
  ``game`` appears in ``AutoWorldRegister.world_types``; if loading
  completes without it (or the timeout expires) the callback fires with
  ``None`` so callers can log and skip instead of hanging generation.

Only uses ``sys.modules`` polling from a daemon thread — no core edits.
"""

import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from .debug import dprint

import logging
logger = logging.getLogger("APAPI.WorldReady")

# callback() -> None
_LoadedCallback = Callable[[], None]
# callback(world_type | None) -> None
_GameCallback = Callable[[Any], None]

_loaded_queue: list[_LoadedCallback] = []
_game_queues: dict[str, list[_GameCallback]] = {}
_queue_lock = threading.RLock()
_worker_started: bool = False
_worlds_ready: bool = False

_POLL_INTERVAL: float = 0.25
_TIMEOUT: float = 120.0


def worlds_loading_complete() -> bool:
    """True once ``worlds/__init__.py`` has built ``network_data_package``."""
    worlds_module: Any = sys.modules.get("worlds")
    return worlds_module is not None and hasattr(worlds_module, "network_data_package")


def is_game_available(game: str) -> bool:
    """True if ``game`` is already registered in ``AutoWorldRegister``."""
    try:
        from worlds.AutoWorld import AutoWorldRegister
    except Exception:
        return False
    return game in AutoWorldRegister.world_types


def get_world_type(game: str) -> Any | None:
    """Return the registered world class for ``game``, or None."""
    try:
        from worlds.AutoWorld import AutoWorldRegister
    except Exception:
        return None
    return AutoWorldRegister.world_types.get(game)


def on_worlds_loaded(callback: _LoadedCallback) -> None:
    """Queue ``callback`` until all loose worlds are loaded; immediate if done."""
    with _queue_lock:
        if _worlds_ready or worlds_loading_complete():
            _mark_ready_locked()
        else:
            _loaded_queue.append(callback)
            dprint("ready", f"queued worlds-loaded callback {getattr(callback, '__name__', callback)}")
            _ensure_worker_locked()
            return
    _fire_loaded(callback)


def when_game_available(game: str, callback: _GameCallback) -> None:
    """Queue ``callback(world_type)`` until ``game`` registers (or fires None)."""
    world_type: Any | None = get_world_type(game)
    if world_type is not None:
        dprint("ready", f"{game} already loaded; firing callback immediately")
        _fire_game(game, callback, world_type)
        return
    with _queue_lock:
        _game_queues.setdefault(game, []).append(callback)
        dprint("ready", f"queued hook for {game} until it loads")
        _ensure_worker_locked()


def _mark_ready_locked() -> None:
    global _worlds_ready
    if not _worlds_ready:
        _worlds_ready = True
        dprint("ready", "all AP worlds loaded")


def _fire_loaded(callback: _LoadedCallback) -> None:
    try:
        callback()
        dprint("ready", f"worlds-loaded callback {getattr(callback, '__name__', callback)} succeeded")
    except Exception as exc:
        logger.warning("[APAPI:ready] worlds-loaded callback %s failed: %s",
                       getattr(callback, "__name__", callback), exc)


def _fire_game(game: str, callback: _GameCallback, world_type: Any | None) -> None:
    try:
        callback(world_type)
        if world_type is None:
            dprint("ready", f"game callback for {game}: NOT FOUND, skipped")
        else:
            dprint("ready", f"hook for {game} applied successfully")
    except Exception as exc:
        logger.warning("[APAPI:ready] game callback for %s failed: %s", game, exc)


def _ensure_worker_locked() -> None:
    global _worker_started
    if _worker_started:
        return
    worker = threading.Thread(target=_poll_worker, name="APAPI-WorldReady", daemon=True)
    worker.start()
    _worker_started = True
    dprint("ready", "world-ready poll worker started")


def _poll_worker() -> None:
    start: float = time.perf_counter()
    while True:
        time.sleep(_POLL_INTERVAL)
        with _queue_lock:
            if worlds_loading_complete():
                _mark_ready_locked()
            # Fire game callbacks whose game just appeared.
            for game in list(_game_queues):
                world_type = get_world_type(game)
                if world_type is not None:
                    for callback in _game_queues.pop(game):
                        _fire_game(game, callback, world_type)
            # Flush worlds-loaded callbacks once ready.
            if _worlds_ready and _loaded_queue:
                pending = _loaded_queue[:]
                del _loaded_queue[:]
            else:
                pending = []
            # Timeout: flush leftovers so nothing hangs forever.
            timed_out: bool = (time.perf_counter() - start) > _TIMEOUT
            leftover_games: dict[str, list[_GameCallback]] = {}
            if timed_out and (_loaded_queue or _game_queues):
                pending.extend(_loaded_queue)
                del _loaded_queue[:]
                leftover_games = dict(_game_queues)
                _game_queues.clear()
                logger.warning("[APAPI:ready] world-ready wait timed out; flushing %d callback(s)",
                               len(pending) + sum(len(v) for v in leftover_games.values()))
            done: bool = _worlds_ready and not _loaded_queue and not _game_queues
        for callback in pending:
            _fire_loaded(callback)
        for game, callbacks in leftover_games.items():
            for callback in callbacks:
                _fire_game(game, callback, None)
        if done or timed_out:
            dprint("ready", "world-ready poll worker finished")
            return


__all__ = [
    "get_world_type",
    "is_game_available",
    "on_worlds_loaded",
    "when_game_available",
    "worlds_loading_complete",
]
