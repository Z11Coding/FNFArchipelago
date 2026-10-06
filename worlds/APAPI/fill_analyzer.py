from __future__ import annotations

"""APAPI Fill Analyzer — figures out *what* is preventing a fill.

When a ``Fill.FillError`` escapes, the raw message lists unplaced items /
unfilled locations but never says *why* no placement was legal. This tool
runs a lightweight differential analysis on the live ``MultiWorld``:

* builds a max-exploration state (current state + all remaining itempool)
* classifies each unfilled location as reachable-now / reachable-with-all-items /
  unreachable-even-with-all-items (logic dead-end)
* for each unplaced progression item, counts how many unfilled locations would
  still accept it, and splits rejections into item_rule vs access failures
* inspects the actual ``access_rule``/``item_rule`` function sources
  (via ``inspect``) to name the items each blocked rule is waiting on and
  show where the rule was defined (file:line)
* checks raw capacity: whether there are literally more unplaced items
  (progression, or overall) than unfilled locations that can take them
* greedily finds which missing item(s) would unlock a blocked location
* reports per-player progression-vs-location balance and completion status

Entry points:
    analyze_fill_error(multiworld, exception) -> FillDiagnosis
    format_fill_diagnosis(diag) -> str
    diagnose_and_format(multiworld, exception) -> str
    attach_diagnosis_to_exception(exc, text) -> exc
"""

import traceback
from dataclasses import dataclass, field
from typing import Any

import logging

logger = logging.getLogger("APAPI.FillAnalyzer")

FILL_ANALYZER_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "max_unplaced_items": 8,
    "max_unfilled_locations": 12,
    "max_examples_per_item": 5,
    "include_spheres": True,
    "inspect_rules": True,
    "max_rule_details": 6,
}


def _get_cfg() -> dict[str, Any]:
    try:
        from .host_config import ensure_apapi_config_exists
        cfg = ensure_apapi_config_exists()
        apapi = cfg.get("apapi", {}) if isinstance(cfg, dict) else {}
        v = apapi.get("fill_analyzer", {}) if isinstance(apapi, dict) else {}
        eff = dict(FILL_ANALYZER_DEFAULTS)
        if isinstance(v, dict):
            eff.update({k: v[k] for k in eff if k in v})
        elif isinstance(v, bool):
            eff["enabled"] = bool(v)
        return eff
    except Exception:
        return dict(FILL_ANALYZER_DEFAULTS)


def is_enabled() -> bool:
    return bool(_get_cfg().get("enabled", True))


@dataclass
class BlockedLocationInfo:
    player: int
    name: str
    region: str | None
    reachable_now: bool
    reachable_with_all_items: bool
    progress_type: str = ""
    needed_items: list[str] = field(default_factory=list)


@dataclass
class UnplacedItemInfo:
    player: int
    name: str
    advancement: bool
    acceptable_count: int = 0
    rule_rejects: int = 0
    access_rejects: int = 0
    example_ok: list[str] = field(default_factory=list)
    example_rule_blocked: list[str] = field(default_factory=list)
    example_access_blocked: list[str] = field(default_factory=list)


@dataclass
class RuleRequirement:
    """What one blocked rule function is technically waiting on."""

    location: str
    player: int
    kind: str  # "access_rule" or "item_rule"
    origin: str = ""  # file:line of the rule function, when resolvable
    source_snippet: str = ""  # first lines of the rule source, truncated
    # (item_name, have_now, have_with_all) for string literals found in
    # state.has/has_all/count/has_group calls inside the rule source.
    required_items: list[tuple[str, int, int]] = field(default_factory=list)
    missing_now: list[str] = field(default_factory=list)


@dataclass
class CapacityInfo:
    """Raw item-vs-location-slot arithmetic."""

    unplaced_progression: int = 0
    unplaced_total: int = 0
    unfilled_total: int = 0
    unfilled_by_player: dict[int, int] = field(default_factory=dict)
    prog_unplaced_by_player: dict[int, int] = field(default_factory=dict)
    overflow_progression: bool = False
    overflow_total: bool = False


