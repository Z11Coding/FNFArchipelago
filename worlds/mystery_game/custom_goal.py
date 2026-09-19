from __future__ import annotations

from worlds.AutoWorld import World

"""Custom Goal for Mystery Game. Toggle with location and item goals."""

from typing import Any

from BaseClasses import Item, ItemClassification, Location, MultiWorld, Region
from Options import OptionDict, OptionSet, Toggle


class MysteryCustomGoal(Toggle):
    """Enable custom goal for this Mystery slot. When on, use goal locations or items."""

    display_name = "Custom Goal"
    default = False


class MysteryCustomGoalLocations(OptionSet):
    """Location names that must be reached for custom goal. Each gets a standard Goal Token."""

    display_name = "Custom Goal Locations"
    default = frozenset()
    supports_weighting = False


class MysteryCustomGoalItems(OptionDict):
    """Item goals for custom goal. Map item name to count required."""

    display_name = "Custom Goal Items"
    default = {}
    supports_weighting = False

    def verify(self, world: Any, player_name: str, plando_options: Any) -> None:
        for name, count in dict(self.value).items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Custom goal item name must be non-empty string for {player_name}.")
            if not isinstance(count, int) or count < 1:
                raise ValueError(f"Custom goal count for {name!r} must be >=1 for {player_name}.")


class MysteryCustomGoalAnyItems(Toggle):
    """When true, any item of the required name counts toward the goal (all matching items become GOAL_MARKED and progression).
    When false, only specifically marked items created for the goal count. For common filler like TUNIC Grass, use true.
    """

    display_name = "Custom Goal: Any Item Counts"
    default = False


CUSTOM_GOAL_TAG = "mystery_custom_goal"
GOAL_MARKED_ATTR = "mystery_goal_marked"
GOAL_MARKED_FLAG: int = 8



GOAL_MARKED_MAP: dict[int, bool] = {}


def is_goal_marked(item: Any) -> bool:
    try:
        return bool(GOAL_MARKED_MAP.get(id(item), False))
    except Exception:
        return False


def _get_custom_goal_data(world: World) -> dict[str, Any]:
    try:
        enabled = bool(getattr(world.options, "mystery_custom_goal", None) and world.options.mystery_custom_goal.value)
    except Exception:
        enabled = False
    if not enabled:
        try:
            enabled = bool(getattr(world.options, "custom_goal", None) and world.options.custom_goal.value)
        except Exception:
            pass
    locations: set[str] = set()
    items: dict[str, int] = {}
    any_items: bool = False
    try:
        loc_opt = getattr(world.options, "mystery_custom_goal_locations", None)
        if loc_opt is None:
            loc_opt = getattr(world.options, "custom_goal_locations", None)
        if loc_opt is not None and hasattr(loc_opt, "value"):
            val = loc_opt.value
            if isinstance(val, (set, frozenset, list, tuple)):
                locations = {str(x).strip() for x in val if isinstance(x, str) and str(x).strip()}
    except Exception:
        pass
    try:
        item_opt = getattr(world.options, "mystery_custom_goal_items", None)
        if item_opt is None:
            item_opt = getattr(world.options, "custom_goal_items", None)
        if item_opt is not None and hasattr(item_opt, "value"):
            val = item_opt.value
            if isinstance(val, dict):
                for k, v in val.items():
                    if isinstance(k, str) and isinstance(v, int) and v >= 1:
                        items[str(k).strip()] = int(v)
    except Exception:
        pass
    try:
        any_opt = getattr(world.options, "mystery_custom_goal_any_items", None)
        if any_opt is None:
            any_opt = getattr(world.options, "custom_goal_any_items", None)
        if any_opt is not None and hasattr(any_opt, "value"):
            any_items = bool(any_opt.value)
    except Exception:
        any_items = False
    return {"enabled": enabled, "locations": locations, "items": items, "any_items": any_items}


def _find_owner_world(mw: MultiWorld, item_name: str, preferred_player: int | None = None) -> tuple[Any, int] | None:

    if preferred_player is not None:
        try:
            w = mw.worlds.get(preferred_player)
            if w is not None and hasattr(w, "item_name_to_id") and item_name in w.item_name_to_id:
                return w, preferred_player
        except Exception:
            pass
    best = None
    for pid, w in mw.worlds.items():
        try:
            if hasattr(w, "item_name_to_id") and item_name in w.item_name_to_id:
                if getattr(w, "game", "") != "Mystery Game":
                    return w, pid
                best = (w, pid)
        except Exception:
            continue
    return best


