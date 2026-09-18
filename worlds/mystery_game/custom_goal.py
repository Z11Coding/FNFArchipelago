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
GOAL_MARKED_FLAG: int = 8  # custom flag (1=prog,2=useful,4=trap,8=goal)

# Mapping for goal-marked items – Item uses __slots__ so we cannot set .tags/.flags reliably.
# Use id(item) -> True instead. Client checks this mapping via slot_data.
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
    # Prefer the preferred_player's own world if it has the item (strict per-player)
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


def _create_goal_marked_item(owner_world: Any, target_player: int, item_name: str, classification: ItemClassification) -> Any:
    """Create item via owner's create_item for correct code, but for target_player.

    Uses the item *from* ``owner_world.create_item`` directly and tracks it
    via ``GOAL_MARKED_MAP`` – ``Item`` uses ``__slots__`` so ``.tags``/``.flags``
    cannot be set reliably. Correct player is ``target_player`` (goal owner),
    code stays as owner's game code.
    """
    tmp = owner_world.create_item(item_name)
    # Use the item *from* create_item directly – do not clone via Item() which
    # would lose the correct code/flags for cross-game items.
    # Just retarget player and ensure mapping.
    try:
        # Directly retarget – Item.__slots__ allows player assignment
        tmp.player = target_player
    except Exception:
        # Fallback: if player is read-only, create new Item with same code
        try:
            item_id = getattr(tmp, "code", 0)
            # Preserve original classification unless overridden
            orig_class = getattr(tmp, "classification", classification)
            # Ensure at least progression
            if not (orig_class & ItemClassification.progression):
                orig_class |= ItemClassification.progression
            tmp = Item(item_name, orig_class, item_id, target_player)
        except Exception:
            pass
    # Ensure at least progression
    try:
        if not (tmp.classification & ItemClassification.progression):
            tmp.classification |= ItemClassification.progression
    except Exception:
        tmp.classification = ItemClassification.progression
    GOAL_MARKED_MAP[id(tmp)] = True
    # Also mark via classification flag for Fill's advancement check (AP tries to make every progression reachable)
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
    # Build reachable set via APAPI – generic, not Mystery-only
    try:
        state = mw.get_all_state()
    except Exception:
        state = None
    # Collect pools with their location (if any) for reachability check
    pools: list[tuple[Any, Location | None]] = []
    try:
        for it in list(mw.itempool):
            pools.append((it, None))  # itempool has no location yet – treat as reachable
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
    # Filter to reachable only when possible – use APAPI's can_reach
    reachable_pools: list[tuple[Any, Location | None]] = []
    for it, loc in pools:
        try:
            if getattr(it, "player", None) != target_player:
                continue
            if getattr(it, "name", None) not in wanted:
                continue
            # If it has a location, require that location be reachable
            if loc is not None and state is not None:
                try:
                    if not loc.can_reach(state):
                        continue
                except Exception:
                    pass
            reachable_pools.append((it, loc))
        except Exception:
            continue
    # If none reachable, fall back to any (so we still mark something)
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
        # Primary: has the source been checked? (Fill-aware)
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
    # Primary: exact player
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
    # Mystery cross-game: allow locations from worlds Mystery generated
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
    return _get_location_for_player(mw, loc_name, -1)  # will not find; kept for compat
    # fallback legacy behavior if needed:
    # for pid in list(mw.worlds.keys()):
    #     try:
    #         loc = mw.get_location(loc_name, pid)
    #         if loc is not None:
    #             return loc, pid
    #     except Exception:
    #         continue
    # return None, None


