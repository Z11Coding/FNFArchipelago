# ItemLink Distribution Mechanism - Complete Analysis

## 1. ItemLink Distribution Mechanism

### 1.1 link_items() in BaseClasses.py (lines 295-377)

#### Location Creation
```python
region = Region(group["world"].origin_region_name, group_id, self, "ItemLink")
self.regions.append(region)
locations = region.locations

# For each item that appears in multiple group members:
for item in self.itempool:
    count = common_item_count.get(item.player, {}).get(item.name, 0)
    if count:
        loc = Location(group_id, f"Item Link: {item.name} -> {self.player_name[item.player]} {count}",
            None, region)
        loc.access_rule = lambda state, item_name = item.name, group_id_ = group_id, count_ = count: \
            state.has(item_name, group_id_, count_)

        locations.append(loc)
        loc.place_locked_item(item)
        common_item_count[item.player][item.name] -= 1
```

**Key properties**:
- `location.player = group_id` (NOT a regular player number)
- `location.item = original item` (preserved from item pool)
- `location.item.player = original player` (NOT changed by link_items)
- `access_rule = state.has(item_name, group_id, count)` - requires GROUP to have item

#### Replacement Items
```python
# Create new items to fill the gap left by removed items
new_itempool: List[Item] = []
for item_name, item_count in next(iter(common_item_count.values())).items():
    for _ in range(item_count):
        new_item = group["world"].create_item(item_name)
        new_item.classification |= classifications[item_name]
        new_itempool.append(new_item)

# Later: Add filler for remaining gaps
while itemcount > len(self.itempool):
    items_to_add = []
    for player in group["players"]:
        if group["link_replacement"]:
            item_player = group_id  # Items go to group
        else:
            item_player = player   # Items go to each player
        if group["replacement_items"][player]:
            items_to_add.append(AutoWorld.call_single(self, "create_item", item_player,
                group["replacement_items"][player]))
        else:
            items_to_add.append(AutoWorld.call_single(self, "create_filler", item_player))
    self.itempool.extend(items_to_add[:itemcount - len(self.itempool)])
```

**Result**:
- Original items (with original players) in ItemLink locations
- New items (owned by group or individual players) in regular item pools

---

## 2. Server-Side Item Distribution

### 2.1 collect_player() in MultiServer.py (lines 1058-1080)

```python
def collect_player(ctx: Context, team: int, slot: int, is_group: bool = False):
    """register any locations that are in the multidata, pointing towards this player"""
    all_locations = ctx.locations.get_for_player(slot)

    ctx.broadcast_text_all("%s (Team #%d) has collected their items from other worlds."
                           % (ctx.player_names[(team, slot)], team + 1),
                           {"type": "Collect", "team": team, "slot": slot})
    for source_player, location_ids in all_locations.items():
        register_location_checks(ctx, team, source_player, location_ids, count_activity=False)
        update_checked_locations(ctx, team, source_player)

    # KEY: Group auto-completion logic
    if not is_group:
        for group, group_players in ctx.groups.items():
            if slot in group_players:
                group_collected_players = ctx.group_collected.setdefault(group, set())
                group_collected_players.add(slot)
                if set(group_players) == group_collected_players:
                    collect_player(ctx, team, group, True)  # RECURSIVE CALL with is_group=True!
```

**Behavior**:
1. When player completes, finds all locations pointing TO them
2. Auto-checks those locations
3. Checks if player is in any groups
4. When ALL group members have collected, recursively calls collect_player for the GROUP
5. When group is collected, auto-checks all locations owned by group

### 2.2 register_location_checks() in MultiServer.py (lines 1089-1120)

