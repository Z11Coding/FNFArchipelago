# Spoiler Dict System

A system for automatically hiding sensitive slot data keys behind spoiler-free labels, while maintaining full compatibility with dict operations.

## Features

- **Transparent Dict Subclass**: `SpoilerDict` extends `dict`, so it works with any code expecting a dict
- **Spoiler-Free Key Labels**: When iterating or displaying, keys show spoiler-free labels like "Area 1", "Treasure", etc.
- **Normal Access Preserved**: Direct access via `[]` and `.get()` works with real keys
- **Automatic Patching**: World `fill_slot_data` calls are automatically patched to add spoiler data
- **Client Support**: CommonClient can access revealed keys via `ctx.special_spoiler_data`
- **JSON Compatible**: Works with serialization/deserialization without data loss
- **Dict Equality**: Underlying data comparisons work correctly for datapackage checks

## Quick Start

### In Your World

```python
from worlds import World
from worlds.spoiler import apply_spoiler_protection_to_world

class MyWorld(World):
    def fill_slot_data(self) -> dict:
        slot_data = {
            "secret_location_1": "magic_sword",
            "secret_location_2": "healing_potion",
            "version": 1  # Not sensitive
        }
        
        # Protect the slot data
        return apply_spoiler_protection_to_world(
            slot_data,
            self,
            key_labels={
                "secret_location_1": "??",
                "secret_location_2": "??",
            }
        )
```

### In Your Client

```python
from CommonClient import CommonContext

class MyContext(CommonContext):
    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            # It's automatic! The system automatically extracts special_spoiler_data
            
            # You can now use helper methods to access real keys
            real_key = self.get_revealed_key("??")  # Returns "secret_location_1"
            real_value = self.get_revealed_value("secret_location_1")  # Returns "magic_sword"
```

## API Reference

### SpoilerDict

A dict subclass that shows spoiler-free labels for keys when iterating or displaying.

#### Methods

- `revealed_keys()` - Get the actual keys (before spoiler translation)
- `revealed_items()` - Get actual (real_key, value) pairs
- `revealed_values()` - Get values (same as regular values)
- `set_label(real_key, label)` - Set a custom spoiler-free label for a key
- `get_label(real_key)` - Get the spoiler-free label for a key
- `get_revealed_key_for_label(label)` - Get the real key for a spoiler-free label
- `copy()` - Create a shallow copy preserving labels
- `to_dict()` - Convert to regular dict with spoiler-free labels as keys
- `from_dict(dict, key_labels)` - Create SpoilerDict from regular dict

#### Example

```python
sd = SpoilerDict(
    real_data={"secret_location": "cool_item", "another_secret": "gem"},
    key_labels={"secret_location": "Location A", "another_secret": "Location B"}
)

# Access works with real keys
sd["secret_location"]  # Returns "cool_item"

# Iteration shows spoiler-free labels
for key in sd:  # key is "Location A" or "Location B"
    print(key, sd[key])  # But need real key for access!

# Get actual keys
sd.revealed_keys()  # Returns {"secret_location", "another_secret"}
```

### World Patching Functions

#### `apply_spoiler_protection_to_world(slot_data, world, key_labels=None, protected_keys=None)`

Apply spoiler protection to a world's slot data.

**Args:**
- `slot_data`: Dict with data to protect
- `world`: World instance (for context/logging)
- `key_labels`: Mapping of real_key -> spoiler_free_label (optional)
- `protected_keys`: List of keys to specifically mark as needing protection (optional)

**Returns:** `SpoilerDict` instance with special_spoiler_data metadata

#### `patch_slotdata_with_spoiler_data(slot_data)`

Patch existing slot_data containing SpoilerDict instances.

Extracts metadata from SpoilerDicts and adds it as "special_spoiler_data" for transmission.

**Args:** `slot_data` - Dict that may contain SpoilerDict instances

**Returns:** Modified dict with special_spoiler_data added

### CommonClient Support (Automatic!)

Once the spoiler system is imported, CommonContext instances automatically have:

- `get_revealed_key(spoiler_free_label, data_key=None)` - Get real key for a label
- `get_revealed_value(real_key, data_key=None)` - Get value for a real key
- `get_all_revealed_keys(data_key=None)` - Get all label -> key mappings
- `get_all_revealed_items(data_key=None)` - Get all key -> value mappings
- `special_spoiler_data` - Dict attribute containing the raw spoiler data (auto-populated on Connected)