@dataclass
class FillDiagnosis:
    seed: str
    players: int
    games: dict[int, str]
    exception_summary: str
    unplaced_count: int
    unfilled_count: int
    completion: dict[int, str] = field(default_factory=dict)
    blocked: list[BlockedLocationInfo] = field(default_factory=list)
    unplaced: list[UnplacedItemInfo] = field(default_factory=list)
    likely_causes: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    unreachable_even_with_all: int = 0
    rules: list[RuleRequirement] = field(default_factory=list)
    capacity: CapacityInfo = field(default_factory=CapacityInfo)


def _short(obj: Any, limit: int = 120) -> str:
    try:
        s = str(obj)
    except Exception:
        s = repr(obj)
    return s if len(s) <= limit else s[:limit] + "..."


_HAS_CALL_RE = None  # compiled lazily (keeps import cheap)


def _get_has_call_re():
    global _HAS_CALL_RE
    if _HAS_CALL_RE is None:
        import re
        # Matches state.has("Item"), state.has_all([...]), state.count("Item", ...),
        # state.has_group(...), and bare has("Item") inside rule lambdas.
        _HAS_CALL_RE = re.compile(
            r"""(?:state\s*\.\s*)?(?:has|has_all|has_group|count)\s*\(\s*"""
            r"""(?P<first>"[^"]+"|'[^']+'|\[[^\]]*\])""",
            re.VERBOSE,
        )
    return _HAS_CALL_RE


def _extract_item_literals(source: str) -> list[str]:
    """Pull item-name string literals out of state.has*/count calls in rule source."""
    import re
    try:
        names: list[str] = []
        for m in _get_has_call_re().finditer(source):
            first = m.group("first").strip()
            # has_all(["A", "B"]) style list literal
            if first.startswith("["):
                for lit in re.findall(r'"([^"]+)"|\'([^\']+)\'', first):
                    name = lit[0] or lit[1]
                    if name and name not in names:
                        names.append(name)
            else:
                name = first[1:-1]  # strip quotes
                if name and name not in names:
                    names.append(name)
        return names
    except Exception:
        return []


def _rule_origin(func: Any) -> str:
    try:
        import inspect
        src_file = inspect.getsourcefile(func) or "?"
        try:
            _, first_line = inspect.getsourcelines(func)
        except Exception:
            first_line = "?"
        return f"{src_file}:{first_line}"
    except Exception:
        return ""


def _rule_snippet(func: Any, max_lines: int = 6, max_chars: int = 600) -> str:
    try:
        import inspect
        src = inspect.getsource(func)
        lines = [ln.strip() for ln in src.splitlines() if ln.strip()][:max_lines]
        snippet = " | ".join(lines)
        return snippet if len(snippet) <= max_chars else snippet[:max_chars] + "..."
    except Exception:
        # Builtins / dynamically generated rules have no source.
        return ""


def _inspect_rule(loc: Any, kind: str, cur_state: Any, max_state: Any) -> RuleRequirement | None:
    """Inspect one rule function: source, origin, and which required items are missing.

    Never raises; returns None when there is nothing useful to report.
    """
    try:
        name = getattr(loc, "name", "?")
        player = getattr(loc, "player", 0)
        func = getattr(loc, kind, None)
        if not callable(func):
            return None
        origin = _rule_origin(func)
        snippet = _rule_snippet(func)
        if not snippet:
            return None  # nothing to show beyond what differential analysis says
        required: list[tuple[str, int, int]] = []
        missing: list[str] = []
        for item_name in _extract_item_literals(snippet):
            try:
                have_now = cur_state.count(item_name, player) if cur_state is not None else 0
            except Exception:
                have_now = 0
            try:
                have_max = max_state.count(item_name, player) if max_state is not None else have_now
            except Exception:
                have_max = have_now
            try:
                required.append((item_name, int(have_now), int(have_max)))
            except Exception:
                continue
            if have_now == 0:
                missing.append(item_name)
        if not required and not snippet:
            return None
        return RuleRequirement(
            location=name, player=player, kind=kind, origin=origin,
            source_snippet=snippet, required_items=required[:8], missing_now=missing[:8],
        )
    except Exception as e:
        logger.debug("APAPI fill analyzer rule inspection failed: %s", e)
        return None


