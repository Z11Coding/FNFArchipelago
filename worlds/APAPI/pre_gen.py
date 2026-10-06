from __future__ import annotations

import argparse
import inspect
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from worlds.AutoWorld import World

from .debug import dprint
from .hard_patch import hard_patches

logger = logging.getLogger("APAPI.PreGen")

_yaml_by_player: dict[int, Any] = {}
_raw_yaml_cache: dict[str, Any] = {}
_instance_queue: list[Any] = []
_pre_gen_pre_hooks: list[Callable] = []

import enum

def register_pre_gen_pre_hook(func: Callable) -> None:
    _pre_gen_pre_hooks.append(func)


_ALWAYS_ATTR = "_apapi_pre_gen_always"


def _mark_always(obj: Any) -> Any:
    try:
        setattr(obj, _ALWAYS_ATTR, True)
    except Exception:
        pass
    try:
        inner = getattr(obj, "__func__", None)
        if inner is not None:
            setattr(inner, _ALWAYS_ATTR, True)
    except Exception:
        pass
    return obj


def run_always(_func: Any | None = None) -> Any:
    if _func is not None and isinstance(_func, (classmethod, staticmethod)):
        return _mark_always(_func)
    if _func is not None and callable(_func):
        return _mark_always(_func)
    def _wrap(func: Any) -> Any:
        return _mark_always(func)
    return _wrap


always_run = run_always
pre_gen_always = run_always
tool_pre_gen = run_always


def _is_always(pre: Any, world_type: Any) -> bool:
    try:
        if getattr(pre, _ALWAYS_ATTR, False):
            return True
    except Exception:
        pass
    try:
        inner_pre = getattr(pre, "__func__", None)
        if inner_pre is not None and getattr(inner_pre, _ALWAYS_ATTR, False):
            return True
    except Exception:
        pass
    try:
        desc = inspect.getattr_static(world_type, "pre_gen")
        if getattr(desc, _ALWAYS_ATTR, False):
            return True
        inner = getattr(desc, "__func__", None)
        if inner is not None and getattr(inner, _ALWAYS_ATTR, False):
            return True
        if getattr(pre, "__wrapped__", None) is not None and getattr(getattr(pre, "__wrapped__", None), _ALWAYS_ATTR, False):
            return True
        wrapped = getattr(pre, "__wrapped__", None)
        if wrapped is not None:
            inner2 = getattr(wrapped, "__func__", None)
            if inner2 is not None and getattr(inner2, _ALWAYS_ATTR, False):
                return True
    except Exception:
        pass
    return False

class RandomKind(str, enum.Enum):
    WEIGHTED = "weighted"
    RANDOM = "random"
    RANDOM_LOW = "random-low"
    RANDOM_MIDDLE = "random-middle"
    RANDOM_HIGH = "random-high"
    RANDOM_RANGE = "random-range"
    RANDOM_RANGE_LOW = "random-range-low"
    RANDOM_RANGE_MIDDLE = "random-range-middle"
    RANDOM_RANGE_HIGH = "random-range-high"


class PendingRandom:
    def __init__(self, raw: Any, option: str | None = None, option_class: Any | None = None):
        self.raw = raw
        self.option = option
        self.option_class = option_class

    @property
    def kind(self) -> RandomKind | None:
        if isinstance(self.raw, dict):
            return RandomKind.WEIGHTED
        if isinstance(self.raw, list):
            return RandomKind.WEIGHTED
        if isinstance(self.raw, str):
            s = self.raw.lower()
            if s.startswith("random-range-low-"):
                return RandomKind.RANDOM_RANGE_LOW
            if s.startswith("random-range-middle-"):
                return RandomKind.RANDOM_RANGE_MIDDLE
            if s.startswith("random-range-high-"):
                return RandomKind.RANDOM_RANGE_HIGH
            if s.startswith("random-range-"):
                return RandomKind.RANDOM_RANGE
            if s == "random-low":
                return RandomKind.RANDOM_LOW
            if s == "random-middle":
                return RandomKind.RANDOM_MIDDLE
            if s == "random-high":
                return RandomKind.RANDOM_HIGH
            if s == "random":
                return RandomKind.RANDOM
        return None

    @property
    def supported_values(self) -> list[Any]:
        if self.option_class is None:
            return []
        if hasattr(self.option_class, "options") and isinstance(self.option_class.options, dict):
            return list(self.option_class.options.keys())
        if hasattr(self.option_class, "range_start") and hasattr(self.option_class, "range_end"):
            try:
                return list(range(int(self.option_class.range_start), int(self.option_class.range_end) + 1))
            except Exception:
                return []
        if hasattr(self.option_class, "valid_keys"):
            try:
                return sorted(self.option_class.valid_keys)  # type: ignore
            except Exception:
                return []
        return []

    def __iter__(self):
        return iter(self.supported_values)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.raw!r})"

    def __bool__(self) -> bool:
        return True