```python
def register_location_checks(ctx: Context, team: int, slot: int, locations: typing.Iterable[int],
                             count_activity: bool = True):
    slot_locations = ctx.locations[slot]
    new_locations = set(locations) - ctx.location_checks[team, slot]
    
    if new_locations:
        sortable: list[tuple[int, int, int, int]] = []
        for location in new_locations:
            # Extract all fields to avoid runtime overhead in LocationStore
            item_id, target_player, flags = slot_locations[location]  # ROUTING EXTRACTION!
            sortable.append((target_player, item_id, location, flags))

        for target_player, item_id, location, flags in sorted(sortable):
            new_item = NetworkItem(item_id, location, slot, flags)
            send_items_to(ctx, team, target_player, new_item)  # SEND TO TARGET!

            ctx.logger.info('(Team #%d) %s sent %s to %s (%s)' % (
                team + 1, ctx.player_names[(team, slot)], 
                ctx.item_names[ctx.slot_info[target_player].game][item_id],
                ctx.player_names[(team, target_player)], 
                ctx.location_names[ctx.slot_info[slot].game][location]))
```

**Critical step**: 
- Extracts `target_player` from `slot_locations[location]` 
- This is the **ROUTING DESTINATION** set during generation!
- Sends item to `target_player`, not to location owner

---

## 3. Group Mechanics in BaseClasses.py

### 3.1 Group vs Player (lines 27-39)

```python
class Group(TypedDict):
    name: str
    game: str
    world: "AutoWorld.World"
    players: AbstractSet[int]
    item_pool: NotRequired[Set[str]]
    replacement_items: NotRequired[Dict[int, Optional[str]]]
    local_items: NotRequired[Set[str]]
    non_local_items: NotRequired[Set[str]]
    link_replacement: NotRequired[bool]
```

**Differences**:
- Groups have `player_types[group_id] = SlotType.group`
- Groups have `game[group_id] = game`
- Groups have `worlds[group_id] = group["world"]` (world instance)
- Groups have `player_name[group_id] = group_name`
- Groups are tracked in `multiworld.groups: Dict[int, Group]`

### 3.2 add_group() in BaseClasses.py (lines 186-210)

```python
def add_group(self, name: str, game: str, players: AbstractSet[int] = frozenset()) -> Tuple[int, Group]:
    """Create a group with name and return the assigned player ID and group.
    If a group of this name already exists, the set of players is extended instead of creating a new one."""
    from worlds import AutoWorld

    for group_id, group in self.groups.items():
        if group["name"] == name:
            group["players"] |= players
            return group_id, group
    
    new_id: int = self.players + len(self.groups) + 1  # ID after all regular players

    self.regions.add_group(new_id)
    self.game[new_id] = game
    self.player_types[new_id] = NetUtils.SlotType.group
    world_type = AutoWorld.AutoWorldRegister.world_types[game]
    self.worlds[new_id] = world_type.create_group(self, new_id, players)
    self.worlds[new_id].collect_item = AutoWorld.World.collect_item.__get__(self.worlds[new_id])
    self.worlds[new_id].collect = AutoWorld.World.collect.__get__(self.worlds[new_id])
    self.worlds[new_id].remove = AutoWorld.World.remove.__get__(self.worlds[new_id])
    self.player_name[new_id] = name

    new_group = self.groups[new_id] = Group(name=name, game=game, players=players,
                                            world=self.worlds[new_id])

    return new_id, new_group
```

**Key points**:
- Group ID = `players + len(groups) + 1` (comes AFTER all regular players)
- Groups get their own World instance
- Groups are marked as `SlotType.group`
- Groups can have items and locations assigned to them (using group_id as player)

### 3.3 Can Groups Have Locations with receiving_player==group_id?

**YES!** This is exactly what ItemLink does:
- Creates regions with `region.player = group_id`
- Creates locations with `location.player = group_id`
- Places items with `item.player = original_player` (routing destination)

Result in multidata: `locations[group_id][location_id] = (item_id, original_player, flags)`

When group is collected, all these locations are auto-checked, and items route to `original_player`.

---

## 4. How Multidata Is Created and Routed

### 4.1 Multidata Structure in Main.py (lines 283-293)

```python
locations_data: dict[int, dict[int, tuple[int, int, int]]] = {player: {} for player in multiworld.player_ids}

for location in multiworld.get_filled_locations():
    if type(location.address) == int:
        assert location.item.code is not None
        assert location.address not in locations_data[location.player]
        
        # THE CRITICAL LINE:
        locations_data[location.player][location.address] = \
            location.item.code, location.item.player, location.item.flags
```

