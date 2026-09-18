from __future__ import annotations

from worlds.AutoWorld import World

"""Custom Goal for Mystery Game. Toggle with location and item goals."""

from typing import Any

from BaseClasses import Item, ItemClassification, Location, MultiWorld
from Options import OptionDict, OptionSet, Toggle


class MysteryCustomGoal(Toggle):
    """Enable custom goal for this Mystery slot. When on, use goal locations or items."""

    display_name = "Custom Goal"
    default = False


class MysteryCustomGoalLocations(OptionSet):
    """Location names that must be reached for custom goal. Each gets a special progression item."""

    display_name = "Custom Goal Locations"
    default = frozenset()
    supports_weighting = False


class MysteryCustomGoalItems(OptionDict):
    """Item goals for custom goal. Map item name to count required. Adds progression items tagged for goal."""

    display_name = "Custom Goal Items"
    default = {}
    supports_weighting = False

    def verify(self, world: Any, player_name: str, plando_options: Any) -> None:
        for name, count in dict(self.value).items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Custom goal item name must be non-empty string for {player_name}.")
            if not isinstance(count, int) or count < 1:
                raise ValueError(f"Custom goal count for {name!r} must be >=1 for {player_name}.")


CUSTOM_GOAL_TAG = "mystery_custom_goal"
CUSTOM_GOAL_TOKEN_PREFIX = "Mystery Goal Token: "


def _get_custom_goal_data(world: World) -> dict[str, Any]:
    """Extract custom goal data from world options. Returns dict with enabled, locations, items."""
    try:
        enabled = bool(getattr(world.options, "mystery_custom_goal", None) and world.options.mystery_custom_goal.value)
    except Exception:
        enabled = False
    if not enabled:
        try:
            # Also check without prefix (direct)
            enabled = bool(getattr(world.options, "custom_goal", None) and world.options.custom_goal.value)
        except Exception:
            pass
    locations: set[str] = set()
    items: dict[str, int] = {}
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
    return {"enabled": enabled, "locations": locations, "items": items}