**No manual extraction needed** - the system automatically extracts `special_spoiler_data` when the Connected packet is received.

**Example:**
```python
# In your on_package handler
def on_package(self, cmd: str, args: dict):
    if cmd == "Connected":
        # It just works! special_spoiler_data is already populated
        real_key = self.get_revealed_key("??")
        real_value = self.get_revealed_value(real_key)
```

## How It Works

### Server Side (Generation)

1. World's `fill_slot_data()` is called
2. World returns `SpoilerDict` with spoiler-free labels
3. World patcher intercepts and adds `special_spoiler_data` to the dict
4. When serialized to JSON, dict keys become the spoiler-free labels
5. `special_spoiler_data` field is included with real key/value mappings

### Network Transmission

The slot_data is serialized to JSON:
```json
{
  "??": "cool_item",        // spoiler-free label as key
  "???_1": "gem",          // spoiler-free label as key
  "game_version": 1,
  "special_spoiler_data": {
    "real_keys": {
      "??": "secret_location",
      "???_1": "another_secret"
    },
    "real_items": {
      "secret_location": "cool_item",
      "another_secret": "gem"
    }
  }
}
```

### Client Side (Reception)

1. Client receives JSON with spoiler-free labels
2. Client calls `process_slot_data_with_spoiler_info()`
3. `special_spoiler_data` is extracted and stored in `ctx.special_spoiler_data`
4. Client can use helper methods to map back to real keys/values

## Data Integrity

- **Equality Checks**: `SpoilerDict.__eq__` compares only underlying data, not labels
  - Ensures datapackage validation passes
  - Two SpoilerDicts with different labels are equal if data is identical
  
- **Hashing**: Based on actual data (if needed)

- **Serialization**: Dict keys automatically use spoiler-free labels in JSON

## Thread Safety

SpoilerDict is as thread-safe as regular dict. No additional synchronization is provided.

## Limitations

1. **Network Transport**: Labels must be serializable to JSON (strings only)
2. **Performance**: Slight overhead from key label lookups during iteration
3. **Modified Dicts**: After modification, new keys get auto-generated labels (???, ???_1, etc)
4. **Not Hashable**: Dicts can't be dict keys; use regular dict for that

## Examples

### Example 1: Simple Item Hide

```python
def fill_slot_data(self):
    from worlds.spoiler import apply_spoiler_protection_to_world
    
    return apply_spoiler_protection_to_world(
        {
            "item_location_1": "sword",
            "item_location_2": "shield",
        },
        self,
        key_labels={
            "item_location_1": "???",
            "item_location_2": "???_1",
        }
    )
```

### Example 2: Partial Protection

```python
def fill_slot_data(self):
    from worlds.spoiler import apply_spoiler_protection_to_world
    
    slot_data = {
        "secret_1": "item_a",
        "secret_2": "item_b", 
        "game_version": 1,  # Not sensitive
        "difficulty": "hard",  # Not sensitive
    }
    
    # Only protect sensitive keys
    key_labels = {
        "secret_1": "First Secret",
        "secret_2": "Second Secret",
    }
    
    return apply_spoiler_protection_to_world(slot_data, self, key_labels=key_labels)
```

### Example 3: Client Access

```python
class MyContext(CommonContext):
    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            from worlds.spoiler import process_slot_data_with_spoiler_info
            process_slot_data_with_spoiler_info(self, args.get("slot_data", {}))
            
            # Now access revealed keys
            print(self.get_all_revealed_keys())
            
            # Map specific labels
            for label, real_key in self.get_all_revealed_keys().items():
                value = self.get_revealed_value(real_key)
                print(f"{label} ({real_key}) = {value}")
```

## Troubleshooting

### Client can't find special_spoiler_data

Make sure to call `process_slot_data_with_spoiler_info()` in your client's `on_package()` method when receiving Connected.

### SpoilerDict comparison fails

Check that you're comparing the underlying data. The `__eq__` method compares dict contents only, not labels.

### Keys appear wrong in JSON

Keys in the JSON will be spoiler-free labels. Use `special_spoiler_data` to map back to real keys.

## Distribution

This system is designed to be distributed separately from individual worlds. Worlds that use it will work with or without spoiler protection enabled (graceful degradation).