**Structure**: 
```
locations_data[location_owner][location_id] = (item_code, receiving_player, flags)
                ^                ^                          ^
                |                |                    WHO GETS THE ITEM!
                |           The location address/ID
            Which player's realm the location is in
```

**Example with ItemLink**:
- `location.player = group_id` (ItemLink region player)
- `location.item.player = player_1` (routing destination)
- Result: `locations[group_id][location_id] = (item_code, player_1, flags)`

When group_id is collected, the item automatically goes to player_1.

### 4.2 LocationStore Query in NetUtils.py (lines 436-442)

```python
def get_for_player(self, slot: int) -> typing.Dict[int, typing.Set[int]]:
    """Find all locations where receiving_player == slot"""
    import collections
    all_locations: typing.Dict[int, typing.Set[int]] = collections.defaultdict(set)
    for source_slot, location_data in self.items():
        for location_id, values in location_data.items():
            if values[1] == slot:  # values[1] is receiving_player!
                all_locations[source_slot].add(location_id)
    return all_locations
```

**Translation**:
- Looks at all locations
- If `values[1] == slot`, the item is destined for this slot
- Returns dict of `{source_player: {location_ids_that_point_to_slot}}`

### 4.3 LocationStore Data Layout (NetUtils.py, line 415)

```python
class _LocationStore(dict, typing.MutableMapping[int, typing.Dict[int, typing.Tuple[int, int, int]]]):
    def __init__(self, values: typing.MutableMapping[int, typing.Dict[int, typing.Tuple[int, int, int]]]):
```

**Formula**:
```
LocationStore: Dict[int, Dict[int, Tuple[int, int, int]]]
                source_player  location_id  item_id, receiving_player, flags
```

So when stored in multidata as `locations_data`, it becomes:
```
multidata["locations"][location_owner][location_id] = (item_id, item_recipient, flags)
```

---

## 5. Alternative Distribution Mechanisms

### 5.1 The No Logic Pattern (Simplest Server-Side Auto-Distribution)