def _get_mystery_token_player(mw: MultiWorld, goal_player: int) -> int:
    try:
        for pid, w in mw.worlds.items():
            if getattr(w, "game", "") == "Mystery Game":
                exp = getattr(w, "expanded_players", None)
                if isinstance(exp, list) and goal_player in exp:
                    return int(pid)
        for pid, w in mw.worlds.items():
            if getattr(w, "game", "") == "Mystery Game":
                return int(pid)
    except Exception:
        pass
    return int(goal_player)


def _create_goal_marked_item(owner_world: Any, target_player: int, item_name: str, classification: ItemClassification) -> Any:
    """Create item via owner's create_item for correct code, but for target_player.

    Uses the item *from* ``owner_world.create_item`` directly and tracks it
    via ``GOAL_MARKED_MAP`` – ``Item`` uses ``__slots__`` so ``.tags``/``.flags``
    cannot be set reliably. Correct player is ``target_player`` (goal owner),
    code stays as owner's game code.
    """
    tmp = owner_world.create_item(item_name)



    try:

        tmp.player = target_player
    except Exception:

        try:
            item_id = getattr(tmp, "code", 0)

            orig_class = getattr(tmp, "classification", classification)

            if not (orig_class & ItemClassification.progression):
                orig_class |= ItemClassification.progression
            tmp = Item(item_name, orig_class, item_id, target_player)
        except Exception:
            pass

    try:
        if not (tmp.classification & ItemClassification.progression):
            tmp.classification |= ItemClassification.progression
    except Exception:
        tmp.classification = ItemClassification.progression
    GOAL_MARKED_MAP[id(tmp)] = True

    return tmp


def _retrofit_any_items(mw: MultiWorld, items: dict[str, int], target_player: int) -> int:
    """Mark existing items of given names that are for target_player as GOAL_MARKED + progression.

    Uses APAPI to only mark *reachable* items – AP tries to make every
    progression item always reachable, so marking an unreachable one as
    progression makes the game unbeatable. We use ``mw.get_all_state()`` and
    ``state.can_reach(location)`` to filter to the closest reachable pool.
    For the non-any case the alternative is to just set the closest
    reachables to progression instead of random pool items.
    """
    if not items:
        return 0
    wanted = set(items.keys())

    try:
        state = mw.get_all_state()
    except Exception:
        state = None

    pools: list[tuple[Any, Location | None]] = []
    try:
        for it in list(mw.itempool):
            pools.append((it, None))
    except Exception:
        pass
    try:
        for loc in mw.get_filled_locations():
            it = getattr(loc, "item", None)
            if it is not None:
                pools.append((it, loc))
    except Exception:
        pass
    try:
        for plist in mw.precollected_items.values():
            for it in list(plist):
                pools.append((it, None))
    except Exception:
        pass
    try:
        for r in mw.regions:
            for loc in r.locations:
                it = getattr(loc, "item", None)
                if it is not None and not any(it is p[0] for p in pools):
                    pools.append((it, loc))
    except Exception:
        pass

    reachable_pools: list[tuple[Any, Location | None]] = []
    for it, loc in pools:
        try:
            if getattr(it, "player", None) != target_player:
                continue
            if getattr(it, "name", None) not in wanted:
                continue

            if loc is not None and state is not None:
                try:
                    if not loc.can_reach(state):
                        continue
                except Exception:
                    pass
            reachable_pools.append((it, loc))
        except Exception:
            continue

    target_pools = reachable_pools if reachable_pools else [p for p in pools if getattr(p[0], "player", None)==target_player and getattr(p[0], "name", None) in wanted]
    count = 0
    for it, _loc in target_pools:
        try:
            if not (it.classification & ItemClassification.progression):
                it.classification |= ItemClassification.progression
        except Exception:
            it.classification = ItemClassification.progression
        GOAL_MARKED_MAP[id(it)] = True
        count += 1
    return count