def _build_capacity(mw: Any, remaining_pool: list, unfilled: list) -> CapacityInfo:
    try:
        from collections import Counter
        prog_by_player: Counter = Counter()
        prog_total = 0
        for item in remaining_pool:
            if getattr(item, "advancement", False):
                prog_total += 1
                try:
                    prog_by_player[getattr(item, "player", 0)] += 1
                except Exception:
                    pass
        unfilled_by_player: Counter = Counter()
        for loc in unfilled:
            try:
                unfilled_by_player[getattr(loc, "player", 0)] += 1
            except Exception:
                pass
        return CapacityInfo(
            unplaced_progression=prog_total,
            unplaced_total=len(remaining_pool),
            unfilled_total=len(unfilled),
            unfilled_by_player=dict(unfilled_by_player),
            prog_unplaced_by_player=dict(prog_by_player),
            overflow_progression=prog_total > len(unfilled),
            overflow_total=len(remaining_pool) > len(unfilled),
        )
    except Exception:
        return CapacityInfo()


def _resolve_multiworld(multiworld: Any, exception: BaseException | None):
    if multiworld is not None and hasattr(multiworld, "player_ids"):
        return multiworld
    # FillError drops the multiworld kwarg after formatting; try fallbacks
    for attr in ("multiworld", "mw"):
        try:
            cand = getattr(exception, attr, None)
            if cand is not None and hasattr(cand, "player_ids"):
                return cand
        except Exception:
            continue
    try:
        from .multiworld_api import get_current_multiworld
        cand = get_current_multiworld()
        if cand is not None and hasattr(cand, "player_ids"):
            return cand
    except Exception:
        pass
    return None


