# No Logic Integration Hooks

These hooks allow other worlds to customize how they interact with No Logic. They are optional and only called when No Logic is present in the multiworld.

## Available Hooks

### `nologic_progression_hook(multiworld: MultiWorld)`

**Purpose**: Provide custom progression items for No Logic to use for Progression Items/Shards.

**Return Types** (one of):
- `Item`: A single progression item
- `Tuple[Item, int]`: A single item with a copy count
- `List[Item]`: Multiple progression items
- `List[Tuple[Item, int]]`: Multiple items with copy counts
- `None`: No custom items

**Notes**:
- Copy counts apply in all modes
- No Logic will create copies of your items. Make sure to use counts if submitting multiple of the same item. Can take references of existing items. It will be copied.

**Example**:
```python
def nologic_progression_hook(self, multiworld):
    return [
        Item("Quest Complete", self.player),
        (Item("Level Up", self.player), 5),  # 5 copies
    ]
```

### `nologic_progression_override`

**Purpose**: Skip automatic progression collection and use only items from your hook.

**Type**: Bool (Class)

**Default**: `False`

**Example**:
```python
class MyWorld(World):
    nologic_progression_override = True
    
    def nologic_progression_hook(self, multiworld):
        # Now only these items will be used, not auto-collected ones
        return [Item("My Custom Item", self.player)]
```

### `nologic_exemptions()`

**Purpose**: Specify locations or entrances exempt from logic removal.

**Returns**: `Set[Location | Entrance]`

**Example**:
```python
def nologic_exemptions(self):
    exempt = set()
    for region in self.multiworld.get_regions(self.player):
        if "Tutorial" in region.name:
            exempt.update(region.locations)
    return exempt
```

