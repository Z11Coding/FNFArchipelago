# ItemLink Investigation - Direct Answers to User Questions

## Question 1: ItemLink Distribution Mechanism

### What does link_items() create?

**Answer**: ItemLink creates **THREE new types of elements**:

1. **ItemLink Region** (owned by group_id, not a player)
   ```python
   region = Region(group["world"].origin_region_name, group_id, self, "ItemLink")
   self.regions.append(region)
   ```

2. **ItemLink Locations** (owned by group_id, point TO group completion)
   ```python
   for item in self.itempool:
       if item.name in common_items:
           loc = Location(group_id, f"Item Link: {item.name} -> ...", None, region)
           locations.append(loc)
           loc.place_locked_item(item)  # Place the ORIGINAL item
   ```

3. **Replacement Items** (new items to replace removed ones)
   ```python
   # Original items removed from pool and placed in ItemLink locations
   # New items created and added to regular locations
   new_itempool.append(group["world"].create_item(item_name))
   ```

### What locations does it create and how are items placed?

```
CREATED LOCATIONS:
- Location player = group_id (e.g., 5 for first group)
- Location address = None → gets replaced with unique IDs
- Location name = "Item Link: Sword -> Player 1 (1)" typical format
- Location region = ItemLink region (player=group_id)

ITEM PLACEMENT:
- Original item (e.g., Sword with item.player=1) is placed in location
- Location is LOCKED - item cannot be moved by filler
- When location is "checked", the item is delivered to item.player

EXAMPLE:
Player 1 has: Sword (3x), Shield (2x)
Player 2 has: Sword (2x), Shield (3x)
ItemLink: {Sword, Shield}

CREATE:
- Location 1: Sword (player=1), player=group_id → receives player=1
- Location 2: Sword (player=1), player=group_id → receives player=1
- Location 3: Shield (player=2), player=group_id → receives player=2
- Location 4: Shield (player=2), player=group_id → receives player=2
```

### What access_rules do these locations have?

**Answer**: Access rules CHECK IF THE GROUP HAS THE ITEM

```python
loc.access_rule = lambda state, item_name = item.name, group_id_ = group_id, count_ = count: \
    state.has(item_name, group_id_, count_)
```

**Behavior**:
- `state.has(item_name, group_id, count)` - checks if group has `count` of `item_name`
- When Player 1 collects a Sword → Group gains a Sword
- When Group has 2 Swords → Both ItemLink Sword locations become accessible
- Access rule = GROUP'S CURRENT INVENTORY, not individual players

### How does the server detect when to auto-check these locations?

**Answer**: Server tracks when ALL group members have collected

```python
# In collect_player() function:
if not is_group:
    for group, group_players in ctx.groups.items():
        if slot in group_players:  # Is this player in a group?
            group_collected_players = ctx.group_collected.setdefault(group, set())
            group_collected_players.add(slot)  # Track collection
            if set(group_players) == group_collected_players:  # All members collected?
                collect_player(ctx, team, group, True)  # TRIGGER!
```

**Trigger sequence**:
1. Player 1 checks location → `collect_player(team, 1, False)`
2. Player 2 checks location → `collect_player(team, 2, False)`
3. Player 3 checks location → `collect_player(team, 3, False)`
4. On 3rd collection: `group_collected_players == {1, 2, 3} == group["players"]` → TRUE
5. Automatically calls: `collect_player(team, group_id, is_group=True)`

---

## Question 2: Server-Side Item Distribution

### How does collect_player() work?

**Answer**: It has TWO phases based on `is_group` flag

**Phase 1: Individual Player Collection** (`is_group=False`)
```python
def collect_player(ctx, team, slot, is_group=False):
    # Find all locations that ROUTE TO this slot
    all_locations = ctx.locations.get_for_player(slot)
    
    # Auto-check those locations
    for source_player, location_ids in all_locations.items():
        register_location_checks(ctx, team, source_player, location_ids)
```

- Called when a player checks a location
- Finds ALL locations pointing TO that player
- Immediately checks them all (1:1 routing)

**Phase 2: Group Collection** (`is_group=True`)
```python
def collect_player(ctx, team, slot, is_group=False):
    # (same code, but now slot is group_id)
    all_locations = ctx.locations.get_for_player(slot)  # slot = group_id!
    
    for source_player, location_ids in all_locations.items():
        # ALL ItemLink locations for this group
        register_location_checks(ctx, team, source_player, location_ids)
```

- Called when all group members have collected
- Finds ALL locations pointing TO that group (not individual members)
- Checks them all at once