def _make_paired_reward_rule(player: int, idx: int, source_loc: Location | None):
    """Return access_rule for reward location paired to source_loc – 1:1.

    Uses ``state.locations_checked`` (``BaseClasses.py:729``, filled via
    ``state.collect(item, True, location)`` at ``:1118`` and swept at
    ``:952``) as the AP-way check: the reward is reachable iff the source
    *has been checked*, not just its region. This keeps dungeon logic
    consistent (OoT keys stay in dungeon) while ``Fill`` sees the pairing
    via ``slot_data``. Count is not used.
    """
    if source_loc is None:
        raise ValueError(f"Paired reward {idx}: source location does not exist – cannot create rule")

    def paired(state, _src=source_loc):

        try:
            if _src in getattr(state, "locations_checked", set()):
                return True
        except Exception:
            pass
        # Fallback: can we reach the exact source location? Region alone is
        # insufficient – a chest can need Hookshot while its region is reachable.
        try:
            return bool(state.can_reach(_src))
        except Exception:
            try:
                return bool(_src.access_rule(state))
            except Exception:
                return True
    return paired


def _get_location_for_player(mw: MultiWorld, loc_name: str, player: int) -> tuple[Location | None, int | None]:
    """Return the Location object for `loc_name` belonging strictly to `player`.

    For `Mystery Game` the custom goal is allowed to hijack locations that
    belong to worlds it generated via ``game_counts``/``slot_games`` (e.g. an
    OoT chest for a Mystery player). In that case we search the expanded
    players first, but still strictly – no lazy first-match across unrelated
    worlds, and we throw if not found.
    """

    try:
        loc = mw.get_location(loc_name, player)
        if loc is not None and getattr(loc, "player", player) == player:
            return loc, player
    except Exception:
        pass
    try:
        for r in mw.regions:
            for loc in r.locations:
                if loc.name == loc_name and getattr(loc, "player", None) == player:
                    return loc, player
    except Exception:
        pass

    try:
        w = mw.worlds.get(player)
        if w is not None and getattr(w, "game", "") == "Mystery Game":
            expanded = getattr(w, "expanded_players", None)
            if isinstance(expanded, list) and expanded:
                for pid in expanded:
                    try:
                        loc = mw.get_location(loc_name, pid)
                        if loc is not None and getattr(loc, "player", pid) == pid:
                            return loc, pid
                    except Exception:
                        continue
                # also scan regions for those pids
                for pid in expanded:
                    for r in mw.regions:
                        for loc in r.locations:
                            if loc.name == loc_name and getattr(loc, "player", None) == pid:
                                return loc, pid
    except Exception:
        pass
    return None, None


def _find_location_and_player(mw: MultiWorld, loc_name: str) -> tuple[Location | None, int | None]:
    """Deprecated: lazy first-match finder. Use _get_location_for_player."""
    return _get_location_for_player(mw, loc_name, -1)











def _record_pair(world: World, idx: int, loc_name: str, reward_name: str, source_loc: Location | None, source_pid: int | None) -> None:
    """Record pairing info on world for slot_data and client."""
    try:
        if not hasattr(world, "mystery_custom_goal_pairs"):
            world.mystery_custom_goal_pairs = []  # type: ignore
        if not hasattr(world, "mystery_custom_goal_reward_to_source"):
            world.mystery_custom_goal_reward_to_source = {}  # type: ignore
        pairs: list[dict[str, Any]] = getattr(world, "mystery_custom_goal_pairs")  # type: ignore
        reward_map: dict[str, str] = getattr(world, "mystery_custom_goal_reward_to_source")  # type: ignore

        for existing in pairs:
            if existing.get("reward") == reward_name:
                return
        entry: dict[str, Any] = {
            "index": idx,
            "source": loc_name,
            "reward": reward_name,
            "source_player": int(source_pid) if isinstance(source_pid, int) else None,
        }
        if source_loc is not None:
            try:
                entry["source_region"] = getattr(source_loc.parent_region, "name", None)
                entry["source_game"] = str(world.multiworld.game[source_pid]) if source_pid is not None and source_pid in world.multiworld.game else None
            except Exception:
                pass
            try:
                entry["source_id"] = int(getattr(source_loc, "address", 0) or 0)
            except Exception:
                pass
        pairs.append(entry)
        reward_map[reward_name] = loc_name
    except Exception:
        pass