class PendingChoiceRandom(PendingRandom):
    @property
    def supported_values(self) -> list[Any]:
        if self.option_class is not None and hasattr(self.option_class, "options"):
            return list(self.option_class.options.keys())
        if self.option_class is not None and hasattr(self.option_class, "name_lookup"):
            try:
                return list(self.option_class.name_lookup.values())
            except Exception:
                pass
        return super().supported_values

    @property
    def supported_ids(self) -> list[int]:
        if self.option_class is not None and hasattr(self.option_class, "options"):
            return list(self.option_class.options.values())
        return []


class PendingRangeRandom(PendingRandom):
    @property
    def range_start(self) -> int | None:
        try:
            return int(getattr(self.option_class, "range_start", None))  # type: ignore
        except Exception:
            return None

    @property
    def range_end(self) -> int | None:
        try:
            return int(getattr(self.option_class, "range_end", None))  # type: ignore
        except Exception:
            return None

    @property
    def random_kind(self) -> str | None:
        if isinstance(self.raw, str):
            return self.raw
        if isinstance(self.raw, dict):
            return "weighted"
        return None

    @property
    def allowed_range(self) -> tuple[int | None, int | None]:
        if isinstance(self.raw, str) and self.raw.startswith("random-range"):
            try:
                parts = self.raw.split("-")
                min_v = int(parts[-2])
                max_v = int(parts[-1])
                min_v, max_v = (min_v, max_v) if min_v <= max_v else (max_v, min_v)
                rs = self.range_start
                re = self.range_end
                if rs is not None:
                    min_v = max(min_v, rs)
                if re is not None:
                    max_v = min(max_v, re)
                return (min_v, max_v)
            except Exception:
                pass
        return (self.range_start, self.range_end)

    @property
    def supported_values(self) -> list[Any]:
        rs, re = self.allowed_range
        if rs is not None and re is not None:
            try:
                if re - rs > 1000:
                    return list(range(rs, re + 1))[:1000]
                return list(range(rs, re + 1))
            except Exception:
                pass
        return super().supported_values

    def iter_range(self):
        rs, re = self.allowed_range
        if rs is not None and re is not None:
            return iter(range(rs, re + 1))
        return iter([])


class PendingSetRandom(PendingRandom):
    @property
    def supported_values(self) -> list[Any]:
        if self.option_class is not None:
            for attr in ("valid_keys", "_valid_keys"):
                if hasattr(self.option_class, attr):
                    try:
                        v = getattr(self.option_class, attr)
                        if v:
                            return sorted(v)  # type: ignore
                    except Exception:
                        pass
            if hasattr(self.option_class, "options"):
                return list(self.option_class.options.keys())
        return super().supported_values

    @property
    def allowed_count_range(self) -> tuple[int, int] | None:
        try:
            n = len(self.supported_values)
            if isinstance(self.raw, str):
                s = self.raw.lower()
                if s == "random":
                    return (0, n)
                if s.startswith("random-range"):
                    parts = s.split("-")
                    lo = int(parts[-2]); hi = int(parts[-1])
                    lo, hi = (lo, hi) if lo <= hi else (hi, lo)
                    lo = max(0, lo); hi = min(n, hi)
                    return (lo, hi)
                if s in ("random-low", "random-high", "random-middle"):
                    return (0, n)
            if isinstance(self.raw, dict):
                return (0, n)
        except Exception:
            pass
        return None

    @property
    def random_kind(self) -> str | None:
        if isinstance(self.raw, str):
            return self.raw
        return None


@dataclass
class _Queued:
    kind: str
    target: Any
    action: Callable
    condition: Callable | None


