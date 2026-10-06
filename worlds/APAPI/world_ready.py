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
_retried_failed_worlds: set[str] = set()

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


def _get_apworld_root_folder(apworld_path: str) -> str | None:
    try:
        import zipfile
        from pathlib import Path
        p = Path(apworld_path)
        # Resolve for is_zip relative case
        if getattr(p, "is_absolute", lambda: False)() is False:
            # Try to find actual file via world_sources or user folder
            pass
        # If path is relative like "worlds/apworld.apworld" or "custom_worlds/x.apworld", try to resolve
        candidates = [Path(apworld_path)]
        try:
            import worlds
            for base in [getattr(worlds, "local_folder", None), getattr(worlds, "user_folder", None)]:
                if base:
                    candidates.append(Path(base) / Path(apworld_path).name)
                    candidates.append(Path(base) / apworld_path)
        except Exception:
            pass
        actual = None
        for cand in candidates:
            if cand.is_file():
                actual = cand
                break
        if actual is None or not actual.is_file():
            # Try direct
            actual = Path(apworld_path)
            if not actual.is_file():
                return None
        with zipfile.ZipFile(actual, "r") as zf:
            tops = set()
            for name in zf.namelist():
                if not name or name.startswith("/") or ".." in name.split("/"):
                    continue
                top = name.split("/")[0]
                if top and "/" in name:
                    tops.add(top)
                elif top and name.lower().endswith(".apworld"):
                    # Top-level apworld file, not a folder
                    continue
            namelist = set(zf.namelist())
            for top in list(tops):
                if f"{top}/__init__.py" not in namelist and f"{top}/__init__.pyc" not in namelist:
                    tops.discard(top)
            if len(tops) == 1:
                return next(iter(tops))
            return None
    except Exception:
        pass
    return None


def _is_generate_context() -> bool:
    try:
        from .launch_context import is_generate_context
        return is_generate_context()
    except Exception:
        try:
            import sys
            return any("Generate" in str(a) for a in sys.argv)
        except Exception:
            return False


def _prompt_rename_apworld(src_path: str, world_name: str, root_folder: str) -> bool:
    is_gen = _is_generate_context()
    msg = f'The APWorld {world_name} seems to expect to be named {root_folder}. Would you like to rename and try again?'
    if is_gen:
        try:
            ans = input(f"\n{msg} [y/N]: ").strip().lower()
            return ans in ("y", "yes")
        except (EOFError, OSError):
            logger.info(f"[APAPI:ready] {msg} (non-interactive, can't consent...)")
            return False
        except Exception:
            return False
    else:
        try:
            from Utils import messagebox
            # Use yesno via messagebox with error flag to get yes/no
            # messagebox returns None, but we can use a custom approach: use tkinter messagebox
            import tkinter.messagebox
            # Ensure Tk is available
            try:
                import tkinter
                root = tkinter.Tk()
                root.withdraw()
                res = tkinter.messagebox.askyesno("APWorld Name Mismatch", msg)
                root.destroy()
                return bool(res)
            except Exception:
                # Fallback to Utils.messagebox which is yes/no via Tk
                res = messagebox(f"{msg}\n\nAn error occurred during load recovery for {world_name}", "APWorld Rename", error=True)
                # Utils.messagebox doesn't return, so assume the user did not consent
                return False
        except Exception:
            try:
                from Utils import messagebox
                messagebox("Could not recover from error in load recovery for APWorld " + world_name, "APWorld Rename")
                return False
            except Exception:
                return False
    return False


def _prompt_replace_existing(target: str) -> bool:
    is_gen = _is_generate_context()
    msg = f"An APWorld named {target} already exists. Replace it?"
    if is_gen:
        try:
            ans = input(f"\n{msg} [y/N]: ").strip().lower()
            return ans in ("y", "yes")
        except (EOFError, OSError):
            return False
        except Exception:
            return False
    else:
        try:
            import tkinter.messagebox
            import tkinter
            root = tkinter.Tk()
            root.withdraw()
            res = tkinter.messagebox.askyesno("Replace APWorld", msg)
            root.destroy()
            return bool(res)
        except Exception:
            try:
                from Utils import messagebox
                messagebox(f"An error occurred while prompting to replace the existing APWorld named {target}", "Replace APWorld")
                return False
            except Exception:
                return False
    return False