### When a group member collects something, what happens?

**Answer**: The server checks if group is now complete

```
Timeline:
- Player 1 checks location → send to Player 2
- Server: collect_player(team, 1)
  ├─ Find locations where receiving_player==1
  ├─ Register those checks (items route appropriately)
  ├─ Check: is Player 1 in a group? YES
  ├─ Add Player 1 to group_collected[group_id]
  ├─ Is set(group["players"]) == group_collected[group_id]? NO (P2, P3 haven't collected)
  └─ Return

- Later: Player 2 checks location
- Server: collect_player(team, 2)
  └─ (same process, still not complete)

- Finally: Player 3 checks location
- Server: collect_player(team, 3)
  ├─ Add Player 3 to group_collected[group_id]
  ├─ Is set(group["players"]) == group_collected[group_id]? YES!
  ├─ CALL: collect_player(team, group_id, is_group=True)
  │  ├─ Find all locations where receiving_player==group_id
  │  ├─ Auto-check location 1: Sword → Player 1
  │  ├─ Auto-check location 2: Sword → Player 1
  │  ├─ Auto-check location 3: Shield → Player 2
  │  ├─ Auto-check location 4: Shield → Player 2
  │  └─ All items route to their destinations!
  └─ Return
```

### What triggers auto-checking of all locations tied to a group?

**Answer**: When `set(group["players"]) == group_collected`

**Exact code**:
```python
if set(group_players) == group_collected_players:
    collect_player(ctx, team, group, True)  # THIS LINE
```

This single line triggers the cascade:
1. Find all locations with `receiving_player==group_id`
2. Auto-check ALL of them
3. Route each item to its `receiving_player`

### Does the server check if ALL group members collected, or each separately?

**Answer**: Checks if ALL group members collected, then triggers ONCE

```python
# NOT one check per member - one check when ALL have collected
if set(group_players) == group_collected_players:  # Compound check
    collect_player(ctx, team, group, True)  # Single call
```

**Result**: All ItemLink locations are checked in ONE recursive call.

---

## Question 3: Group Mechanics

### What is the difference between a group and a player?

**Answer**: Groups are pseudo-players with shared collection semantics

| Property | Player | Group |
|----------|--------|-------|
| ID Range | 1-4 (example) | 5+ |
| Type | `SlotType.player` | `SlotType.group` |
| Members | 1 | Multiple |
| Has World | Yes | Yes (shared instance) |
| Collection | Immediate | Waits for all members |
| Locations | Regular | ItemLink |
| Items Owned | Individual | Shared pool |

### Can a group have locations assigned to it where location.player==group_id?

**Answer**: YES, explicitly! This is the PRIMARY mechanism.

```python
Location(group_id, "ItemLink: Sword", 5001, region)  # location.player = group_id
```

These are the **ItemLink locations**. When group collects, these auto-check.

### When items in those locations have item.player=some_world, what happens?

**Answer**: Items are routed to `item.player` when the location is checked

**Rule**: 
```
Multidata stores: locations[location.player][address] = (item_id, item.player, flags)
                                                                  ↑
                                                        ROUTING TARGET!
```

**Example**:
```python
locations[group_5][5001] = (sword_item_id, 1, 0)  # When group collects, go to Player 1
locations[group_5][5002] = (shield_item_id, 2, 0) # When group collects, go to Player 2
```

### How does NetworkSlot and SlotType.group work?

**Answer**: SlotType.group is metadata; NetworkSlot stores group membership

**In multidata**:
```python
slot_info[group_id] = NetworkSlot(
    name="ItemLink: Weapons",
    game="My Game",
    type=SlotType.group,
    group_members=sorted([1, 2, 3])  # The member players
)
```

**Server usage**:
```python
ctx.slot_info[group_id].type == SlotType.group  # Check if group
ctx.slot_info[group_id].group_members  # Get member players
```

**Clients**: Group slots don't have clients (no one connecting as group).

---

## Question 4: Alternative Mechanisms

### Are there "World Groups" in the World class itself?

**Answer**: No, groups are only in MultiWorld. Worlds don't know about groups.

World sees:
- `multiworld.groups: Dict[int, Group]` - read-only during generation
- `multiworld.player_types[id] == SlotType.group` - identify groups
- `multiworld.worlds[group_id]` - access group's world instance

### Can you find any alternative distribution mechanisms used by other worlds?

**Answer**: YES - Found 3 mechanisms:

1. **ItemLink** (framework feature)
   - Used by: many worlds with shared pools
   - Mechanism: Group + location routing
   - Auto-send: Yes, via group collection

