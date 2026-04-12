# ItemLink Distribution - Quick Reference

## Distribution Flow Diagram

```
┌────────────────────────────────────┐
│     GENERATION PHASE               │
└────────────────────────────────────┘
        ↓
   Find common items across 
   group members (by name)
        ↓
┌────────────────────────────────────┐
│  Create ItemLink Region            │
│  player = group_id (not 1-4)       │
└────────────────────────────────────┘
        ↓
   For each common item:
   - Create Location(group_id, ...)
   - Create access_rule = state.has(item, group_id)
   - Place original item (item.player = original)
   - Remove from main pool
        ↓
   Create replacement items
   - New items owned by group or individual
   - Added to regular pools
        ↓
┌────────────────────────────────────┐
│    MULTIDATA ASSEMBLY              │
└────────────────────────────────────┘
        ↓
   For each location with item:
   locations[location.player][address] = 
     (item.code, item.player, flags)
                  ↑
         ROUTING DESTINATION!
        ↓
┌────────────────────────────────────┐
│    RUNTIME (Server)                │
└────────────────────────────────────┘
        ↓
   Player checks location
        ↓
   Is player in a group?
   AND all group members collected?
        ↓ YES
   collect_player(team, group_id, is_group=True)
        ↓
   Find all locations where receiving_player in group
   Auto-check all those locations
        ↓
   Extract receiving_player from each item
   Send to that player
```

## Key Code Points Reference

| Concept | File | Lines | What It Does |
|---------|------|-------|-------------|
| **Find Common Items** | BaseClasses.py | 299-327 | `find_common_pool()` - finds items all group members have |
| **Create ItemLink Locations** | BaseClasses.py | 340-360 | Creates locations owned by group_id with original items |
| **Replacement Items** | BaseClasses.py | 362-377 | Creates new items for regular pools |
| **Write Multidata** | Main.py | 283-293 | Stores `(item_code, receiving_player, flags)` |
| **Group Query** | NetUtils.py | 436-442 | `get_for_player(slot)` - finds items routed to slot |
| **Location Extraction** | MultiServer.py | 1089-1120 | Extracts `target_player` from stored items |
| **Auto-Distribution** | MultiServer.py | 1058-1080 | `collect_player()` - triggers group collection |
| **Send to Player** | MultiServer.py | 1082-1087 | `send_items_to()` - delivers to target player |

## LocationStore Structure

```python
# In multidata and server memory:
LocationStore: Dict[int, Dict[int, Tuple[int, int, int]]]
                    ↓        ↓     ↓    ↓       ↓
            location_owner location_id item_id receiving_player flags
```

**Example**:
```python
{
    1: {  # Player 1's locations
        500: (1001, 2, 0),      # Location 500: item 1001, goes to Player 2
        501: (1002, 3, 0),      # Location 501: item 1002, goes to Player 3
    },
    100: {  # Group 100 (ItemLink locations)
        300: (1003, 1, 0),      # ItemLink location 300: item 1003, goes to Player 1
        301: (1004, 2, 0),      # ItemLink location 301: item 1004, goes to Player 2
    }
}
```

When Player 1 or Player 2 collects, group 100 auto-completes → all group locations auto-checked.

## Access Rules

### ItemLink Locations
```python
loc.access_rule = lambda state, item_name=item.name, group_id_=group_id, count_=count: \
    state.has(item_name, group_id_, count_)
```
- Requires GROUP to have the item (shared pool semantics)
- When group gets item (from group members), access rule opens

### Individual Group Locations (Simplified Pattern)
```python
location.access_rule = lambda state: True  # Always accessible
```
- Checked when player joins the group
- Most permissive approach

### No Logic Pattern
```python
# No explicit rule - defaults to True if in group
# Auto-checks when group triggers
```

## Group ID Assignment

```python
new_id = self.players + len(self.groups) + 1
```

**Example for 4 players, 2 groups**:
```
Player IDs: 1, 2, 3, 4
Group 1 ID: 4 + 0 + 1 = 5
Group 2 ID: 4 + 1 + 1 = 6
```

Groups always come AFTER all players.

## When Items Route Correctly vs Wrong

### CORRECT Routing (ItemLink Standard)
```python
item.player = 1             # Original item owner
location.player = group_id  # Located in group region
→ multidata: locations[group_id][addr] = (code, 1, flags)
→ When group collected → item goes to Player 1 ✓
```

### WRONG Routing (Without Setting item.player)
```python
item.player = group_id          # WRONG!
location.player = player_world  # Regular location
→ multidata: locations[player][addr] = (code, group_id, flags)
→ When location checked → item goes to group_id!
→ But group_id has no client, item is lost ✗
```

## Multiworld.groups Structure

```python
multiworld.groups = {
    100: Group(
        name="ItemLink: Shared Weapons",
        game="My Game",
        world=<WorldInstance>,
        players={1, 3, 4},
        item_pool={"Sword", "Shield"},
        replacement_items={1: "Filler", 3: "Filler", 4: "Filler"},
        local_items=set(),
        non_local_items=set(),
        link_replacement=False,
    )
}
```

## Server-Side Group Collection Logic

```python
# When a player collects:
collect_player(ctx, team, slot, is_group=False):
    # 1. Find all locations pointing TO this player
    all_locations = ctx.locations.get_for_player(slot)
    
    # 2. Register and route those items
    for source_player, location_ids in all_locations.items():
        register_location_checks(ctx, team, source_player, location_ids)
    
    # 3. Check if this player is in any groups
    if not is_group:
        for group_id, group_players in ctx.groups.items():
            if slot in group_players:
                # Track that this player collected
                group_collected[group_id].add(slot)
                
                # If ALL group members have collected:
                if set(group_players) == group_collected[group_id]:
                    # Recursively trigger group collection!
                    collect_player(ctx, team, group_id, is_group=True)
```

## The No Logic Pattern (Simplest Implementation)

```python
def auto_distribute_to_players(world, multiworld, items_to_distribute):
    """
    Auto-distribute items without client support.
    
    items_to_distribute = {target_player: item_object, ...}
    """
    # Only 1 player in group = immediate collection
    group_id, group = multiworld.add_group(
        name=f"Distribution Group",
        game=world.game,
        players={world.player}  # ← ONLY THIS PLAYER
    )
    
    # Create region and locations
    region = Region(f"Distribution", group_id, multiworld)
    multiworld.regions.append(region)
    multiworld.regions.add_group(group_id)
    
    # For each item to distribute
    for target, item in items_to_distribute.items():
        loc = Location(group_id, f"Distribute {item.name}", addr, region)
        item.player = target  # ← SET ROUTING!
        loc.place_locked_item(item)
        region.locations.append(loc)
    
    # When player checks ANY location anywhere:
    # 1. Group completes (all 1 members collected)
    # 2. All distribution locations auto-checked
    # 3. Items route to their targets
```

## Debugging Checklist

- [ ] Is `item.player` set to the RECEIVING player?
- [ ] Is `location.player` set to match the planned collector?
- [ ] Are group locations created before multidata dump?
- [ ] Are group members all included in `group["players"]`?
- [ ] Does access rule use correct group_id for `state.has()`?
- [ ] Running `link_items()` in generation pipeline?
- [ ] Is group_id greater than all player IDs?
- [ ] Are location addresses unique?
- [ ] Do replacement items exist for removed items?