def analyze_fill_error(multiworld: Any = None, exception: BaseException | None = None) -> FillDiagnosis:
    """Run differential fill analysis. Never raises — returns best-effort diagnosis."""
    cfg = _get_cfg()
    max_items: int = int(cfg.get("max_unplaced_items", 8))
    max_locs: int = int(cfg.get("max_unfilled_locations", 12))
    max_examples: int = int(cfg.get("max_examples_per_item", 5))

    mw = _resolve_multiworld(multiworld, exception)
    exc_summary = _short(exception, 300) if exception else "unknown FillError"
    if mw is None:
        return FillDiagnosis(
            seed="unknown", players=0, games={},
            exception_summary=exc_summary, unplaced_count=0, unfilled_count=0,
            likely_causes=["Could not resolve MultiWorld from FillError; "
                           "attach multiworld=multiworld when raising or run during generation."],
            suggestions=["Re-run with the failing multiworld still alive so APAPI can inspect it."],
        )

    try:
        seed = str(getattr(mw, "seed_name", getattr(mw, "seed", "unknown")))
    except Exception:
        seed = "unknown"
    try:
        players = int(getattr(mw, "players", len(list(getattr(mw, "player_ids", [])))))
    except Exception:
        players = 0
    games: dict[int, str] = {}
    try:
        for pid in list(getattr(mw, "player_ids", [])):
            try:
                games[pid] = str(mw.game[pid])
            except Exception:
                games[pid] = "?"
    except Exception:
        pass

    # --- snapshots ---
    try:
        unfilled = list(mw.get_unfilled_locations())
    except Exception:
        unfilled = []
    try:
        remaining_pool = list(getattr(mw, "itempool", []))
    except Exception:
        remaining_pool = []

    capacity = _build_capacity(mw, remaining_pool, unfilled)

    # current state vs max-exploration state (current + everything left in pool)
    cur_state = None
    max_state = None
    try:
        from Fill import sweep_from_pool
        base = getattr(mw, "state", None)
        if base is not None:
            try:
                max_state = sweep_from_pool(base, list(remaining_pool))
            except Exception:
                max_state = None
        if max_state is None:
            try:
                max_state = mw.get_all_state()
            except Exception:
                max_state = None
        try:
            cur_state = base.copy() if base is not None and hasattr(base, "copy") else None
            if cur_state is not None:
                try:
                    cur_state.sweep_for_advancements()
                except Exception:
                    pass
        except Exception:
            cur_state = None
    except Exception:
        pass

    # completion per player (using max state — "beatable even if filled?")
    completion: dict[int, str] = {}
    try:
        probe = max_state if max_state is not None else cur_state
        if probe is not None:
            for pid in list(getattr(mw, "player_ids", [])):
                try:
                    beaten = mw.has_beaten_game(probe, pid)
                    completion[pid] = "beaten" if beaten else "not-beaten"
                except Exception as e:
                    completion[pid] = f"ERR {e}"
    except Exception:
        pass

    # --- classify unfilled locations ---
    blocked: list[BlockedLocationInfo] = []
    unreachable_count = 0
    try:
        for loc in unfilled[:max_locs * 3]:  # scan a bit more, keep top max_locs
            try:
                r_now = bool(loc.can_reach(cur_state)) if cur_state is not None else False
            except Exception:
                r_now = False
            try:
                r_max = bool(loc.can_reach(max_state)) if max_state is not None else r_now
            except Exception:
                r_max = r_now
            if r_now:
                continue  # reachable now — not the blocker (fill chose not to use it: rule issue, handled below)
            if not r_max:
                unreachable_count += 1
            try:
                region = loc.parent_region.name if loc.parent_region else None
            except Exception:
                region = None
            try:
                pt = str(getattr(loc, "progress_type", ""))
            except Exception:
                pt = ""
            blocked.append(BlockedLocationInfo(
                player=getattr(loc, "player", 0), name=getattr(loc, "name", "?"),
                region=region, reachable_now=r_now,
                reachable_with_all_items=r_max, progress_type=pt,
            ))
            if len(blocked) >= max_locs:
                break
    except Exception as e:
        logger.debug("APAPI fill analyzer location scan failed: %s", e)

    # For blocked-but-reachable-with-all-items, greedily find which pool items unlock it.
    try:
        prog_pool = [i for i in remaining_pool if getattr(i, "advancement", False)]
        for b in blocked:
            if b.reachable_now or not b.reachable_with_all_items:
                continue
            try:
                loc = mw.get_location(b.name, b.player)
            except Exception:
                continue
            needed: list[str] = []
            try:
                from Fill import sweep_from_pool as _sweep
                trial_items: list[Any] = []
                # greedy: add pool items one at a time until reachable (cap 4 rounds)
                trial_state = cur_state.copy() if cur_state is not None and hasattr(cur_state, "copy") else None
                if trial_state is None:
                    continue
                for _round in range(4):
                    found = False
                    for item in prog_pool:
                        if item in trial_items:
                            continue
                        probe_state = trial_state.copy()
                        try:
                            probe_state.collect(item, True)
                            probe_state.sweep_for_advancements()
                        except Exception:
                            continue
                        try:
                            if loc.can_reach(probe_state):
                                trial_items.append(item)
                                needed.append(f"{item.name} (P{item.player})")
                                found = True
                                break
                        except Exception:
                            continue
                    if found:
                        break
                    # no single item unlocks it; commit the item that expands reach most, then retry
                    best = None
                    best_reach = -1
                    for item in prog_pool:
                        if item in trial_items:
                            continue
                        try:
                            ps = trial_state.copy()
                            ps.collect(item, True)
                            ps.sweep_for_advancements()
                            n = len(mw.get_reachable_locations(ps))
                        except Exception:
                            continue
                        if n > best_reach:
                            best_reach = n
                            best = item
                    if best is None:
                        break
                    trial_items.append(best)
                    try:
                        trial_state.collect(best, True)
                        trial_state.sweep_for_advancements()
                    except Exception:
                        break
                    try:
                        if loc.can_reach(trial_state):
                            needed.append(f"{best.name} (P{best.player})")
                            break
                    except Exception:
                        break
                # record what we committed beyond the final unlocker
                for t in trial_items:
                    label = f"{t.name} (P{t.player})"
                    if label not in needed:
                        needed.append(label)
            except Exception:
                pass
            b.needed_items = needed[:4]
    except Exception:
        pass

    # --- inspect the actual rule functions behind the blockages ---
    rule_details: list[RuleRequirement] = []
    try:
        if bool(cfg.get("inspect_rules", True)):
            max_rules: int = int(cfg.get("max_rule_details", 6))
            seen_rules: set = set()
            # access_rule of each sampled blocked location
            for b in blocked:
                if len(rule_details) >= max_rules:
                    break
                try:
                    loc = mw.get_location(b.name, b.player)
                except Exception:
                    continue
                try:
                    key = (b.player, b.name, "access_rule")
                    if key in seen_rules:
                        continue
                    seen_rules.add(key)
                    req = _inspect_rule(loc, "access_rule", cur_state, max_state)
                    if req is not None:
                        rule_details.append(req)
                except Exception:
                    continue
    except Exception as e:
        logger.debug("APAPI fill analyzer access-rule inspection failed: %s", e)

    # --- classify unplaced items ---
    unplaced_infos: list[UnplacedItemInfo] = []
    try:
        # progression first — those are what actually fail fills
        ordered = sorted(remaining_pool, key=lambda i: (not getattr(i, "advancement", False), str(getattr(i, "name", ""))))
        for item in ordered[:max_items]:
            info = UnplacedItemInfo(
                player=getattr(item, "player", 0), name=getattr(item, "name", "?"),
                advancement=bool(getattr(item, "advancement", False)),
            )
            try:
                probe_state = max_state if max_state is not None else cur_state
                for loc in unfilled:
                    if len(info.example_ok) >= max_examples and info.rule_rejects + info.access_rejects > max_examples * 2:
                        # keep counting cheaply but stop storing
                        pass
                    try:
                        # item_rule-only check first (no access), then full check
                        rule_ok = bool(loc.item_rule(item))
                    except Exception:
                        rule_ok = True  # fail-open: don't blame the rule on introspection errors
                    if not rule_ok:
                        info.rule_rejects += 1
                        if len(info.example_rule_blocked) < max_examples:
                            info.example_rule_blocked.append(f"P{loc.player} {loc.name}")
                        continue
                    try:
                        if probe_state is not None and loc.can_fill(probe_state, item, True):
                            info.acceptable_count += 1
                            if len(info.example_ok) < max_examples:
                                info.example_ok.append(f"P{loc.player} {loc.name}")
                        else:
                            info.access_rejects += 1
                            if len(info.example_access_blocked) < max_examples:
                                info.example_access_blocked.append(f"P{loc.player} {loc.name}")
                    except Exception:
                        info.access_rejects += 1
            except Exception:
                pass
            unplaced_infos.append(info)
    except Exception as e:
        logger.debug("APAPI fill analyzer item scan failed: %s", e)

    # --- item_rule inspection for fully rule-blocked items ---
    try:
        if bool(cfg.get("inspect_rules", True)):
            max_rules: int = int(cfg.get("max_rule_details", 6))
            seen_rules: set = set()
            try:
                # seed with keys already used above
                for r in rule_details:
                    seen_rules.add((r.player, r.location, r.kind))
            except Exception:
                pass
            for info in unplaced_infos:
                if len(rule_details) >= max_rules:
                    break
                if not (info.advancement and info.acceptable_count == 0 and info.example_rule_blocked):
                    continue
                # inspect the item_rule of the first example location
                try:
                    ex = info.example_rule_blocked[0]
                    # format is "P{player} {name}"
                    parts = ex.split(" ", 1)
                    ex_pid = int(parts[0][1:])
                    ex_name = parts[1] if len(parts) > 1 else ""
                    key = (ex_pid, ex_name, "item_rule")
                    if key in seen_rules:
                        continue
                    seen_rules.add(key)
                    loc = mw.get_location(ex_name, ex_pid)
                    req = _inspect_rule(loc, "item_rule", cur_state, max_state)
                    if req is not None:
                        rule_details.append(req)
                except Exception:
                    continue
    except Exception as e:
        logger.debug("APAPI fill analyzer item-rule inspection failed: %s", e)

    # --- likely causes / suggestions ---
    causes: list[str] = []
    suggestions: list[str] = []
    try:
        total_locs = len(list(mw.get_locations()))
        prog_left = sum(1 for i in remaining_pool if getattr(i, "advancement", False))
        # raw capacity: literally too many items for the remaining slots?
        try:
            if capacity.overflow_progression:
                causes.append(
                    f"OVERSUBSCRIBED: {capacity.unplaced_progression} unplaced progression item(s) "
                    f"but only {capacity.unfilled_total} unfilled location(s) total — there are "
                    f"literally more progression items than slots. No placement exists.")
                suggestions.append("Remove progression items (or add locations): check create_items counts, "
                                   "duplicate item creation, and plando/excluded pools.")
            elif capacity.overflow_total:
                causes.append(
                    f"OVERSUBSCRIBED: {capacity.unplaced_total} unplaced item(s) total but only "
                    f"{capacity.unfilled_total} unfilled location(s) — more items than slots.")
                suggestions.append("Compare itempool size vs location count per player; look for "
                                   "double-created items or locations removed after items were made.")
        except Exception:
            pass
        if prog_left and unfilled:
            # per-player balance
            from collections import Counter
            need = Counter(getattr(i, "player", 0) for i in remaining_pool if getattr(i, "advancement", False))
            have = Counter(getattr(l, "player", 0) for l in unfilled)
            for pid, n in need.items():
                if have.get(pid, 0) < n:
                    causes.append(
                        f"P{pid} has {n} unplaced progression item(s) but only {have.get(pid, 0)} "
                        f"unfilled location(s) of their own — progression likely forced onto other "
                        f"players' locations and none accept it (check plando/item rules).")
        if unreachable_count:
            causes.append(
                f"{unreachable_count} sampled unfilled location(s) are unreachable EVEN with all "
                f"remaining items collected — logic dead-end (disconnected region/entrance, "
                f"over-strict access rule, or missing dungeon/entrance connection).")
            suggestions.append("Check the world(s) owning those regions: recent set_rules/connect_entrances "
                               "changes, and whether entrance randomization left an exit disconnected.")
        # item-rule wall
        for info in unplaced_infos:
            if info.advancement and info.acceptable_count == 0 and (info.rule_rejects + info.access_rejects) > 0:
                if info.rule_rejects >= info.access_rejects and info.rule_rejects > 0:
                    causes.append(
                        f"Progression item '{info.name}' (P{info.player}) is rejected by item_rule at "
                        f"{info.rule_rejects} sampled location(s) (e.g. {', '.join(info.example_rule_blocked[:3]) or 'n/a'}).")
                    suggestions.append(f"Inspect item rules/excluded/priority types blocking '{info.name}'; "
                                       f"check fill_hook / add_item_rule / plando_blocks for P{info.player}.")
                elif info.access_rejects > 0:
                    causes.append(
                        f"Progression item '{info.name}' (P{info.player}) passes item rules but no sampled "
                        f"location is reachable for it — all {info.access_rejects} candidate(s) fail the "
                        f"access check (progression bottleneck, nothing reachable to put it in).")
                    suggestions.append("Look at the 'needs to unlock' hints per blocked location above — "
                                       "those items must be reachable FIRST; the fill order may be impossible.")
        if not causes:
            if prog_left == 0:
                causes.append("No unplaced progression items remain — failure is in filler/useful placement "
                              "(likely excluded-location overflow or item_rule conflicts on filler).")
                suggestions.append("Compare excluded-location count vs filler pool size; check location "
                                   "progress types (EXCLUDED with no matching filler).")
            else:
                causes.append("No single dominant cause isolated — likely a swap-exhausted restrictive fill "
                              "(items placed early block later ones and no valid swap chain exists).")
                suggestions.append("Try a different seed; if it reproduces, bisect recent rule/pool changes. "
                                   "The full location/item lists are in the exception message and report file.")
        # completion hint
        try:
            unbeatable = [pid for pid, s in completion.items() if s == "not-beaten"]
            if unbeatable:
                suggestions.append(f"can_beat_game=False for P{unbeatable} even with all items — "
                                   f"completion condition itself may be unreachable (not just fill order).")
        except Exception:
            pass
    except Exception as e:
        logger.debug("APAPI fill analyzer cause synthesis failed: %s", e)

    return FillDiagnosis(
        seed=seed, players=players, games=games,
        exception_summary=exc_summary,
        unplaced_count=len(remaining_pool), unfilled_count=len(unfilled),
        completion=completion, blocked=blocked, unplaced=unplaced_infos,
        likely_causes=causes, suggestions=suggestions,
        unreachable_even_with_all=unreachable_count,
        rules=rule_details, capacity=capacity,
    )