class PreGenContext:
    def __init__(self, args: argparse.Namespace, seed: Any, yamls_by_player: dict[int, Any], raw_by_player: dict[int, Any] | None = None):
        self.args = args
        self.seed = seed
        self.yamls_by_player = dict(yamls_by_player)
        self.raw_yamls_by_player = dict(raw_by_player) if raw_by_player else dict(yamls_by_player)

    def get_yamls(self, player: int) -> Any:
        return self.yamls_by_player.get(player)

    def get_raw_yamls(self, player: int) -> Any:
        return self.raw_yamls_by_player.get(player)

    def get_all_yamls(self) -> dict[int, Any]:
        return dict(self.yamls_by_player)

    def get_all_raw_yamls(self) -> dict[int, Any]:
        return dict(self.raw_yamls_by_player)

    def get_yamls_for_game(self, game: str) -> dict[int, Any]:
        out: dict[int, Any] = {}
        game_map: Any = getattr(self.args, "game", {})
        if isinstance(game_map, dict):
            for p, g in game_map.items():
                if g == game:
                    out[p] = self.yamls_by_player.get(p)
        return out

    def get_players_for_game(self, game: str) -> list[int]:
        game_map: Any = getattr(self.args, "game", {})
        if isinstance(game_map, dict):
            return [p for p, g in game_map.items() if g == game]
        return []

    def get_game(self, player: int) -> str | None:
        game_map: Any = getattr(self.args, "game", {})
        if isinstance(game_map, dict):
            return game_map.get(player)
        return None

    def get_name(self, player: int) -> str | None:
        name_map: Any = getattr(self.args, "name", {})
        if isinstance(name_map, dict):
            return name_map.get(player)
        return None

    def queue_for_player(self, player: int, action: Callable, condition: Callable | None = None) -> None:
        _instance_queue.append(_Queued("player", player, action, condition))

    def queue_for_name(self, name: str, action: Callable, condition: Callable | None = None) -> None:
        _instance_queue.append(_Queued("name", name, action, condition))

    def queue_for_game(self, game: str, action: Callable, condition: Callable | None = None) -> None:
        _instance_queue.append(_Queued("game", game, action, condition))

    def queue(self, target: int | str, action: Callable, condition: Callable | None = None) -> None:
        if isinstance(target, int):
            self.queue_for_player(target, action, condition)
        else:
            self.queue_for_name(str(target), action, condition)


def _is_random_string(s: Any) -> bool:
    return isinstance(s, str) and s.lower().startswith("random")


def _make_pending(raw: Any, option: str | None, hint: Any) -> PendingRandom:
    try:
        if hint is not None:
            if hasattr(hint, "range_start") and hasattr(hint, "range_end"):
                return PendingRangeRandom(raw, option, hint)
            # OptionSet has valid_keys / _valid_keys or is OptionSet subclass
            try:
                import Options as _Opts
                if isinstance(hint, type) and issubclass(hint, _Opts.OptionSet):
                    return PendingSetRandom(raw, option, hint)
            except Exception:
                pass
            if hasattr(hint, "valid_keys") or hasattr(hint, "_valid_keys"):
                return PendingSetRandom(raw, option, hint)
            if hasattr(hint, "options"):
                return PendingChoiceRandom(raw, option, hint)
    except Exception:
        pass
    return PendingRandom(raw, option, hint)


def _wrap_random_in_doc(doc: Any) -> Any:
    if not isinstance(doc, dict):
        return doc
    try:
        import Options
        from worlds.AutoWorld import AutoWorldRegister
    except Exception:
        return doc
    out: dict[str, Any] = {}
    for k, v in doc.items():
        if k in AutoWorldRegister.world_types and isinstance(v, dict):
            wt = AutoWorldRegister.world_types[k]
            hints = getattr(wt.options_dataclass, "type_hints", {})
            inner: dict[str, Any] = {}
            for ok, ov in v.items():
                hint = hints.get(ok)
                is_weighted = bool(hint and getattr(hint, "supports_weighting", False))
                if _is_random_string(ov):
                    inner[ok] = _make_pending(ov, ok, hint)
                elif is_weighted and isinstance(ov, (dict, list)):
                    inner[ok] = _make_pending(ov, ok, hint)
                else:
                    inner[ok] = ov
            out[k] = inner
        elif k in getattr(Options.CommonOptions, "type_hints", {}):
            hint = Options.CommonOptions.type_hints.get(k)
            is_weighted = bool(hint and getattr(hint, "supports_weighting", False))
            if _is_random_string(v):
                out[k] = _make_pending(v, k, hint)
            elif is_weighted and isinstance(v, (dict, list)):
                out[k] = _make_pending(v, k, hint)
            else:
                out[k] = v
        else:
            out[k] = v
    return out


def _apply_rolled_identity(doc: Any, pid: int, args: argparse.Namespace) -> Any:
    try:
        if not isinstance(doc, dict):
            return doc
        out = dict(doc)
        game_map = getattr(args, "game", None)
        if isinstance(game_map, dict):
            g = game_map.get(pid)
            if isinstance(g, str) and g:
                out["game"] = g
        name_map = getattr(args, "name", None)
        if isinstance(name_map, dict):
            n = name_map.get(pid)
            if isinstance(n, str) and n:
                out["name"] = n
        return out
    except Exception:
        return doc