def _record_pair(world: World, idx: int, loc_name: str, reward_name: str, source_loc: Location | None, source_pid: int | None) -> None:
    """Record pairing info on world for slot_data and client."""
    try:
        if not hasattr(world, "mystery_custom_goal_pairs"):
            world.mystery_custom_goal_pairs = []  # type: ignore
        if not hasattr(world, "mystery_custom_goal_reward_to_source"):
            world.mystery_custom_goal_reward_to_source = {}  # type: ignore
        pairs: list[dict[str, Any]] = getattr(world, "mystery_custom_goal_pairs")  # type: ignore
        reward_map: dict[str, str] = getattr(world, "mystery_custom_goal_reward_to_source")  # type: ignore
        # Avoid duplicates
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

    # For location goals: use existing game locations as goals.
    # Ensure Mystery has a reward region for the displaced items.
    reward_region: Region | None = None
    for r in mw.regions:
        if r.name == "Mystery Goal Rewards" and r.player == player:
            reward_region = r
            break
    if reward_region is None:
        try:
            # Find Menu to connect, else first Mystery region
            menu = None
            for r in mw.regions:
                if r.name == "Menu" and r.player == player:
                    menu = r
                    break
            reward_region = Region("Mystery Goal Rewards", player, mw)
            mw.regions.append(reward_region)
            if menu is not None:
                # Connect via Puzzle Hall or directly - ensure reachable after Menu
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
    # Keep internal_map for backwards compat, but now keys are the existing loc names
    if not hasattr(world, "mystery_custom_goal_internal_map"):
        world.mystery_custom_goal_internal_map = {}  # type: ignore
    if not hasattr(world, "mystery_custom_goal_pairs"):
        world.mystery_custom_goal_pairs = []  # type: ignore
    if not hasattr(world, "mystery_custom_goal_reward_to_source"):
        world.mystery_custom_goal_reward_to_source = {}  # type: ignore
    # Defer actual placement to pre_fill to ensure all locations exist; if we are in create_items, just validate existence.
    # We will handle placement in a pre_fill hook if needed, but for now handle immediately if loc exists.
    # To ensure we run at a safe time (pre_fill), we store pending locations and let the pre_fill hook do the work.
    # If we are currently in pre_fill, do the placement now; otherwise, defer.
    try:
        from worlds.APAPI.generation import get_current_stage
        cur_stage = get_current_stage()
    except Exception:
        cur_stage = None
    # If not in pre_fill and not all locations may exist yet, defer the actual hijack to pre_fill
    is_pre_fill = (cur_stage == "pre_fill")
    # Store pending for pre_fill – per-player to avoid cross-world contamination
    pending_key = f"_mystery_pending_loc_goals_{player}"
    if not is_pre_fill:
        # In create_items stage: validate existence and queue for pre_fill
        existing_pending = getattr(mw, pending_key, None)
        if existing_pending is None:
            setattr(mw, pending_key, [])
            existing_pending = getattr(mw, pending_key)
        # Also store on world for slot_data
        world.mystery_custom_goal_pending_locs = sorted_locs  # type: ignore
        for loc_name in sorted_locs:
            if loc_name not in existing_pending:
                existing_pending.append(loc_name)
        # Defer reward creation to pre_fill when source locations are guaranteed to exist.
        # Do not create placeholders here – rewards are paired 1:1 and must be able to
        # copy the source's reachability. If the source does not exist we throw.
        for idx, loc_name in enumerate(sorted_locs, start=1):
            if idx > MAX_CUSTOM_GOALS:
                break
            internal_reward_name = custom_goal_reward_location_name(idx)
            # Only record internal map entry for slot_data preview; actual Location
            # and paired rule are created in pre_fill.
            if loc_name not in world.mystery_custom_goal_internal_map:  # type: ignore
                world.mystery_custom_goal_internal_map[loc_name] = internal_reward_name  # type: ignore
    else:
        # In pre_fill: do the actual hijack of existing locations and pair rewards
        for idx, loc_name in enumerate(sorted_locs, start=1):
            if idx > MAX_CUSTOM_GOALS:
                break
            internal_reward_name = custom_goal_reward_location_name(idx)
            # Find or create reward loc
            reward_loc_obj = None
            for r in mw.regions:
                for l in r.locations:
                    if l.name == internal_reward_name and l.player == player:
                        reward_loc_obj = l
                        break
                if reward_loc_obj:
                    break
            # Find the existing location to hijack – must exist on the player who set the goal or we throw
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
                        reward_loc_obj = GoalCls(player, internal_reward_name, reward_id, reward_region)
                        # Paired rule: reachable iff source item can be collected
                        reward_loc_obj.access_rule = _make_paired_reward_rule(player, idx, target_loc)
                        if reward_region is not None:
                            reward_region.locations.append(reward_loc_obj)
                    except Exception as e:
                        raise RuntimeError(f"Failed to create paired reward '{internal_reward_name}' for '{loc_name}': {e}") from e
                else:
                    # Upgrade existing placeholder to paired rule
                    reward_loc_obj.access_rule = _make_paired_reward_rule(player, idx, target_loc)
                # Record pairing with full source info
                world.mystery_custom_goal_internal_map[loc_name] = internal_reward_name  # type: ignore
                _record_pair(world, idx, loc_name, internal_reward_name, target_loc, target_pid)
                # Create token
                token_item = Item(CUSTOM_GOAL_TOKEN_ITEM, ItemClassification.progression, CUSTOM_GOAL_TOKEN_ID, player)
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
                # If target already has an item (locked), move it to reward
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
                # Place token at the existing location
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
            # Any mode: will retrofit after all items are created (pre_fill hook)
            world.mystery_custom_goal_any_items_pending = True  # type: ignore
        else:
            # Specific mode: create GOAL_MARKED items for Mystery player using owner template
            for item_name, count in items.items():
                owner_info = _find_owner_world(mw, item_name, preferred_player=player)
                if owner_info is None:
                    owner_world, owner_player = world, player
                else:
                    owner_world, owner_player = owner_info
                    # Use Mystery player as target, but owner_world for template
                total = sum(items.values())
                classification = ItemClassification.progression
                if total >= 5:
                    classification |= ItemClassification.deprioritized
                if total >= 10:
                    classification |= ItemClassification.skip_balancing
                for _ in range(count):
                    item = _create_goal_marked_item(owner_world, player, item_name, classification)
                    # Ensure player is Mystery
                    try:
                        item.player = player
                    except Exception:
                        pass
                    try:
                        mw.itempool.append(item)
                    except Exception:
                        continue

    def custom_completion(state) -> bool:
        # Locations: need enough Goal Tokens
        if locations:
            # Internal goal count is len(sorted_locs) but we use tokens count
            if state.count(CUSTOM_GOAL_TOKEN_ITEM, player) < len(sorted_locs):
                return False
        # Items
        if items:
            if any_items:
                # Any item: count any matching item for Mystery player
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
            result["mystery_custom_goal_token_id"] = 7000  # placeholder, client uses names
            try:
                internal_map = getattr(world_self, "mystery_custom_goal_internal_map", {})
                if internal_map:
                    result["mystery_custom_goal_internal_map"] = dict(internal_map)
            except Exception:
                pass
            # New: paired reward info for client/logic transparency
            try:
                pairs = getattr(world_self, "mystery_custom_goal_pairs", None)
                if isinstance(pairs, list) and pairs:
                    result["mystery_custom_goal_pairs"] = [dict(p) for p in pairs]
                    # Also provide reward -> source map
                    rmap = getattr(world_self, "mystery_custom_goal_reward_to_source", {})
                    if isinstance(rmap, dict) and rmap:
                        result["mystery_custom_goal_reward_map"] = dict(rmap)
                else:
                    # Fallback: build from internal_map if pairs not yet built
                    im = getattr(world_self, "mystery_custom_goal_internal_map", {})
                    if isinstance(im, dict) and im:
                        result["mystery_custom_goal_pairs"] = [
                            {"index": i+1, "source": src, "reward": rew, "source_player": None}
                            for i, (src, rew) in enumerate(sorted(im.items()))
                        ]
                        result["mystery_custom_goal_reward_map"] = dict(im) if isinstance(im, dict) else {}
            except Exception:
                pass
            # Expose pairing rule type for client info (always paired now)
            result["mystery_custom_goal_reward_paired"] = True
            result["mystery_custom_goal_max"] = 3000
        else:
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
        # --- Location goals: hijack existing locations at pre_fill ---
        if data["locations"]:
            # Only run once
            loc_flag = getattr(mw, f"_mystery_loc_goals_done_{player}", False) or getattr(mw, "_mystery_loc_goals_done", False)
            if not loc_flag:
                from .puzzles import CUSTOM_GOAL_TOKEN_ITEM, CUSTOM_GOAL_TOKEN_ID, custom_goal_reward_location_name, CUSTOM_GOAL_REWARD_LOCATION_BASE
                from BaseClasses import Item, ItemClassification
                # Find pending locs (queued at create_items) per-player or use current data
                pending = getattr(mw, f"_mystery_pending_loc_goals_{player}", None)
                # Fallback to legacy global key for old saves
                if pending is None:
                    pending = getattr(mw, "_mystery_pending_loc_goals", None)
                locs_to_process = list(pending) if isinstance(pending, list) and pending else sorted(data["locations"])
                # Ensure pairs structures exist
                if not hasattr(world_self, "mystery_custom_goal_pairs"):
                    world_self.mystery_custom_goal_pairs = []  # type: ignore
                if not hasattr(world_self, "mystery_custom_goal_reward_to_source"):
                    world_self.mystery_custom_goal_reward_to_source = {}  # type: ignore
                if not hasattr(world_self, "mystery_custom_goal_internal_map"):
                    world_self.mystery_custom_goal_internal_map = {}  # type: ignore
                # Now hijack each existing location
                for idx, loc_name in enumerate(locs_to_process, start=1):
                    # Find source location strictly for the player who owns the custom goal
                    target_loc, target_pid = _get_location_for_player(mw, loc_name, player)
                    if target_loc is None:
                        raise ValueError(f"Custom goal location '{loc_name}' does not exist for player {player} – cannot create paired reward '{custom_goal_reward_location_name(idx)}' (no rule without source)")
                    # Find its reward location
                    reward_name = custom_goal_reward_location_name(idx)
                    reward_loc = None
                    for r in mw.regions:
                        for l in r.locations:
                            if l.name == reward_name and l.player == player:
                                reward_loc = l
                                break
                        if reward_loc:
                            break
                    # If reward not yet created, create it now with paired reachability
                    if reward_loc is None:
                        from BaseClasses import Region, Location
                        # Find reward region
                        reward_region = None
                        for r in mw.regions:
                            if r.name == "Mystery Goal Rewards" and r.player == player:
                                reward_region = r
                                break
                        if reward_region is None:
                            reward_region = Region("Mystery Goal Rewards", player, mw)
                            mw.regions.append(reward_region)
                            for r in mw.regions:
                                if r.name == "Menu" and r.player == player:
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
                        reward_loc = GoalCls(player, reward_name, reward_id, reward_region)
                        reward_loc.access_rule = _make_paired_reward_rule(player, idx, target_loc)
                        reward_region.locations.append(reward_loc)
                    else:
                        # Update rule to paired (source must be reachable)
                        reward_loc.access_rule = _make_paired_reward_rule(player, idx, target_loc)
                    # Record pairing (idempotent)
                    try:
                        _record_pair(world_self, idx, loc_name, reward_name, target_loc, target_pid)
                        if loc_name not in world_self.mystery_custom_goal_internal_map:  # type: ignore
                            world_self.mystery_custom_goal_internal_map[loc_name] = reward_name  # type: ignore
                    except Exception:
                        pass
                    # Create token if not already placed (idempotent check)
                    existing_on_target = getattr(target_loc, "item", None)
                    is_token_already = False
                    try:
                        if existing_on_target is not None and getattr(existing_on_target, "name", None) == CUSTOM_GOAL_TOKEN_ITEM:
                            is_token_already = True
                    except Exception:
                        pass
                    if is_token_already:
                        continue
                    token_item = Item(CUSTOM_GOAL_TOKEN_ITEM, ItemClassification.progression, CUSTOM_GOAL_TOKEN_ID, player)
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
                    # Move displaced item if any (should be None at this stage, but handle locked)
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
                    # Place token at the existing location (hijack)
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
        # --- Any-items retrofit ---
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
        # Any-mode retrofit at pre_fill (after all create_items)
        inject_world_behavior(_g, "pre_fill", after=_after_pre_fill)
except Exception:
    pass