**File**: [worlds/noLogic/__init__.py](worlds/noLogic/__init__.py#L320-L387)

```python
def distribute_items(self):
    """Create a group that auto-distributes progression items when checked"""
    if not hasattr(self, 'progression_item_objects'):
        return
    
    # Step 1: Create a group containing only this player
    group_id, group = self.multiworld.add_group(
        name=f"No Logic Distribution ({self.player_name})",
        game=self.game,
        players={self.player}  # ONLY ONE PLAYER!
    )
    
    # Step 2: Create a region for the group
    group_region = Region(f"No Logic Distribution Region", group_id, self.multiworld)
    self.multiworld.regions.append(group_region)
    self.multiworld.regions.add_group(group_id)
    
    # Step 3 & 4: Create locations for each item
    for target_player, item in self.progression_item_objects.items():
        # Create a location owned by the group
        location_name = f"Distribute {item.name} to {self.multiworld.player_name[target_player]}"
        location = Location(group_id, location_name, get_unused_location_id(), group_region)
        group_region.locations.append(location)
        
        # SET THE ROUTING DESTINATION!
        item.player = target_player
        
        # Place the item (locked)
        location.place_locked_item(item)
```

**Why this works**:
1. Group contains only 1 player (the distributor)
2. When that player collects ANY item, the group is immediately complete
3. Server calls `collect_player(team, group_id, is_group=True)`
4. All locations with `location.player=group_id` are auto-checked
5. Each item routes to its `item.player` destination

**Result**: Single location check → All progression items distribute automatically!

### 5.2 Precollected Items (Alternative: Startup Inventory)

**File**: Main.py lines 263-265

```python
precollected_items = {player: [item.code for item in world_precollected if type(item.code) == int]
                      for player, world_precollected in multiworld.precollected_items.items()}
```

**How it works**:
- Items in `multiworld.precollected_items[player]` are included in multidata
- Server converts them to NetworkItem with `location_id = -2` (special marker)
- Sent immediately at connection time, not checked via protocol
- Non-routable - go directly to their `item.player` owner

**Limitation**: Only for startup items, not for discovered items.

### 5.3 Adventure World's AutoCollect (Client-Specific)

**File**: worlds/adventure/__init__.py, AdventureAutoCollectLocation

- ROM-based solution, not framework-level
- Client-side only mechanism
- Not applicable to server-only distribution

---

## 6. The Key Pattern: How Item Routing Works

### How ItemLink Items Automatically Go to the Right Player

```
GENERATION PHASE:
├─ Player 1 has: Sword (3x), Shield (2x)
├─ Player 2 has: Sword (2x), Shield (3x)
├─ ItemLink group created with {Player 1, Player 2}
│
├─ Common items found: Sword (min=2), Shield (min=2)
│
├─ Original items removed from pool:
│  ├─ Sword #1 (player=1) → ItemLink location, kept in location.item
│  ├─ Sword #2 (player=1) → ItemLink location, kept in location.item
│  ├─ Shield #1 (player=2) → ItemLink location, kept in location.item
│  └─ Shield #2 (player=2) → ItemLink location, kept in location.item
│
├─ Replacement items created and added to regular pools:
│  ├─ "Random Sword" (player=group_id or player=1)
│  ├─ "Random Sword" (player=group_id or player=1)
│  ├─ "Random Shield" (player=group_id or player=2)
│  └─ "Random Shield" (player=group_id or player=2)

MULTIDATA CREATION:
├─ locations[group_id][location_1] = (sword_item_code, 1, flags)  ← Routes to Player 1!
├─ locations[group_id][location_2] = (sword_item_code, 1, flags)  ← Routes to Player 1!
├─ locations[group_id][location_3] = (shield_item_code, 2, flags) ← Routes to Player 2!
└─ locations[group_id][location_4] = (shield_item_code, 2, flags) ← Routes to Player 2!

RUNTIME (when group collects):
├─ Server calls collect_player(team, group_id, is_group=True)
├─ Server finds all locations with receiving_player==(group_id or player_in_group)
├─ Auto-checks all ItemLink locations
├─ register_location_checks extracts: (sword_code, 1, flags)
├─ Calls send_items_to(team, 1, sword_item)
└─ sword_item goes to Player 1! ✓
```

---

## 7. Complete Flow Summary

```
1. OPTIONS RESOLVE (BaseClasses.multiworld_post_init)
   └─ For each ItemLinks option entry:
      ├─ Collect players and item pools
      └─ Create group via add_group()

2. LINK_ITEMS() CALLED (Main.py line 177)
   └─ For each group:
      ├─ Find common items across group members
      ├─ Create ItemLink region with player=group_id
      ├─ Create ItemLink locations with player=group_id
      ├─ Place original items (keeping item.player = original)
      └─ Create replacement items for regular items

3. FILL LOGIC
   └─ Fill locations (including ItemLink locations with their items)

4. MULTIDATA ASSEMBLY (Main.py lines 283-293)
   └─ For each filled location:
      └─ Store (item.code, item.player, item.flags)
         └─ item.player is the ROUTING DESTINATION!

5. CLIENT CONNECTION
   └─ Client connects
   └─ Server sends multidata with locations

6. PLAYER COMPLETES LOCATION
   └─ Client sends location check
   └─ Server registers check
   └─ Server calls collect_player(team, player)
      ├─ If player in group AND all group members collected:
      │  └─ Call collect_player(team, group_id, is_group=True)
      │     ├─ Find all locations with owner=group_id
      │     ├─ Extract receiving_player from each
      │     └─ Send items to their receiving_player
      └─ Update item indices and broadcast
```

---

## 8. When to Use What

### Use ItemLink When:
- Multiple players share an item pool for specific items
- You want balanced distribution of shared items
- Each group member has access to shared items through the group
- You need the group completion trigger for other effects

### Use No Logic Pattern When:
- You need ONE-TIME auto-distribution without client support
- Creating a progression item bridge between worlds
- You want simplicity: one location check = all items distributed
- No complex group semantics needed

### Use Precollected When:
- Items should start with player at game start
- No checks needed (free items)
- Very common for start inventory

### Use Custom Group When:
- You need finer control over location ownership
- Complex distribution logic needed
- Multiple groups in one world
- Player-specific items that shouldn't route through checks