def _build_yamls_by_player(args: argparse.Namespace) -> dict[int, Any]:
    yamls: dict[int, Any] = {}
    multi = getattr(args, "multi", 0)
    if not isinstance(multi, int) or multi <= 0:
        game_map = getattr(args, "game", {})
        if isinstance(game_map, dict) and game_map:
            multi = max(game_map.keys())
        else:
            return yamls
    for player in range(1, multi + 1):
        data: dict[str, Any] = {}
        for key, val in vars(args).items():
            if isinstance(val, dict) and player in val:
                data[key] = val[player]
        if data:
            yamls[player] = data
        elif hasattr(args, "_apapi_raw_yamls") and isinstance(getattr(args, "_apapi_raw_yamls"), dict):
            raw = getattr(args, "_apapi_raw_yamls").get(player)
            if raw is not None:
                yamls[player] = raw
    if not yamls and hasattr(args, "_apapi_raw_yamls"):
        raw_map = getattr(args, "_apapi_raw_yamls")
        if isinstance(raw_map, dict):
            for p, v in raw_map.items():
                yamls[p] = v
    return yamls


def _try_build_raw_from_files(args: argparse.Namespace) -> dict[int, Any] | None:
    try:
        ppath = getattr(args, "player_files_path", None)
        if not ppath or not os.path.isdir(str(ppath)):
            return None
        weights_path = getattr(args, "weights_file_path", None)
        meta_path = getattr(args, "meta_file_path", None)
        if weights_path and not os.path.isabs(str(weights_path)):
            weights_path = os.path.join(str(ppath), str(weights_path))
        if meta_path and not os.path.isabs(str(meta_path)):
            meta_path = os.path.join(str(ppath), str(meta_path))
        weights_cache: dict[str, tuple] = {}
        for entry in os.scandir(str(ppath)):
            fname = entry.name
            if entry.is_file() and not fname.startswith(".") and not fname.lower().endswith(".ini") and os.path.join(str(ppath), fname) not in {str(weights_path), str(meta_path)}:
                fpath = os.path.join(str(ppath), fname)
                try:
                    import Utils
                    with open(fpath, "rb") as f:
                        text = str(f.read(), "utf-8-sig")
                    docs = tuple(Utils.parse_yamls(text))
                    docs = tuple(d for d in docs if d is not None)
                    if docs:
                        weights_cache[fname] = docs
                except Exception:
                    continue
        if not weights_cache:
            return None
        weights_cache = {k: v for k, v in sorted(weights_cache.items(), key=lambda kv: kv[0].casefold())}
        raw_by_player: dict[int, Any] = {}
        pid = 1
        for fname, docs in weights_cache.items():
            for doc in docs:
                wrapped = _wrap_random_in_doc(doc)
                raw_by_player[pid] = wrapped
                pid += 1
        return raw_by_player if raw_by_player else None
    except Exception:
        return None


def _rebuild_world_derived(world_type: Any) -> None:
    try:
        world_type.item_name_to_id = {k: v for k, v in world_type.item_name_to_id.items() if v}
        world_type.location_name_to_id = {k: v for k, v in world_type.location_name_to_id.items() if v}
        world_type.item_id_to_name = {v: k for k, v in world_type.item_name_to_id.items()}
        world_type.location_id_to_name = {v: k for k, v in world_type.location_name_to_id.items()}
        world_type.item_names = frozenset(world_type.item_name_to_id)
        world_type.location_names = frozenset(world_type.location_name_to_id)
        try:
            if hasattr(world_type, "item_name_groups") and isinstance(world_type.item_name_groups, dict):
                for g, s in list(world_type.item_name_groups.items()):
                    try:
                        world_type.item_name_groups[g] = frozenset(s)
                    except Exception:
                        pass
                if "Everything" in world_type.item_name_groups:
                    world_type.item_name_groups["Everything"] = world_type.item_names
        except Exception:
            pass
        try:
            if hasattr(world_type, "location_name_groups") and isinstance(world_type.location_name_groups, dict):
                for g, s in list(world_type.location_name_groups.items()):
                    try:
                        world_type.location_name_groups[g] = frozenset(s)
                    except Exception:
                        pass
                if "Everywhere" in world_type.location_name_groups:
                    world_type.location_name_groups["Everywhere"] = world_type.location_names
        except Exception:
            pass
        try:
            if hasattr(world_type, "all_item_and_group_names"):
                world_type.all_item_and_group_names = frozenset(world_type.item_names | set(getattr(world_type, "item_name_groups", {})))
        except Exception:
            pass
    except Exception:
        pass


def _refresh_data_package(games: set[str]) -> None:
    try:
        import worlds
        from worlds.AutoWorld import AutoWorldRegister
        for game in games:
            wt = AutoWorldRegister.world_types.get(game)
            if wt is None:
                continue
            try:
                _rebuild_world_derived(wt)
                data = wt.get_data_package_data()
                worlds.network_data_package["games"][game] = data
                dprint("pre_gen", f"refreshed datapackage for {game}")
            except Exception as exc:
                logger.warning("APAPI pre_gen datapackage refresh failed for %s: %s", game, exc)
    except Exception:
        pass


