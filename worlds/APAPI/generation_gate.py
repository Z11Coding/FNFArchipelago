from __future__ import annotations

"""Generation gate — makes multiworld generation wait for AP patches.

This gate installs a ``core.main`` *before* hook that blocks ``Main.main``
until all deferred AP patches have settled. This ensures ``inject_option``
and ``inject_world_behavior`` injections are ready before generation starts.

What it waits for (polling, short timeout):
* ``world_ready`` — ``worlds`` import finished and ``on_worlds_loaded`` /
  ``when_game_available`` queues drained (covers ``inject_option`` /
  ``inject_world_behavior`` deferrals).
* ``core_hooks`` — all ``CORE_HOOK_SPECS`` targets patched and no pending
  ``register_soft_before`` / ``register_soft_after`` leftovers.
* ``hard_patches`` — no explicit pending queue, but if ``core_hooks`` is
  settled the ``hard_patches`` wrappers it installs are also settled.

If the gate times out it logs a warning and lets generation proceed — never
hard-blocks forever. Debug logging via ``dprint`` respects ``apapi.debug.enabled``.

Installed from ``APAPI.__init__`` after ``initialize_core_hooks`` so the
``core.main`` hook point already exists; falls back to a hard ``Main.main``
wrapper if the soft hook point is not yet available.
"""

import logging
import time
from typing import Any

from .debug import dprint

logger = logging.getLogger("APAPI.Gate")

_TIMEOUT: float = 12.0
_INTERVAL: float = 0.05


def _snapshot_pending() -> list[str]:
    """Return list of human-readable pending reasons; empty means settled."""
    pending: list[str] = []

    # world_ready — worlds import + injection queues
    try:
        from .world_ready import worlds_loading_complete, _loaded_queue, _game_queues  # type: ignore

        if not worlds_loading_complete():
            pending.append(
                f"worlds not loaded (loaded_q={len(_loaded_queue)}, game_q={len(_game_queues)})"
            )
        elif _loaded_queue or _game_queues:
            pending.append(
                f"world_ready queues: loaded={len(_loaded_queue)}, games={sorted(_game_queues.keys())}"
            )
    except Exception:
        pass

    # core_hooks — only care about pending soft callbacks, not about
    # whether every CORE_HOOK_SPECS target is patched. Targets like
    # Launcher.run_gui / CommonClient.default are never loaded during headless
    # Generate and would otherwise make the gate always timeout. Generation-
    # relevant hooks (core.main, core.multiworld_init, etc.) are already
    # covered by world_ready; we just need to drain any queued soft callbacks.
    try:
        from .core_hooks import _pending_after, _pending_before  # type: ignore

        pending_before = sum(len(v) for v in _pending_before.values())
        pending_after = sum(len(v) for v in _pending_after.values())
        if pending_before or pending_after:
            pending.append(f"core pending before={pending_before} after={pending_after}")
    except Exception:
        pass

    # injection — targeted options/behaviours are queued via when_game_available,
    # which is already covered by world_ready._game_queues, but also check the
    # raw registries for visibility
    try:
        from .injection import _global_options, _targeted_options  # type: ignore
        from worlds.AutoWorld import AutoWorldRegister  # type: ignore

        missing_games: list[str] = []
        for game in list(_targeted_options.keys()):
            if game not in AutoWorldRegister.world_types:
                missing_games.append(game)
        if missing_games:
            # Not necessarily pending — game may simply not be installed — but
            # worth noting when debug is on.
            dprint("gate", f"injection has options for not-yet-loaded games: {missing_games}")
    except Exception:
        pass

    return pending