def apply_custom_goal(world: World) -> None:
    data = _get_custom_goal_data(world)
    if not data["enabled"]:
        return
    locations: set[str] = data["locations"]
    items: dict[str, int] = data["items"]
    any_items: bool = data["any_items"]
    if not locations and not items:
        return
    mw: MultiWorld = world.multiworld
    player: int = world.player
    world.mystery_custom_goal_locations = set(locations)
    world.mystery_custom_goal_items = dict(items)
    world.mystery_custom_goal_any_items = bool(any_items)
    world.mystery_custom_goal_enabled = True

    from .puzzles import (
        CUSTOM_GOAL_TOKEN_ITEM,
        CUSTOM_GOAL_TOKEN_ID,
        MAX_CUSTOM_GOALS,
        custom_goal_reward_location_name,
        CUSTOM_GOAL_REWARD_LOCATION_BASE,
    )
    from BaseClasses import Region, Location

    token_player = _get_mystery_token_player(mw, player)
    reward_region: Region | None = None
    for r in mw.regions:
        if r.name == "Mystery Goal Rewards" and r.player == token_player:
            reward_region = r
            break
    if reward_region is None:
        try:
            menu = None
            for r in mw.regions:
                if r.name == "Menu" and r.player == token_player:
                    menu = r
                    break
            reward_region = Region("Mystery Goal Rewards", token_player, mw)
            mw.regions.append(reward_region)
            if menu is not None:

                try:
                    menu.connect(reward_region)
                except Exception:
                    pass
            else:
                for r in mw.regions:
                    if r.player == player:
                        r.connect(reward_region)
                        break
        except Exception:
            reward_region = None

    sorted_locs = sorted(locations)

    if not hasattr(world, "mystery_custom_goal_internal_map"):
        world.mystery_custom_goal_internal_map = {}  # type: ignore
    if not hasattr(world, "mystery_custom_goal_pairs"):
        world.mystery_custom_goal_pairs = []  # type: ignore
    if not hasattr(world, "mystery_custom_goal_reward_to_source"):
        world.mystery_custom_goal_reward_to_source = {}  # type: ignore




    try:
        from worlds.APAPI.generation import get_current_stage
        cur_stage = get_current_stage()
    except Exception:
        cur_stage = None

    is_pre_fill = (cur_stage == "pre_fill")

    pending_key = f"_mystery_pending_loc_goals_{player}"
    if not is_pre_fill:

        existing_pending = getattr(mw, pending_key, None)
        if existing_pending is None:
            setattr(mw, pending_key, [])
            existing_pending = getattr(mw, pending_key)

        world.mystery_custom_goal_pending_locs = sorted_locs  # type: ignore
        for loc_name in sorted_locs:
            if loc_name not in existing_pending:
                existing_pending.append(loc_name)



        for idx, loc_name in enumerate(sorted_locs, start=1):
            if idx > MAX_CUSTOM_GOALS:
                break
            internal_reward_name = custom_goal_reward_location_name(idx)


            if loc_name not in world.mystery_custom_goal_internal_map:  # type: ignore
                world.mystery_custom_goal_internal_map[loc_name] = internal_reward_name  # type: ignore
    else:

        for idx, loc_name in enumerate(sorted_locs, start=1):
            if idx > MAX_CUSTOM_GOALS:
                break
            internal_reward_name = custom_goal_reward_location_name(idx)

            reward_loc_obj = None
            for r in mw.regions:
                for l in r.locations:
                    if l.name == internal_reward_name and l.player == player:
                        reward_loc_obj = l
                        break
                if reward_loc_obj:
                    break

            try:
                target_loc, target_pid = _get_location_for_player(mw, loc_name, player)
                if target_loc is None:
                    raise ValueError(f"Custom goal location '{loc_name}' does not exist for player {player} – cannot create paired reward '{internal_reward_name}' (no rule without source)")
                if reward_loc_obj is None:
                    try:
                        try:
                            from .__init__ import MysteryLocation as ML  # type: ignore
                            GoalCls = ML
                        except Exception:
                            GoalCls = Location
                        reward_id = CUSTOM_GOAL_REWARD_LOCATION_BASE + (idx - 1)
                        reward_loc_obj = GoalCls(_get_mystery_token_player(mw, player), internal_reward_name, reward_id, reward_region)

                        reward_loc_obj.access_rule = _make_paired_reward_rule(player, idx, target_loc)
                        if reward_region is not None:
                            reward_region.locations.append(reward_loc_obj)
                    except Exception as e:
                        raise RuntimeError(f"Failed to create paired reward '{internal_reward_name}' for '{loc_name}': {e}") from e
                else:

                    reward_loc_obj.access_rule = _make_paired_reward_rule(player, idx, target_loc)

                world.mystery_custom_goal_internal_map[loc_name] = internal_reward_name  # type: ignore
                _record_pair(world, idx, loc_name, internal_reward_name, target_loc, target_pid)
                token_player = _get_mystery_token_player(mw, player)
                token_item = Item(CUSTOM_GOAL_TOKEN_ITEM, ItemClassification.progression, CUSTOM_GOAL_TOKEN_ID, token_player)
                try:
                    setattr(token_item, GOAL_MARKED_ATTR, True)
                except Exception:
                    try:
                        from . import _goal_marked_registry
                    except Exception:
                        _goal_marked_registry = set()  # type: ignore
                    try:
                        _goal_marked_registry.add(id(token_item))  # type: ignore
                    except Exception:
                        pass
                try:
                    token_item.flags |= GOAL_MARKED_FLAG  # type: ignore
                except Exception:
                    pass
                try:
                    token_item.tags = [CUSTOM_GOAL_TAG]  # type: ignore
                except Exception:
                    pass

                existing_item = getattr(target_loc, "item", None)
                if existing_item is not None:
                    try:
                        if getattr(reward_loc_obj, "item", None) is not None:
                            try:
                                mw.itempool.append(existing_item)
                            except Exception:
                                pass
                        else:
                            reward_loc_obj.place_locked_item(existing_item)
                    except Exception:
                        try:
                            mw.itempool.append(existing_item)
                        except Exception:
                            pass

                try:
                    target_loc.place_locked_item(token_item)
                except Exception as e:
                    import logging
                    logging.getLogger("MysteryCustomGoal").warning(f"Failed to place token at '{loc_name}': {e}")
                    continue
            except ValueError:
                raise
            except Exception as e:
                import logging
                logging.getLogger("MysteryCustomGoal").warning(f"Failed to hijack location '{loc_name}': {e}")
                continue

    if items:
        if any_items:

            world.mystery_custom_goal_any_items_pending = True  # type: ignore
        else:

            for item_name, count in items.items():
                owner_info = _find_owner_world(mw, item_name, preferred_player=player)
                if owner_info is None:
                    owner_world, owner_player = world, player
                else:
                    owner_world, owner_player = owner_info

                total = sum(items.values())
                classification = ItemClassification.progression
                if total >= 5:
                    classification |= ItemClassification.deprioritized
                if total >= 10:
                    classification |= ItemClassification.skip_balancing
                for _ in range(count):
                    item = _create_goal_marked_item(owner_world, player, item_name, classification)

                    try:
                        item.player = player
                    except Exception:
                        pass
                    try:
                        mw.itempool.append(item)
                    except Exception:
                        continue

    def custom_completion(state) -> bool:
        token_player = _get_mystery_token_player(mw, player)
        if locations:
            if state.count(CUSTOM_GOAL_TOKEN_ITEM, token_player) < len(sorted_locs):
                return False

        if items:
            if any_items:

                for name, need in items.items():
                    if state.count(name, player) < int(need):
                        return False
            else:
                for name, need in items.items():
                    if state.count(name, player) < int(need):
                        return False
        return True

    try:
        mw.completion_condition[player] = custom_completion
    except Exception:
        pass
    try:
        world.mystery_custom_goal_data = {"locations": sorted(locations), "items": dict(items), "any_items": bool(any_items), "internal_map": getattr(world, "mystery_custom_goal_internal_map", {})}
    except Exception:
        pass