def _find_multiworld_via_stack() -> Any | None:
    try:
        import inspect as _insp
        frame = _insp.currentframe()
        for _ in range(12):
            if frame is None:
                break
            frame = frame.f_back
            if frame is None:
                break
            for v in frame.f_locals.values():
                try:
                    import BaseClasses
                    if isinstance(v, BaseClasses.MultiWorld):
                        return v
                except Exception:
                    continue
                try:
                    if hasattr(v, "worlds") and hasattr(v, "player_ids") and hasattr(v, "game"):
                        return v
                except Exception:
                    continue
            for v in frame.f_globals.values():
                try:
                    if hasattr(v, "worlds") and hasattr(v, "player_ids"):
                        return v
                except Exception:
                    continue
    except Exception:
        pass
    finally:
        try:
            del frame  # type: ignore
        except Exception:
            pass
    return None


def _run_pre_gen(args: argparse.Namespace, seed: Any, multiworld: Any | None = None) -> None:
    global _yaml_by_player, _instance_queue
    _instance_queue.clear()
    if multiworld is None:
        multiworld = _find_multiworld_via_stack()
    yamls_by_player = _build_yamls_by_player(args)
    raw_try = _try_build_raw_from_files(args)
    if raw_try:
        for pid, raw_doc in raw_try.items():
            yamls_by_player[pid] = _apply_rolled_identity(raw_doc, pid, args)
        raw_by_player = {pid: _apply_rolled_identity(doc, pid, args) for pid, doc in raw_try.items()}
        # ensure players from args that have no raw file still present in raw_by_player as rolled
        for pid, doc in list(yamls_by_player.items()):
            if pid not in raw_by_player:
                raw_by_player[pid] = doc
            # also ensure raw_try players not in base are added
        for pid, doc in raw_try.items():
            if pid not in yamls_by_player:
                yamls_by_player[pid] = doc
    else:
        raw_by_player = dict(yamls_by_player)
    if not yamls_by_player:
        dprint("pre_gen", "no per-player yamls found, skipping")
        return
    _yaml_by_player = dict(yamls_by_player)
    ctx = PreGenContext(args, seed, yamls_by_player, raw_by_player)
    try:
        ctx.multiworld = multiworld  # type: ignore
    except Exception:
        pass
    for _hook in list(_pre_gen_pre_hooks):
        try:
            _hook(ctx, multiworld)
        except Exception as _he:
            logger.warning("APAPI pre_gen pre-hook %s failed: %s", getattr(_hook, "__name__", str(_hook)), _he, exc_info=True)
    try:
        for _pid, _ydoc in list(ctx.yamls_by_player.items()):
            if _pid not in yamls_by_player:
                yamls_by_player[_pid] = _ydoc
                _yaml_by_player[_pid] = _ydoc
                if hasattr(ctx.args, "game") and isinstance(ctx.args.game, dict) and _pid not in ctx.args.game:
                    # try to infer game from yaml
                    try:
                        _g = _ydoc.get("game") if isinstance(_ydoc, dict) else None
                        if isinstance(_g, str):
                            ctx.args.game[_pid] = _g
                    except Exception:
                        pass
                if hasattr(ctx.args, "name") and isinstance(ctx.args.name, dict) and _pid not in ctx.args.name:
                    try:
                        _n = _ydoc.get("name") if isinstance(_ydoc, dict) else None
                        if isinstance(_n, str):
                            ctx.args.name[_pid] = _n
                    except Exception:
                        pass
        for _pid, _ydoc in list(ctx.raw_yamls_by_player.items()):
            if _pid not in raw_by_player:
                raw_by_player[_pid] = _ydoc
    except Exception:
        pass
    try:
        from worlds.AutoWorld import AutoWorldRegister, World
    except Exception:
        return
    touched: set[str] = set()
    world_items = list(AutoWorldRegister.world_types.items())
    world_items.sort(key=lambda x: getattr(x[1], "pre_gen_priority", 0))
    for game, world_type in world_items:
        if getattr(world_type, "game", game) != game:
            continue
        pre = getattr(world_type, "pre_gen", None)
        if pre is None:
            continue
        base_pre = getattr(World, "pre_gen", None)
        if base_pre is not None and pre is base_pre:
            continue
        always = _is_always(pre, world_type)
        players = ctx.get_players_for_game(game)
        if not players and not always:
            continue
        yamls = [ctx.yamls_by_player[p] for p in players if p in ctx.yamls_by_player] if players else []
        touched.add(game)
        try:
            sig = inspect.signature(pre)
            params = list(sig.parameters.values())
            try:
                desc = inspect.getattr_static(world_type, "pre_gen")
                is_static = isinstance(desc, staticmethod)
                is_class = isinstance(desc, classmethod)
            except Exception:
                is_static = False
                is_class = False
            # try to include multiworld if available
            cand_sets: list[tuple] = []
            if is_static or is_class:
                if multiworld is not None:
                    cand_sets.append((yamls, ctx, multiworld))
                cand_sets.append((yamls, ctx))
                cand_sets.append((yamls,))
                cand_sets.append(())
            else:
                if multiworld is not None:
                    cand_sets.append((world_type, yamls, ctx, multiworld))
                cand_sets.append((world_type, yamls, ctx))
                if multiworld is not None:
                    cand_sets.append((world_type, yamls, multiworld))
                cand_sets.append((world_type, yamls))
                if multiworld is not None:
                    cand_sets.append((yamls, ctx, multiworld))
                cand_sets.append((yamls, ctx))
                cand_sets.append((yamls,))
                cand_sets.append(())
            # filter by param count to try closest first
            # sort by length descending but keep original order for ties
            # try each candidate, fallback to next on TypeError
            success = False
            last_exc: Exception | None = None
            for cand in cand_sets:
                try:
                    sig.bind(*cand)
                except TypeError:
                    try:
                        sig.bind_partial(*cand)
                    except TypeError:
                        continue
                try:
                    pre(*cand)
                    success = True
                    break
                except TypeError as te:
                    last_exc = te
                    continue
                except Exception:
                    # non-TypeError means call succeeded in binding but failed inside, re-raise
                    raise
            if not success and last_exc is not None:
                raise last_exc
            elif not success:
                # fallback try simplest
                pre(yamls)
            dprint("pre_gen", f"{game} pre_gen succeeded for players {players}")
        except Exception as exc:
            logger.warning("APAPI pre_gen for %s failed: %s", game, exc, exc_info=True)
    if touched:
        _refresh_data_package(touched)
    try:
        args._apapi_yamls_by_player = dict(yamls_by_player)  # type: ignore
        args._apapi_raw_yamls_by_player = dict(raw_by_player)  # type: ignore
        args._apapi_pre_gen_ctx = ctx  # type: ignore
    except Exception:
        pass


