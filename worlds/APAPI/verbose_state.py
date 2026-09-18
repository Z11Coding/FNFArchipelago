from __future__ import annotations

"""APAPI Fill Diagnostic – lightweight, works for any game.

Enable via host.yaml:
  apapi:
    verbose_collection_state:
      enabled: true

On Fill.FillError it writes output/fill_diagnostic_<seed>.txt with:
- spheres (logic_api.sphere_summary_with_inventory) for actual generation
- blockades (first_blockades) with has/can_reach detail
- completion per player (has_beaten/can_beat_game) and mystery custom goal token/item counts
- state summary (checked/advancements)

No VerboseCollectionState, no per-predicate logging – just APAPI logic_api + get_all_state,
so it does not freeze and works for any world.
"""

import logging
import traceback
import time
from pathlib import Path
from typing import Any, Dict, List

from BaseClasses import MultiWorld
from .host_config import ensure_apapi_config_exists
from .debug import dprint

logger = logging.getLogger("APAPI.VerboseState")

VERBOSE_DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "report_on_fill_error": True,
    "ask_force_continue": False,
}

_CFG_CACHE = None
_CFG_CACHE_TIME = 0.0

def _get_cfg():
    global _CFG_CACHE, _CFG_CACHE_TIME
    now = time.time()
    if _CFG_CACHE is not None and now - _CFG_CACHE_TIME < 1.0:
        return _CFG_CACHE
    try:
        cfg = ensure_apapi_config_exists()
        apapi = cfg.get("apapi", {}) if isinstance(cfg, dict) else {}
        v = apapi.get("verbose_collection_state", {}) if isinstance(apapi, dict) else {}
        eff = dict(VERBOSE_DEFAULTS)
        if isinstance(v, dict):
            eff.update(v)
        elif isinstance(v, bool):
            eff["enabled"] = bool(v)
        _CFG_CACHE = eff
        _CFG_CACHE_TIME = now
        return eff
    except Exception:
        return dict(VERBOSE_DEFAULTS)

_FORCE_ENABLED = False

def is_enabled() -> bool:
    if _FORCE_ENABLED:
        return True
    return bool(_get_cfg().get("enabled", False))

def enable_verbose() -> None:
    global _FORCE_ENABLED
    _FORCE_ENABLED = True
    try:
        import yaml
        from pathlib import Path as P
        from Utils import user_path
        p = P(user_path("host.yaml"))
        data = {}
        if p.exists():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
        if "apapi" not in data or not isinstance(data["apapi"], dict):
            data["apapi"] = {}
        data["apapi"]["verbose_collection_state"] = {"enabled": True}
        p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    except Exception:
        pass

def _ensure_dirs():
    from Utils import user_path
    out = Path(user_path("output"))
    logs = Path(user_path("logs"))
    out.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    return out, logs