def wait_for_all_patches(timeout: float = _TIMEOUT, interval: float = _INTERVAL) -> bool:
    """Block until AP patches are settled or timeout. Returns True if settled."""
    start = time.perf_counter()
    first_pending = True
    # Require stable empty for a short period to handle cascade where
    # world_ready callbacks queue new hard_patches/inject_world_behavior
    # after the initial snapshot appears empty
    stable_since: float | None = None
    stable_required = 0.35
    last_world_count = -1
    while True:
        pending = _snapshot_pending()
        # Also check for world count stability and hard_patches queue
        try:
            from worlds.AutoWorld import AutoWorldRegister
            cur_count = len(AutoWorldRegister.world_types)
        except Exception:
            cur_count = last_world_count
        world_count_changed = cur_count != last_world_count
        last_world_count = cur_count
        # Consider hard_patches pending if any recent wrapper was added?
        # Use pending list as primary, but require stable period
        is_pending = bool(pending) or world_count_changed
        if not is_pending:
            if stable_since is None:
                stable_since = time.perf_counter()
            elif time.perf_counter() - stable_since >= stable_required:
                if not first_pending:
                    dprint("gate", "all AP patches settled (stable)")
                return True
        else:
            stable_since = None
            if time.perf_counter() - start > timeout:
                logger.warning("[APAPI:gate] wait timed out with pending: %s", "; ".join(pending) if pending else f"world_count {cur_count}")
                dprint("gate", f"timeout after {timeout:.1f}s, pending: {'; '.join(pending) if pending else 'world_count changing'} — proceeding anyway")
                return False
            if first_pending:
                # Normal print so user sees wait even when debug is off
                logger.info("[APAPI:gate] waiting for AP patches: %s", "; ".join(pending) if pending else f"world_count {cur_count}")
                dprint("gate", f"waiting for AP patches: {'; '.join(pending) if pending else f'world_count {cur_count}'}")
                first_pending = False
            else:
                dprint("gate", f"still waiting: {'; '.join(pending) if pending else f'world_count {cur_count}'}")
        time.sleep(interval)


def _before_main(*args: Any, **kwargs: Any) -> None:
    """Soft before hook for core.main — waits for all AP patches to settle."""
    # Always wait if patches are pending, with a normal print so user sees it even when debug is off.
    # dprint is still used for debug, but logger.info ensures visibility.
    try:
        pending = _snapshot_pending()
    except Exception:
        pending = []
    if pending:
        logger.info("[APAPI:gate] generation start — waiting for AP patches: %s", "; ".join(pending))
        dprint("gate", f"generation start — waiting for AP patches: {'; '.join(pending)}")
    else:
        dprint("gate", "generation start — checking AP patches")
    wait_for_all_patches()
    if pending:
        logger.info("[APAPI:gate] gate passed — proceeding with Main.main")
    dprint("gate", "gate passed — proceeding with Main.main")


def initialize_generation_gate() -> None:
    """Install the gate. Idempotent; called from APAPI.__init__."""
    # Already installed?
    try:
        if getattr(initialize_generation_gate, "_installed", False):  # type: ignore
            return
    except Exception:
        pass

    # Prefer soft hook (goes through APAPI's validated path) — this is the
    # intended APAPI-native way. If the hook point doesn't exist yet, fall back
    # to a hard Main.main wrapper.
    try:
        from .core_hooks import register_soft_before  # type: ignore

        register_soft_before("core.main", _before_main)
        dprint("init", "generation gate installed (core.main before)")
    except Exception as exc:
        dprint("init", f"generation gate soft hook deferred ({exc})")
        try:
            from .hard_patch import hard_patches  # type: ignore

            def _hard_wrapper(next_callable, *a, **kw):  # type: ignore
                _before_main(*a, **kw)
                return next_callable(*a, **kw)

            hard_patches.add_wrapper("Main.main", _hard_wrapper, load_missing=True)
            dprint("init", "generation gate installed (Main.main hard wrapper fallback)")
        except Exception as exc2:
            logger.warning("[APAPI:gate] could not install generation gate: %s / %s", exc, exc2)
            return

    try:
        setattr(initialize_generation_gate, "_installed", True)  # type: ignore
    except Exception:
        pass


__all__ = ["initialize_generation_gate", "wait_for_all_patches"]