def _install_world_new_hook() -> None:
    try:
        from worlds.AutoWorld import World
    except Exception:
        return
    if getattr(World, "_apapi_new_patched", False):
        return
    orig_new = World.__new__
    def _patched_new(cls, *args, **kwargs):  # type: ignore
        try:
            inst = orig_new(cls)  # type: ignore
        except TypeError:
            try:
                inst = orig_new(cls, *args, **kwargs)  # type: ignore
            except Exception:
                inst = object.__new__(cls)
        try:
            multiworld = None
            player = None
            if len(args) >= 1:
                multiworld = args[0]
            if len(args) >= 2:
                player = args[1]
            if multiworld is None:
                multiworld = kwargs.get("multiworld")
            if player is None:
                player = kwargs.get("player")
            if isinstance(player, int) and multiworld is not None:
                yaml_data = _yaml_by_player.get(player)
                if yaml_data is None:
                    try:
                        yaml_data = getattr(multiworld, "_apapi_yamls_by_player", {}).get(player)  # type: ignore
                    except Exception:
                        yaml_data = None
                if yaml_data is not None:
                    object.__setattr__(inst, "_apapi_yaml", yaml_data)
        except Exception:
            pass
        # print(f"Created instance of {cls} with _apapi_yaml: {getattr(inst, '_apapi_yaml', None)}")
        return inst
    try:
        World.__new__ = staticmethod(_patched_new)  # type: ignore
        setattr(World, "_apapi_new_patched", True)  # type: ignore
        dprint("pre_gen", "World.__new__ patched for yaml")
    except Exception as exc:
        logger.debug("APAPI could not patch World.__new__: %s", exc)


def _install_yaml_property() -> None:
    try:
        from worlds.AutoWorld import World
    except Exception:
        return
    if getattr(World, "_apapi_pre_gen_yaml_installed", False):
        _install_world_new_hook()
        return
    orig_init = World.__init__

    def apapi_init(self, multiworld, player, *a, **kw):  # type: ignore
        try:
            yaml_data = _yaml_by_player.get(player)
            if yaml_data is None:
                try:
                    args_yamls = getattr(multiworld, "_apapi_yamls_by_player", None)
                    if isinstance(args_yamls, dict) and player in args_yamls:
                        yaml_data = args_yamls[player]
                except Exception:
                    yaml_data = None
            if yaml_data is not None:
                object.__setattr__(self, "_apapi_yaml", yaml_data)
        except Exception:
            pass
        return orig_init(self, multiworld, player, *a, **kw)

    World.__init__ = apapi_init  # type: ignore

    def _get_yaml(self):  # type: ignore
        return getattr(self, "_apapi_yaml", {})

    def _set_yaml(self, value):  # type: ignore
        object.__setattr__(self, "_apapi_yaml", value)

    try:
        World.__yaml__ = property(_get_yaml, _set_yaml)  # type: ignore
    except Exception:
        pass
    try:
        setattr(World, "_apapi_pre_gen_yaml_installed", True)  # type: ignore
    except Exception:
        pass
    _install_world_new_hook()
    dprint("pre_gen", "World.__yaml__ property installed")