def generate_report(multiworld: MultiWorld, exception: BaseException | None = None) -> Path:
    out_dir, _ = _ensure_dirs()
    seed = getattr(multiworld, "seed_name", str(getattr(multiworld, "seed", "unknown")))
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"fill_diagnostic_{seed}_{ts}.txt"
    try:
        state = multiworld.get_all_state()
        state_err = None
    except Exception as e:
        state = None
        state_err = f"{e}\n{traceback.format_exc()}"

    lines: List[str] = []
    lines.append("="*80)
    lines.append(f"APAPI Fill Diagnostic – Seed: {seed}  Players: {multiworld.players}")
    lines.append(f"Games: {', '.join(f'P{pid}:{multiworld.game[pid]}' for pid in multiworld.player_ids)}")
    lines.append("="*80)
    if exception:
        lines.append(f"\nFillError: {exception}")
        lines.append("".join(traceback.format_exception(type(exception), exception, exception.__traceback__)[-8:]))
    if state_err:
        lines.append(f"\n[get_all_state failed]: {state_err}")

    lines.append("\n" + "="*80)
    lines.append("COMPLETION (actual multiworld)")
    lines.append("="*80)
    for pid in multiworld.player_ids:
        try:
            world = multiworld.worlds[pid]
            name = multiworld.player_name[pid]
            game = multiworld.game[pid]
            cur = state if state else multiworld.get_all_state()
            try:
                beaten = multiworld.has_beaten_game(cur, pid)
            except Exception as e:
                beaten = f"ERR {e}"
            try:
                beatable = multiworld.can_beat_game(cur)
            except Exception as e:
                beatable = f"ERR {e}"
            lines.append(f"P{pid} {name} [{game}]: has_beaten={beaten} can_beat={beatable}")
            # mystery custom goal detail
            try:
                from worlds.mystery_game.custom_goal import _get_custom_goal_data
                cg = _get_custom_goal_data(world)
                if cg.get("enabled"):
                    from worlds.mystery_game.puzzles import CUSTOM_GOAL_TOKEN_ITEM
                    have = cur.count(CUSTOM_GOAL_TOKEN_ITEM, pid)
                    need = len(cg.get("locations", []))
                    missing = [l for l in cg.get("locations", []) if l not in [x.name for x in cur.locations_checked if x.player == pid]]
                    lines.append(f"  tokens: have {have}/{need} missing: {missing[:5]}")
                    for it, nd in cg.get("items", {}).items():
                        hv = cur.count(it, pid)
                        lines.append(f"    {it}: {hv}/{nd} {'MISSING' if hv < nd else 'OK'}")
            except Exception:
                pass
        except Exception as e:
            lines.append(f" P{pid} ERR {e}")

    try:
        from .logic_api import sphere_summary_with_inventory, first_blockades
        for pid in multiworld.player_ids:
            try:
                spheres = sphere_summary_with_inventory(multiworld, pid, max_spheres=20)
                lines.append(f"\n-- P{pid} {multiworld.player_name[pid]} --")
                for sph in spheres[:10]:
                    if sph["newly_reachable"]:
                        lines.append(f"  Sphere {sph['sphere']}: {', '.join(sph['newly_reachable'][:12])} ({len(sph['newly_reachable'])} new)")
                block = first_blockades(multiworld, pid, limit=15)
                if block:
                    lines.append(f"  Blocked ({len(block)}):")
                    for b in block:
                        lines.append(f"    - {b['location']} [{b['region']}]")
                        try:
                            loc = multiworld.get_location(b["location"], pid)
                            # quick has check for this loc
                            if state:
                                # try to see which has fails by checking rule directly
                                # we just show that it's not reachable
                                lines.append(f"      can_reach: {state.can_reach(loc)}  checked: {loc in state.locations_checked}")
                        except Exception:
                            pass
                else:
                    lines.append(f"  No blockades")
            except Exception as e:
                lines.append(f" spheres failed P{pid}: {e}")
    except Exception as e:
        lines.append(f" logic_api failed: {e}")

    if state is not None:
        try:
            lines.append(f"\n--- State ---")
            for pid in multiworld.player_ids:
                chk = len([l for l in state.locations_checked if l.player == pid])
                tot = len(list(multiworld.get_locations(pid)))
                lines.append(f" P{pid}: checked {chk}/{tot}  advancements {len([l for l in state.advancements if l.player==pid])}")
        except Exception as e:
            lines.append(f" state failed: {e}")

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.warning("APAPI Fill Diagnostic written to %s", path)
    dprint("verbose_state", f"report {path}")
    return path

def _install_hooks():
    try:
        import Main, Fill
        from BaseClasses import MultiWorld as _MW
        # Always wrap Fill/Main to generate report on FillError, verbose flag only controls extra logging
        try:
            import Main as _Main
            _orig = _Main.main
            def _wm(*a, **kw):
                try:
                    return _orig(*a, **kw)
                except Exception as e:
                    from Fill import FillError
                    if isinstance(e, FillError):
                        mw = getattr(e, "multiworld", None)
                        if mw is None:
                            try:
                                from .multiworld_api import get_current_multiworld
                                mw = get_current_multiworld()
                            except Exception:
                                pass
                        if mw is None and a and hasattr(a[0], "player_ids"):
                            mw = a[0]
                        if mw is not None:
                            try:
                                generate_report(mw, e)
                            except Exception:
                                pass
                    raise
            _Main.main = _wm
        except Exception:
            pass
        try:
            import Fill as _F
            _orig2 = _F.distribute_items_restrictive
            def _wf(*a, **kw):
                try:
                    return _orig2(*a, **kw)
                except Exception as e:
                    from Fill import FillError
                    if isinstance(e, FillError):
                        mw = getattr(e, "multiworld", None)
                        if mw is None and a and hasattr(a[0], "player_ids"):
                            mw = a[0]
                        if mw is not None:
                            try:
                                generate_report(mw, e)
                            except Exception:
                                pass
                    raise
            _F.distribute_items_restrictive = _wf
        except Exception:
            pass
        ensure_apapi_config_exists()
    except Exception:
        pass

try:
    _install_hooks()
except Exception:
    pass
try:
    ensure_apapi_config_exists()
except Exception:
    pass

__all__ = ["is_enabled", "enable_verbose", "generate_report"]
