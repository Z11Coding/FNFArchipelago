from __future__ import annotations

"""Defer callbacks until worlds are loaded or a game is available."""

import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from .debug import dprint

import logging
logger = logging.getLogger("APAPI.WorldReady")

_LoadedCallback = Callable[[], None]
_GameCallback = Callable[[Any], None]

_loaded_queue: list[_LoadedCallback] = []
_game_queues: dict[str, list[_GameCallback]] = {}
_queue_lock = threading.RLock()
_worker_started: bool = False
_worlds_ready: bool = False

_POLL_INTERVAL: float = 0.25
_TIMEOUT: float = 120.0


def worlds_loading_complete() -> bool:
    """Returns: True if network_data_package exists."""
    worlds_module: Any = sys.modules.get("worlds")
    return worlds_module is not None and hasattr(worlds_module, "network_data_package")


def is_game_available(game: str) -> bool:
    """Input: game. Returns: True if registered."""
    try:
        from worlds.AutoWorld import AutoWorldRegister
    except Exception:
        return False
    return game in AutoWorldRegister.world_types


def get_world_type(game: str) -> Any | None:
    """Input: game. Returns: world class or None."""
    try:
        from worlds.AutoWorld import AutoWorldRegister
    except Exception:
        return None
    return AutoWorldRegister.world_types.get(game)


def on_worlds_loaded(callback: _LoadedCallback) -> None:
    """Input: callback. Returns: None (fires now or queues)."""
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
    """Input: game, callback. Returns: None (fires now or queues)."""
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
    """Input: None. Returns: None (marks ready)."""
    global _worlds_ready
    if not _worlds_ready:
        _worlds_ready = True
        dprint("ready", "all AP worlds loaded")


def _fire_loaded(callback: _LoadedCallback) -> None:
    """Input: callback. Returns: None (runs it)."""
    try:
        callback()
        dprint("ready", f"worlds-loaded callback {getattr(callback, '__name__', callback)} succeeded")
    except Exception as exc:
        logger.warning("[APAPI:ready] worlds-loaded callback %s failed: %s",
                       getattr(callback, "__name__", callback), exc)


def _fire_game(game: str, callback: _GameCallback, world_type: Any | None) -> None:
    """Input: game, callback, world_type. Returns: None (runs it)."""
    try:
        callback(world_type)
        if world_type is None:
            dprint("ready", f"game callback for {game}: NOT FOUND, skipped")
        else:
            dprint("ready", f"hook for {game} applied successfully")
    except Exception as exc:
        logger.warning("[APAPI:ready] game callback for %s failed: %s", game, exc)


def _ensure_worker_locked() -> None:
    """Input: None. Returns: None (starts poll worker)."""
    global _worker_started
    if _worker_started:
        return
    worker = threading.Thread(target=_poll_worker, name="APAPI-WorldReady", daemon=True)
    worker.start()
    _worker_started = True
    dprint("ready", "world-ready poll worker started")


def _poll_worker() -> None:
    """Input: None. Returns: None (polls until ready/timeout)."""
    start: float = time.perf_counter()
    while True:
        time.sleep(_POLL_INTERVAL)
        with _queue_lock:
            if worlds_loading_complete():
                _mark_ready_locked()
            for game in list(_game_queues):
                world_type = get_world_type(game)
                if world_type is not None:
                    for callback in _game_queues.pop(game):
                        _fire_game(game, callback, world_type)
            if _worlds_ready and _loaded_queue:
                pending = _loaded_queue[:]
                del _loaded_queue[:]
            else:
                pending = []
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