def _resolve_players_for_queued(multiworld: Any, kind: str, target: Any) -> list[int]:
    try:
        if kind == "player" and isinstance(target, int):
            return [target] if target in getattr(multiworld, "player_ids", []) else []
        if kind == "name" and isinstance(target, str):
            low = target.lower()
            return [pid for pid, name in getattr(multiworld, "player_name", {}).items() if str(name).lower() == low]
        if kind == "game" and isinstance(target, str):
            return [pid for pid, g in getattr(multiworld, "game", {}).items() if g == target]
    except Exception:
        pass
    return []


def _execute_queued_actions(multiworld: Any) -> None:
    if not _instance_queue:
        return
    pending = list(_instance_queue)
    _instance_queue.clear()
    for entry in pending:
        try:
            players = _resolve_players_for_queued(multiworld, entry.kind, entry.target)
            for pid in players:
                try:
                    world = multiworld.worlds.get(pid)
                    if world is None:
                        continue
                    cond = entry.condition
                    if cond is not None:
                        try:
                            if not cond(world):
                                continue
                        except Exception as ce:
                            logger.warning("APAPI queued condition failed for %s p%s: %s", entry.target, pid, ce)
                            continue
                    try:
                        entry.action(world)
                    except Exception as ae:
                        logger.warning("APAPI queued action failed for %s p%s: %s", entry.target, pid, ae, exc_info=True)
                except Exception:
                    continue
        except Exception:
            continue
    # if actions queued new actions recursively, keep them for next sweep
    if _instance_queue:
        # defer remainder? run again once
        extra = list(_instance_queue)
        _instance_queue.clear()
        for e in extra:
            _instance_queue.append(e)


_deferred_args: argparse.Namespace | None = None
_deferred_seed: Any | None = None
_pre_gen_done: bool = False

def _main_wrapper(next_callable, *a, **kw):  # type: ignore
    global _deferred_args, _deferred_seed, _pre_gen_done, _yaml_by_player
    args = a[0] if len(a) >= 1 else kw.get("args")
    seed = a[1] if len(a) >= 2 else kw.get("seed")
    # capture yamls early so _yaml_by_player is available for World.__new__ even before pre_gen dispatch
    try:
        if isinstance(args, argparse.Namespace) and hasattr(args, "game"):
            # build yamls now for early World.__new__ injection, but defer pre_gen dispatch until multiworld exists
            yamls = _build_yamls_by_player(args)
            raw_try = _try_build_raw_from_files(args)
            if raw_try:
                for pid, doc in raw_try.items():
                    yamls[pid] = _apply_rolled_identity(doc, pid, args)
            if yamls:
                _yaml_by_player = dict(yamls)
                try:
                    args._apapi_yamls_by_player = dict(yamls)  # type: ignore
                    # raw_by_player for later
                    raw_for_ctx = ({pid: _apply_rolled_identity(doc, pid, args) for pid, doc in raw_try.items()}
                                   if raw_try else dict(yamls))
                    # ensure raw_for_ctx also has entries for yamls not in raw_try
                    for pid in list(yamls.keys()):
                        if pid not in raw_for_ctx:
                            raw_for_ctx[pid] = yamls[pid]
                    args._apapi_raw_yamls_by_player = raw_for_ctx  # type: ignore
                except Exception:
                    pass
            _deferred_args = args
            _deferred_seed = seed
            _pre_gen_done = False
    except Exception as exc:
        logger.warning("APAPI pre_gen wrapper failed: %s", exc, exc_info=True)
    result = next_callable(*a, **kw)
    try:
        if result is not None and hasattr(result, "player_ids"):
            if hasattr(args, "_apapi_yamls_by_player"):
                try:
                    setattr(result, "_apapi_yamls_by_player", getattr(args, "_apapi_yamls_by_player"))
                except Exception:
                    pass
            for p in list(getattr(result, "player_ids", [])):
                try:
                    w = result.worlds.get(p)
                    if w is not None and not hasattr(w, "_apapi_yaml"):
                        y = _yaml_by_player.get(p)
                        if y is not None:
                            object.__setattr__(w, "_apapi_yaml", y)
                except Exception:
                    continue
    except Exception:
        pass
    return result