def format_fill_diagnosis(diag: FillDiagnosis, *, include_header: bool = True) -> str:
    """Format a FillDiagnosis as human-readable text for APAPI error output."""
    lines: list[str] = []
    if include_header:
        lines.append(f"Seed: {diag.seed}  Players: {diag.players}")
        if diag.games:
            lines.append("Games: " + ", ".join(f"P{pid}:{g}" for pid, g in sorted(diag.games.items())))
        lines.append(f"FillError: {diag.exception_summary}")
        lines.append(f"Remaining: {diag.unplaced_count} unplaced item(s), "
                     f"{diag.unfilled_count} unfilled location(s)")
        try:
            cap = diag.capacity
            if cap.unplaced_total or cap.unfilled_total:
                lines.append(
                    f"Capacity: {cap.unplaced_progression} progression / {cap.unplaced_total} total "
                    f"unplaced vs {cap.unfilled_total} unfilled slots"
                    + ("  <-- OVERSUBSCRIBED" if (cap.overflow_progression or cap.overflow_total) else ""))
                if cap.unfilled_by_player:
                    per_p = ", ".join(
                        f"P{pid}: {cap.prog_unplaced_by_player.get(pid, 0)} prog unplaced / "
                        f"{n} slots"
                        for pid, n in sorted(cap.unfilled_by_player.items()))
                    lines.append(f"  per-player: {per_p}")
        except Exception:
            pass
    if diag.completion:
        lines.append("")
        lines.append("Completion (max-exploration state):")
        for pid in sorted(diag.completion):
            g = diag.games.get(pid, "?") if diag.games else "?"
            lines.append(f"  P{pid} [{g}]: {diag.completion[pid]}")
    if diag.unplaced:
        lines.append("")
        lines.append("Unplaced items (why nothing accepts them):")
        for info in diag.unplaced:
            adv = "progression" if info.advancement else "useful/filler"
            lines.append(f"  - '{info.name}' (P{info.player}, {adv}): "
                         f"{info.acceptable_count} accepting location(s), "
                         f"{info.rule_rejects} rule-rejected, {info.access_rejects} access-rejected")
            if info.example_ok:
                lines.append(f"      would fit: {', '.join(info.example_ok[:3])}")
            if info.example_rule_blocked:
                lines.append(f"      rule-blocked e.g.: {', '.join(info.example_rule_blocked[:3])}")
            if info.example_access_blocked and info.acceptable_count == 0:
                lines.append(f"      access-blocked e.g.: {', '.join(info.example_access_blocked[:3])}")
    if diag.blocked:
        lines.append("")
        lines.append("Blocked locations (unreachable right now):")
        for b in diag.blocked:
            if b.reachable_with_all_items:
                need = f" needs: {', '.join(b.needed_items)}" if b.needed_items else " (unlockable with remaining items)"
                lines.append(f"  - P{b.player} {b.name} [{b.region or '?'}]{need}")
            else:
                lines.append(f"  - P{b.player} {b.name} [{b.region or '?'}] UNREACHABLE even with all items"
                             f"  <-- logic dead-end")
    if diag.rules:
        lines.append("")
        lines.append("Rule inspection (what the rule code is waiting on):")
        for r in diag.rules:
            lines.append(f"  - P{r.player} {r.location} [{r.kind}]")
            if r.origin:
                lines.append(f"      defined at: {r.origin}")
            if r.source_snippet:
                lines.append(f"      rule: {r.source_snippet}")
            if r.required_items:
                for item_name, have_now, have_max in r.required_items:
                    flag = "MISSING now" if have_now == 0 else "ok"
                    extra = f", {have_max} with all items" if have_max != have_now else ""
                    lines.append(f"      needs '{item_name}': have {have_now} now{extra} ({flag})")
            elif r.missing_now:
                lines.append(f"      missing now: {', '.join(r.missing_now)}")
    if diag.likely_causes:
        lines.append("")
        lines.append("Likely cause(s):")
        for i, c in enumerate(diag.likely_causes, 1):
            lines.append(f"  {i}. {c}")
    if diag.suggestions:
        lines.append("")
        lines.append("What to check:")
        for i, s in enumerate(diag.suggestions, 1):
            lines.append(f"  {i}. {s}")
    return "\n".join(lines)