def _try_reload_failed_worlds() -> None:
    try:
        import worlds
        raw_failed = list(getattr(worlds, "failed_world_loads", []))
        failed = list(dict.fromkeys(raw_failed))
        if len(failed) != len(raw_failed):
            worlds.failed_world_loads[:] = failed
        if not failed:
            return
        to_retry = [name for name in failed if name not in ("", None) and name not in _retried_failed_worlds]
        to_retry = list(dict.fromkeys(to_retry))
        if not to_retry:
            return
        for name in to_retry:
            _retried_failed_worlds.add(name)
        logger.info(f"[APAPI:ready] retrying {len(to_retry)} failed world(s) before ready: {to_retry}")
        dprint("ready", f"retrying failed worlds: {to_retry}")
        for world_name in to_retry[:]:
            try:
                src = None
                for s in getattr(worlds, "world_sources", []):
                    try:
                        if s.path.rsplit(".", 1)[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1] == world_name or s.path == world_name or s.path.startswith(world_name + "."):
                            src = s
                            break
                        from pathlib import Path
                        if Path(s.path).stem == world_name:
                            src = s
                            break
                    except Exception:
                        continue
                if src is None:
                    continue
                # Check for misnamed apworld (root folder vs file stem)
                try:
                    root_folder = _get_apworld_root_folder(src.resolved_path if hasattr(src, "resolved_path") else src.path)
                    file_stem = None
                    try:
                        from pathlib import Path
                        file_stem = Path(src.path).stem
                        # For is_zip relative, need resolved
                        if hasattr(src, "resolved_path"):
                            file_stem = Path(src.resolved_path).stem
                    except Exception:
                        file_stem = world_name
                    if root_folder and file_stem and root_folder != file_stem and root_folder != world_name:
                        # Misnamed: file is wrong_name.apworld but expects root_folder
                        if _prompt_rename_apworld(src.path, file_stem, root_folder):
                            try:
                                from pathlib import Path
                                import shutil
                                # Determine actual file paths
                                src_file = Path(src.resolved_path if hasattr(src, "resolved_path") else src.path)
                                # Find base folder for apworlds
                                base_dir = src_file.parent
                                # Try to find correct base (worlds or custom_worlds)
                                # Use src_file's parent
                                target = base_dir / f"{root_folder}.apworld"
                                if target.exists():
                                    if not _prompt_replace_existing(str(target)):
                                        logger.info(f"[APAPI:ready] rename skipped for {world_name} -> {root_folder} (target exists, user declined replace)")
                                        continue
                                    try:
                                        target.unlink()
                                    except Exception:
                                        pass
                                # Try to rename/move
                                try:
                                    src_file.rename(target)
                                    logger.info(f"[APAPI:ready] renamed {src_file.name} -> {target.name} for {world_name}")
                                except Exception:
                                    shutil.copyfile(src_file, target)
                                    try:
                                        src_file.unlink()
                                    except Exception:
                                        pass
                                # Update WorldSource path
                                try:
                                    src.path = str(target) if getattr(src, "relative", False) else str(target)
                                    # For relative, need relative to local_folder
                                    if getattr(src, "relative", False):
                                        try:
                                            import worlds as _w
                                            base_local = _w.local_folder
                                            src.path = str(Path(target).relative_to(base_local)) if str(target).startswith(str(base_local)) else target.name
                                        except Exception:
                                            src.path = target.name
                                except Exception:
                                    pass
                                # Update failed list name
                                try:
                                    worlds.failed_world_loads.remove(world_name)
                                    if root_folder not in worlds.failed_world_loads:
                                        worlds.failed_world_loads.append(root_folder)
                                except Exception:
                                    pass
                                world_name = root_folder
                                # Now retry with corrected src
                            except Exception as e:
                                logger.warning(f"[APAPI:ready] rename failed for {world_name} -> {root_folder}: {e}")
                            # Fall through to retry load below
                except Exception as me:
                    logger.debug(f"[APAPI:ready] misname check failed for {world_name}: {me}")
                if src.load():
                    try:
                        worlds.failed_world_loads.remove(world_name)
                    except ValueError:
                        pass
                    # Also try to remove any old misnamed entry
                    try:
                        for n in list(worlds.failed_world_loads):
                            if n != world_name:
                                # Check if this was the misnamed one
                                pass
                    except Exception:
                        pass
                    logger.info(f"[APAPI:ready] retry succeeded for {world_name}")
                    dprint("ready", f"retry succeeded for {world_name}")
                else:
                    logger.debug(f"[APAPI:ready] retry still failed for {world_name}")
            except Exception as e:
                logger.debug(f"[APAPI:ready] retry failed for {world_name}: {e}")
    except Exception as e:
        logger.debug(f"[APAPI:ready] _try_reload_failed_worlds failed: {e}")



def _poll_worker() -> None:
    """Input: None. Returns: None (polls until ready/timeout)."""
    start: float = time.perf_counter()
    while True:
        time.sleep(_POLL_INTERVAL)
        with _queue_lock:
            if worlds_loading_complete():
                _try_reload_failed_worlds()
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
                _try_reload_failed_worlds()
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