def _set_options_wrapper(next_callable, *a, **kw):  # type: ignore
    global _pre_gen_done
    try:
        self = a[0] if a else kw.get("self")
        args = a[1] if len(a) >= 2 else kw.get("args")
        # dispatch pre_gen with multiworld if not yet done
        if not _pre_gen_done and self is not None and hasattr(self, "worlds"):
            use_args = None
            use_seed = None
            if isinstance(args, argparse.Namespace) and hasattr(args, "game"):
                use_args = args
                try:
                    use_seed = getattr(self, "seed", None)
                    if use_seed is None:
                        use_seed = _deferred_seed
                except Exception:
                    use_seed = _deferred_seed
            elif _deferred_args is not None and hasattr(_deferred_args, "game"):
                use_args = _deferred_args
                use_seed = _deferred_seed
                try:
                    if hasattr(self, "seed") and getattr(self, "seed") is not None:
                        use_seed = getattr(self, "seed")
                except Exception:
                    pass
            else:
                # weird scope parsing fallback: try to find args in stack
                try:
                    import inspect as _insp2
                    fr = _insp2.currentframe()
                    for _ in range(8):
                        if fr is None:
                            break
                        fr = fr.f_back
                        if fr is None:
                            break
                        for v in list(fr.f_locals.values()) + list(fr.f_globals.values()):
                            if isinstance(v, argparse.Namespace) and hasattr(v, "game"):
                                use_args = v
                                break
                        if use_args is not None:
                            break
                except Exception:
                    pass
            if use_args is not None:
                try:
                    _run_pre_gen(use_args, use_seed, self)
                except Exception as e2:
                    logger.warning("APAPI pre_gen (set_options) failed: %s", e2, exc_info=True)
                _pre_gen_done = True
                # ensure multiworld has yamls for World.__new__
                try:
                    if hasattr(use_args, "_apapi_yamls_by_player"):
                        setattr(self, "_apapi_yamls_by_player", getattr(use_args, "_apapi_yamls_by_player"))
                    elif _yaml_by_player:
                        setattr(self, "_apapi_yamls_by_player", dict(_yaml_by_player))
                except Exception:
                    pass
    except Exception as exc:
        logger.debug("APAPI pre_gen dispatch (set_options) failed: %s", exc)
    result = next_callable(*a, **kw)
    try:
        self2 = a[0] if a else kw.get("self")
        if self2 is not None and hasattr(self2, "worlds"):
            _execute_queued_actions(self2)
    except Exception as exc:
        logger.warning("APAPI queued execution failed: %s", exc, exc_info=True)
    return result


def _generate_wrapper(next_callable, *a, **kw):  # type: ignore
    result = next_callable(*a, **kw)
    try:
        if isinstance(result, tuple) and len(result) == 2:
            erargs, seed = result
            if isinstance(erargs, argparse.Namespace):
                yamls = _build_yamls_by_player(erargs)
                if yamls:
                    try:
                        erargs._apapi_raw_yamls = yamls  # type: ignore
                    except Exception:
                        pass
                    global _yaml_by_player
                    _yaml_by_player = dict(yamls)
    except Exception:
        pass
    return result


def initialize_pre_gen() -> None:
    _install_yaml_property()
    try:
        hard_patches.add_wrapper("Main.main", _main_wrapper, load_missing=True)
        dprint("pre_gen", "Main.main wrapper installed")
    except Exception as exc:
        logger.warning("APAPI pre_gen could not wrap Main.main: %s", exc)
    try:
        hard_patches.add_wrapper("BaseClasses.MultiWorld.set_options", _set_options_wrapper, load_missing=True)
        dprint("pre_gen", "set_options wrapper installed")
        try:
            from worlds.APAPI.world_ready import on_worlds_loaded

            def _repatch_set_options():
                try:
                    hard_patches.add_wrapper("BaseClasses.MultiWorld.set_options", _set_options_wrapper, load_missing=False)
                    dprint("pre_gen", "set_options wrapper re-installed after worlds loaded")
                except Exception as e2:
                    logger.debug("APAPI set_options re-patch failed: %s", e2)

            on_worlds_loaded(_repatch_set_options)
        except Exception:
            pass
    except Exception as exc:
        logger.warning("APAPI pre_gen could not wrap set_options: %s", exc)
    try:
        hard_patches.add_wrapper("Generate.main", _generate_wrapper, load_missing=True)
        dprint("pre_gen", "Generate.main wrapper installed")
    except Exception as exc:
        dprint("pre_gen", f"Generate.main wrapper deferred: {exc}")
        try:
            hard_patches.add_wrapper("Generate.main", _generate_wrapper, load_missing=True)
        except Exception as exc2:
            logger.warning("APAPI pre_gen could not wrap Generate.main: %s", exc2)
    dprint("init", "pre_gen initialized")


__all__ = ["PreGenContext", "PendingRandom", "always_run", "pre_gen_always", "run_always", "tool_pre_gen", "initialize_pre_gen"]