def diagnose_and_format(multiworld: Any = None, exception: BaseException | None = None) -> str:
    """Convenience: analyze + format. Never raises (returns error string on failure)."""
    try:
        return format_fill_diagnosis(analyze_fill_error(multiworld, exception))
    except Exception as e:
        return f"(APAPI fill analyzer failed: {e})"


def attach_diagnosis_to_exception(exc: BaseException, text: str, report_path: Any = None) -> BaseException:
    """Attach diagnosis text to the exception for APAPI error-output handlers. Returns exc."""
    try:
        setattr(exc, "apapi_fill_diagnosis", text)
    except Exception:
        pass
    if report_path is not None:
        try:
            setattr(exc, "apapi_fill_report_path", str(report_path))
        except Exception:
            pass
    return exc


_hooks_installed = False


def _install_hooks() -> None:
    """Hook FillError sites so the diagnosis shows in APAPI's own error output.

    Wraps ``Fill.distribute_items_restrictive`` and ``Main.main``: on FillError,
    resolves the live MultiWorld and delegates to
    ``assertions.report_fill_error`` (same banner style as the assertion
    aggregate error). No report files, no sphere dumps — console output only.
    Idempotent. Never raises.
    """
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True

    def _resolve_mw(exc: BaseException | None, args: tuple) -> Any:
        mw = getattr(exc, "multiworld", None) if exc is not None else None
        if mw is not None and hasattr(mw, "player_ids"):
            return mw
        if args and hasattr(args[0], "player_ids"):
            return args[0]
        try:
            from .multiworld_api import get_current_multiworld
            cand = get_current_multiworld()
            if cand is not None and hasattr(cand, "player_ids"):
                return cand
        except Exception:
            pass
        return None

    def _maybe_report(exc: BaseException, args: tuple) -> None:
        try:
            from Fill import FillError as _FE
        except Exception:
            return
        if not isinstance(exc, _FE):
            return
        # Skip if something already reported this exact exception (e.g. both
        # Fill and Main wrappers firing for the same failure).
        try:
            if getattr(exc, "apapi_fill_diagnosis", None):
                return
        except Exception:
            pass
        try:
            from .assertions import report_fill_error
            report_fill_error(exc, _resolve_mw(exc, args))
        except Exception:
            pass

    def _fill_wrapper(next_callable: Any, *a: Any, **kw: Any) -> Any:
        try:
            return next_callable(*a, **kw)
        except Exception as e:
            _maybe_report(e, a)
            raise

    def _main_wrapper(next_callable: Any, *a: Any, **kw: Any) -> Any:
        try:
            return next_callable(*a, **kw)
        except Exception as e:
            _maybe_report(e, a)
            raise

    # Use APAPI's hard-patch registry so wrappers chain with other APAPI
    # hooks instead of being clobbered by import order. load_missing=True
    # defers until Fill/Main are importable.
    _fill_wrapper._apapi_fill_analyzer = True  # type: ignore[attr-defined]
    _main_wrapper._apapi_fill_analyzer = True  # type: ignore[attr-defined]
    try:
        from .hard_patch import hard_patches
        existing = hard_patches._wrappers.get("Fill.distribute_items_restrictive", [])
        if not any(getattr(w, "_apapi_fill_analyzer", False) for w in existing):
            hard_patches.add_wrapper("Fill.distribute_items_restrictive", _fill_wrapper, load_missing=True)
    except Exception as e:
        logger.debug("APAPI fill analyzer could not hook Fill: %s", e)
    try:
        from .hard_patch import hard_patches as _hp_main
        existing_main = _hp_main._wrappers.get("Main.main", [])
        if not any(getattr(w, "_apapi_fill_analyzer", False) for w in existing_main):
            _hp_main.add_wrapper("Main.main", _main_wrapper, load_missing=True)
    except Exception as e:
        logger.debug("APAPI fill analyzer could not hook Main: %s", e)


try:
    _install_hooks()
except Exception:
    pass


__all__ = [
    "FILL_ANALYZER_DEFAULTS",
    "FillDiagnosis",
    "BlockedLocationInfo",
    "UnplacedItemInfo",
    "RuleRequirement",
    "CapacityInfo",
    "analyze_fill_error",
    "format_fill_diagnosis",
    "diagnose_and_format",
    "attach_diagnosis_to_exception",
    "is_enabled",
]