def apply_custom_goal(world: World) -> None:
    """Apply custom goal to Mystery world. Called during generate."""
    data = _get_custom_goal_data(world)
    if not data["enabled"]:
        return
    locations: set[str] = data["locations"]
    items: dict[str, int] = data["items"]
    if not locations and not items:
        return
    mw: MultiWorld = world.multiworld
    player: int = world.player
    # Tag and create items, set completion
    # For location goals: place a special token at each location
    # For item goals: add progression items to pool
    # We will store goal info on world for client
    world.mystery_custom_goal_locations = set(locations)
    world.mystery_custom_goal_items = dict(items)
    world.mystery_custom_goal_enabled = True
    # Create special items for locations
    for loc_name in locations:
        token_name = f"{CUSTOM_GOAL_TOKEN_PREFIX}{loc_name}"
        # Use existing item id if available, else create new
        # We will create a new item with custom classification
        try:
            item_id = world.location_name_to_id.get(loc_name) or world.item_name_to_id.get(token_name) or 0
        except Exception:
            item_id = 0
        # Create item
        try:
            item = Item(token_name, ItemClassification.progression, item_id, player)
            item.tags = [CUSTOM_GOAL_TAG]  # type: ignore[attr-defined]
            # Try to place at location if it exists in this world
            loc = None
            try:
                loc = mw.get_location(loc_name, player)
            except Exception:
                # Try to find in any of Mystery's controlled worlds?
                # For Mystery, locations are in the Mystery world itself (puzzle/unlock), but custom locations likely refer to underlying real games
                # Search all worlds for that location name
                for pid, w in mw.worlds.items():
                    if pid == player:
                        continue
                    # Only consider worlds that are Mystery-controlled?
                    try:
                        loc = mw.get_location(loc_name, pid)
                        if loc is not None:
                            break
                    except Exception:
                        continue
            if loc is not None:
                # Place token at location, make it progression
                try:
                    loc.place_locked_item(item)
                except Exception:
                    # If location already has item, add to pool
                    mw.itempool.append(item)
            else:
                # Location not found, add to pool as fallback (will be placed somewhere)
                mw.itempool.append(item)
        except Exception:
            continue
    # For item goals: add progression items
    for item_name, count in items.items():
        for _ in range(count):
            try:
                # Determine item id
                item_id = None
                # Try to get from world's item pool
                try:
                    item_id = world.item_name_to_id.get(item_name)
                except Exception:
                    pass
                if item_id is None:
                    # Try to find in any world's items
                    for w in mw.worlds.values():
                        try:
                            if hasattr(w, "item_name_to_id") and item_name in w.item_name_to_id:
                                item_id = w.item_name_to_id[item_name]
                                break
                        except Exception:
                            continue
                if item_id is None:
                    item_id = 0
                classification = ItemClassification.progression
                # If many items, add deprioritized and skip balancing
                total = sum(items.values())
                if total >= 5:
                    classification |= ItemClassification.deprioritized
                if total >= 10:
                    classification |= ItemClassification.skip_balancing
                item = Item(item_name, classification, item_id or 0, player)
                # Tag
                try:
                    existing_tags = getattr(item, "tags", [])
                    if not isinstance(existing_tags, list):
                        existing_tags = []
                    if CUSTOM_GOAL_TAG not in existing_tags:
                        existing_tags.append(CUSTOM_GOAL_TAG)
                    item.tags = existing_tags  # type: ignore[attr-defined]
                except Exception:
                    pass
                mw.itempool.append(item)
            except Exception:
                continue
    # Set completion condition
    def custom_completion(state) -> bool:
        # Check locations: need special tokens
        for loc_name in locations:
            token_name = f"{CUSTOM_GOAL_TOKEN_PREFIX}{loc_name}"
            if not state.has(token_name, player):
                return False
        # Check items: need counts
        for item_name, count in items.items():
            if state.count(item_name, player) < count:
                return False
        return True

    try:
        mw.completion_condition[player] = custom_completion
    except Exception:
        pass
    # Store for slot_data
    try:
        world.mystery_custom_goal_data = {"locations": sorted(locations), "items": dict(items)}
    except Exception:
        pass


def _after_fill_slot_data(result: Any, world_self: Any, *args: Any, **kwargs: Any) -> Any:
    """Add custom goal info to slot_data for client."""
    if not isinstance(result, dict):
        result = {}
    try:
        data = _get_custom_goal_data(world_self)
        if data["enabled"]:
            result["mystery_custom_goal"] = True
            result["mystery_custom_goal_locations"] = sorted(data["locations"])
            result["mystery_custom_goal_items"] = dict(data["items"])
            result["mystery_custom_goal_tag"] = CUSTOM_GOAL_TAG
        else:
            result["mystery_custom_goal"] = False
    except Exception:
        pass
    return result


def _after_create_items(result: Any, world_self: Any, *args: Any, **kwargs: Any) -> Any:
    """Apply custom goal after items are created. Called via APAPI."""
    try:
        apply_custom_goal(world_self)
    except Exception:
        pass
    return result


try:
    from worlds.APAPI import inject_option, inject_world_behavior

    inject_option("mystery_custom_goal", MysteryCustomGoal, games=["Mystery Game"], group_name="Mystery Custom Goal")
    inject_option("mystery_custom_goal_locations", MysteryCustomGoalLocations, games=["Mystery Game"], group_name="Mystery Custom Goal")
    inject_option("mystery_custom_goal_items", MysteryCustomGoalItems, games=["Mystery Game"], group_name="Mystery Custom Goal")

    inject_world_behavior("Mystery Game", "fill_slot_data", after=_after_fill_slot_data)
    inject_world_behavior("Mystery Game", "create_items", after=_after_create_items)
except Exception:
    pass