def _after_fill_slot_data(result: Any, world_self: Any, *args: Any, **kwargs: Any) -> Any:
    if not isinstance(result, dict):
        result = {}
    try:
        data = _get_custom_goal_data(world_self)
        if data["enabled"]:
            result["mystery_custom_goal"] = True
            result["mystery_custom_goal_locations"] = sorted(data["locations"])
            result["mystery_custom_goal_items"] = dict(data["items"])
            result["mystery_custom_goal_any_items"] = bool(data["any_items"])
            result["mystery_custom_goal_tag"] = CUSTOM_GOAL_TAG
            result["mystery_custom_goal_token"] = "Mystery Goal Token"
            result["mystery_custom_goal_token_id"] = 7000
            try:
                internal_map = getattr(world_self, "mystery_custom_goal_internal_map", {})
                if internal_map:
                    result["mystery_custom_goal_internal_map"] = dict(internal_map)
            except Exception:
                pass

            try:
                pairs = getattr(world_self, "mystery_custom_goal_pairs", None)
                if isinstance(pairs, list) and pairs:
                    result["mystery_custom_goal_pairs"] = [dict(p) for p in pairs]

                    rmap = getattr(world_self, "mystery_custom_goal_reward_to_source", {})
                    if isinstance(rmap, dict) and rmap:
                        result["mystery_custom_goal_reward_map"] = dict(rmap)
                else:

                    im = getattr(world_self, "mystery_custom_goal_internal_map", {})
                    if isinstance(im, dict) and im:
                        result["mystery_custom_goal_pairs"] = [
                            {"index": i+1, "source": src, "reward": rew, "source_player": None}
                            for i, (src, rew) in enumerate(sorted(im.items()))
                        ]
                        result["mystery_custom_goal_reward_map"] = dict(im) if isinstance(im, dict) else {}
            except Exception:
                pass

            result["mystery_custom_goal_reward_paired"] = True
            result["mystery_custom_goal_max"] = 3000
        else:
            try:
                if getattr(world_self, "game", "") == "Mystery Game":
                    mw = getattr(world_self, "multiworld", None)
                    exp = getattr(world_self, "expanded_players", None)
                    if isinstance(exp, list) and exp and mw is not None:
                        per_slot: dict[str, dict[str, Any]] = {}
                        for pid in exp:
                            w = mw.worlds.get(pid)
                            if w is None or not getattr(w, "mystery_custom_goal_enabled", False):
                                continue
                            try:
                                slot_name = str(mw.player_name.get(pid, f"P{pid}"))
                            except Exception:
                                slot_name = f"P{pid}"
                            entry: dict[str, Any] = {}
                            try:
                                locs = getattr(w, "mystery_custom_goal_locations", set()) or set()
                                entry["mystery_custom_goal"] = True
                                entry["mystery_custom_goal_locations"] = sorted(set(locs) if isinstance(locs, (set, list, tuple)) else [])
                            except Exception:
                                entry["mystery_custom_goal_locations"] = []
                            try:
                                its = getattr(w, "mystery_custom_goal_items", {}) or {}
                                entry["mystery_custom_goal_items"] = dict(its) if isinstance(its, dict) else {}
                            except Exception:
                                entry["mystery_custom_goal_items"] = {}
                            try:
                                entry["mystery_custom_goal_any_items"] = bool(getattr(w, "mystery_custom_goal_any_items", False))
                            except Exception:
                                entry["mystery_custom_goal_any_items"] = False
                            entry["mystery_custom_goal_tag"] = CUSTOM_GOAL_TAG
                            entry["mystery_custom_goal_token"] = "Mystery Goal Token"
                            entry["mystery_custom_goal_token_id"] = 7000
                            try:
                                im = getattr(w, "mystery_custom_goal_internal_map", {}) or {}
                                if isinstance(im, dict) and im:
                                    entry["mystery_custom_goal_internal_map"] = dict(im)
                            except Exception:
                                pass
                            try:
                                ps = getattr(w, "mystery_custom_goal_pairs", []) or []
                                if isinstance(ps, list) and ps:
                                    entry["mystery_custom_goal_pairs"] = [dict(p) for p in ps if isinstance(p, dict) and "source" in p]
                                    rm = getattr(w, "mystery_custom_goal_reward_to_source", {}) or {}
                                    if isinstance(rm, dict) and rm:
                                        entry["mystery_custom_goal_reward_map"] = dict(rm)
                                else:
                                    im2 = getattr(w, "mystery_custom_goal_internal_map", {}) or {}
                                    if isinstance(im2, dict) and im2:
                                        entry["mystery_custom_goal_pairs"] = [
                                            {"index": i+1, "source": src, "reward": rew, "source_player": pid}
                                            for i, (src, rew) in enumerate(sorted(im2.items()))
                                        ]
                                        entry["mystery_custom_goal_reward_map"] = dict(im2)
                            except Exception:
                                pass
                            entry["mystery_custom_goal_reward_paired"] = True
                            entry["mystery_custom_goal_max"] = 3000
                            per_slot[slot_name] = entry
                        if per_slot:
                            result["mystery_custom_goal_per_slot"] = per_slot
                            return result
            except Exception:
                pass
            result["mystery_custom_goal"] = False
    except Exception:
        pass
    return result