2. **Precollected Items** (startup inventory)
   - File: MultiServer.py lines 498-499
   - Mechanism: Items in `multidata["precollected_items"]`
   - Storage: NetworkItem with location_id=-2
   - Use case: Starting items
   - Auto-send: Yes, at connection time

3. **No Logic Pattern** (world-specific)
   - File: worlds/noLogic/__init__.py
   - Mechanism: Single-player group → auto-completes instantly
   - Auto-send: Yes, progression items distribute on first location check
   - Simpler than ItemLink for one-time distribution

### Is there a way to mark items as "auto-send" or "auto-collect"?

**Answer**: No explicit "auto" flag, but there are implicit mechanisms:

1. **Set item.player**: Item automatically routes when location is checked
   ```python
   item.player = target_player  # This is the routing destination
   ```

2. **Put in group region**: Location auto-checks when group collects
   ```python
   location.player = group_id  # Auto-checked when group completes
   ```

3. **Use precollected**: Item sends at connection
   ```python
   multiworld.precollected_items[player].append(item)
   ```

These aren't "flags" but mechanisms that trigger auto-send.

---

## Question 5: The Key Pattern

### Find where the server writes to multidata for items in locations

**Answer**: Main.py lines 292-293

```python
locations_data[location.player][location.address] = \
    location.item.code, location.item.player, location.item.flags
```

This single assignment creates the entire routing infrastructure!

### What determines if an item goes to the wrong player initially?

**Answer**: NOT setting `item.player` correctly

**WRONG**:
```python
item = create_item("Sword")  # item.player defaults to world player
location = Location(1, "Get Sword", 100, region)
location.place_locked_item(item)
# Result: locations[1][100] = (code, 1, flags) → goes to Player 1 ✓
```

**WRONG with ItemLink**:
```python
item = create_item("Sword")  # item.player = 1
location = Location(group_5, "ItemLink Sword", 5001, region)
location.place_locked_item(item)
# Result: locations[5][5001] = (code, 1, flags) → goes to Player 1 ✓
# THIS IS CORRECT!
```

**WRONG - Item to group**:
```python
item = create_item("Sword")
item.player = group_5  # Set to group! ✗
location = Location(1, "Get Sword", 100, region)
location.place_locked_item(item)
# Result: locations[1][100] = (code, 5, flags)
# But group 5 has no client! Item disappears ✗
```

### How does multidata routing work when location_owner != item_destination?

**Answer**: LocationStore separates them

```
MULTIDATA:
locations[location_owner][location_id] = (item_code, receiving_player, flags)
         ↑                                               ↑
    WHO CHECKS IT                              WHO GETS THE ITEM
```

**Example**:
```python
locations[1][100] = (sword_code, 2, 0)
```
- Location 100 is in Player 1's world
- Player 1 checks it
- Server extracts: receiving_player = 2
- Item goes to Player 2!

**With groups**:
```python
locations[5][5001] = (sword_code, 1, 0)
```
- Location 5001 in Group 5 (ItemLink region)
- When group collects
- Server finds all locations[5][*]
- For each, extracts receiving_player
- Items route accordingly!

---

## Summary: How to Auto-Distribute Without Client

### The Simplest Method (No Logic Pattern)

```python
def create_auto_distribution(world, multiworld, items_dict):
    """
    items_dict = {target_player: item_object}
    
    One location check → all items distributed automatically
    """
    # 1. Create group with ONLY the distributor player
    group_id, _ = multiworld.add_group(
        name=f"Auto Distribution",
        game=world.game,
        players={world.player}  # ← SINGLE PLAYER
    )
    
    # 2. Create ItemLink region
    region = Region("Distribution", group_id, multiworld)
    multiworld.regions.append(region)
    multiworld.regions.add_group(group_id)
    
    # 3. For each item to distribute
    for target_player, item in items_dict.items():
        loc = Location(group_id, f"Distribute {item.name}", get_id(), region)
        item.player = target_player  # ← KEY: Set routing destination
        loc.place_locked_item(item)
        region.locations.append(loc)
    
    # RESULT:
    # When distributor checks ANY location:
    # → Group size 1, all members collected
    # → collect_player(team, group_id, is_group=True) triggers
    # → All distribution locations auto-checked
    # → Items route to targets!
```

**Why it works**:
- Group has 1 player = immediate completion
- Recursive `collect_player()` with `is_group=True`
- Auto-checks all locations with `location.player = group_id`
- Items route via `item.player` field

**Result**: No client needed, no checks needed per item, pure server-side logic!