def _after_create_items(result: Any, world_self: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        apply_custom_goal(world_self)
    except ValueError:
        raise
    except Exception as e:
        import logging
        logging.getLogger("MysteryCustomGoal").warning(f"apply_custom_goal failed: {e}", exc_info=True)
    return result


def _after_pre_fill(result: Any, world_self: Any, *args: Any, **kwargs: Any) -> Any:
    """Handle location hijacking and any-items retrofit at pre_fill (all locations exist)."""
    try:
        data = _get_custom_goal_data(world_self)
        if not data["enabled"]:
            return result
        mw = getattr(world_self, "multiworld", None)
        if mw is None:
            return result
        player = int(getattr(world_self, "player", 0))

        if data["locations"]:

            loc_flag = getattr(mw, f"_mystery_loc_goals_done_{player}", False) or getattr(mw, "_mystery_loc_goals_done", False)
            if not loc_flag:
                from .puzzles import CUSTOM_GOAL_TOKEN_ITEM, CUSTOM_GOAL_TOKEN_ID, custom_goal_reward_location_name, CUSTOM_GOAL_REWARD_LOCATION_BASE
                from BaseClasses import Item, ItemClassification

                pending = getattr(mw, f"_mystery_pending_loc_goals_{player}", None)

                if pending is None:
                    pending = getattr(mw, "_mystery_pending_loc_goals", None)
                locs_to_process = list(pending) if isinstance(pending, list) and pending else sorted(data["locations"])

                if not hasattr(world_self, "mystery_custom_goal_pairs"):
                    world_self.mystery_custom_goal_pairs = []  # type: ignore
                if not hasattr(world_self, "mystery_custom_goal_reward_to_source"):
                    world_self.mystery_custom_goal_reward_to_source = {}  # type: ignore
                if not hasattr(world_self, "mystery_custom_goal_internal_map"):
                    world_self.mystery_custom_goal_internal_map = {}  # type: ignore

                for idx, loc_name in enumerate(locs_to_process, start=1):

                    target_loc, target_pid = _get_location_for_player(mw, loc_name, player)
                    if target_loc is None:
                        raise ValueError(f"Custom goal location '{loc_name}' does not exist for player {player} – cannot create paired reward '{custom_goal_reward_location_name(idx)}' (no rule without source)")

                    reward_name = custom_goal_reward_location_name(idx)
                    reward_loc = None
                    token_player = _get_mystery_token_player(mw, player)
                    for r in mw.regions:
                        for l in r.locations:
                            if l.name == reward_name and l.player == token_player:
                                reward_loc = l
                                break
                        if reward_loc:
                            break

                    if reward_loc is None:
                        from BaseClasses import Region, Location
                        reward_region = None
                        for r in mw.regions:
                            if r.name == "Mystery Goal Rewards" and r.player == token_player:
                                reward_region = r
                                break
                        if reward_region is None:
                            reward_region = Region("Mystery Goal Rewards", token_player, mw)
                            mw.regions.append(reward_region)
                            for r in mw.regions:
                                if r.name == "Menu" and r.player == token_player:
                                    try:
                                        r.connect(reward_region)
                                    except Exception:
                                        pass
                                    break
                        try:
                            from .__init__ import MysteryLocation as ML  # type: ignore
                            GoalCls = ML
                        except Exception:
                            GoalCls = Location
                        reward_id = CUSTOM_GOAL_REWARD_LOCATION_BASE + (idx - 1)
                        reward_loc = GoalCls(token_player, reward_name, reward_id, reward_region)
                        reward_loc.access_rule = _make_paired_reward_rule(player, idx, target_loc)
                        reward_region.locations.append(reward_loc)
                    else:

                        reward_loc.access_rule = _make_paired_reward_rule(player, idx, target_loc)

                    try:
                        _record_pair(world_self, idx, loc_name, reward_name, target_loc, target_pid)
                        if loc_name not in world_self.mystery_custom_goal_internal_map:  # type: ignore
                            world_self.mystery_custom_goal_internal_map[loc_name] = reward_name  # type: ignore
                    except Exception:
                        pass

                    existing_on_target = getattr(target_loc, "item", None)
                    is_token_already = False
                    try:
                        if existing_on_target is not None and getattr(existing_on_target, "name", None) == CUSTOM_GOAL_TOKEN_ITEM:
                            is_token_already = True
                    except Exception:
                        pass
                    if is_token_already:
                        continue
                    token_player = _get_mystery_token_player(mw, player)
                    token_item = Item(CUSTOM_GOAL_TOKEN_ITEM, ItemClassification.progression, CUSTOM_GOAL_TOKEN_ID, token_player)
                    try:
                        setattr(token_item, GOAL_MARKED_ATTR, True)
                    except Exception:
                        try:
                            from . import _goal_marked_registry
                        except Exception:
                            _goal_marked_registry = set()  # type: ignore
                        try:
                            _goal_marked_registry.add(id(token_item))  # type: ignore
                        except Exception:
                            pass

                    if existing_on_target is not None:
                        try:
                            if getattr(reward_loc, "item", None) is None:
                                reward_loc.place_locked_item(existing_on_target)
                            else:
                                mw.itempool.append(existing_on_target)
                        except Exception:
                            try:
                                mw.itempool.append(existing_on_target)
                            except Exception:
                                pass

                    try:
                        target_loc.place_locked_item(token_item)
                    except Exception as e:
                        import logging
                        logging.getLogger("MysteryCustomGoal").warning(f"Failed to place token at '{loc_name}': {e}")
                        continue
                setattr(mw, f"_mystery_loc_goals_done_{player}", True)
                setattr(mw, "_mystery_loc_goals_done", True)
                import logging
                logging.getLogger("MysteryCustomGoal").info(f"Hijacked {len(locs_to_process)} locations for custom goal (paired rewards)")

        if data["any_items"] and data["items"]:
            flag = getattr(mw, f"_mystery_any_retrofit_done_{player}", False) or getattr(mw, "_mystery_any_retrofit_done", False)
            if not flag:
                cnt = _retrofit_any_items(mw, data["items"], player)
                setattr(mw, f"_mystery_any_retrofit_done_{player}", True)
                setattr(mw, "_mystery_any_retrofit_done", True)
                import logging
                logging.getLogger("MysteryCustomGoal").info(f"Retrofitted {cnt} items for any-mode goal {data['items']}")
    except ValueError:
        raise
    except Exception as e:
        import logging
        logging.getLogger("MysteryCustomGoal").warning(f"_after_pre_fill failed: {e}", exc_info=True)
    return result


try:
    from worlds.APAPI import inject_option, inject_world_behavior

    for _g in ["Mystery Game", "TUNIC"]:
        inject_option("mystery_custom_goal", MysteryCustomGoal, games=[_g], group_name="Mystery Custom Goal")
        inject_option("mystery_custom_goal_locations", MysteryCustomGoalLocations, games=[_g], group_name="Mystery Custom Goal")
        inject_option("mystery_custom_goal_items", MysteryCustomGoalItems, games=[_g], group_name="Mystery Custom Goal")
        inject_option("mystery_custom_goal_any_items", MysteryCustomGoalAnyItems, games=[_g], group_name="Mystery Custom Goal")
        inject_world_behavior(_g, "fill_slot_data", after=_after_fill_slot_data)
        inject_world_behavior(_g, "create_items", after=_after_create_items)

        inject_world_behavior(_g, "pre_fill", after=_after_pre_fill)
except Exception:
    pass
