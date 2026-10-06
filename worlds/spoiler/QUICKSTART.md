# Spoiler Dict System - Quick Start Guide

## What Is This?

The Spoiler Dict system hides sensitive slot data keys behind spoiler-free labels. A player sees `??` as a key name instead of `secret_location_1`, but clients can use `special_spoiler_data` to map back to real keys if needed.

## Setup

The spoiler system is in `/worlds/spoiler/` and is automatically initialized on import.

```python
from worlds.spoiler import apply_spoiler_protection_to_world
```

## For World Developers

### Protect Your Slot Data

In your world's `fill_slot_data()` method:

```python
from worlds.spoiler import apply_spoiler_protection_to_world

class MyWorld(World):
    def fill_slot_data(self) -> dict:
        slot_data = {
            "dungeon_1_boss": "key_1",
            "dungeon_2_boss": "key_2", 
            "version": 1  # Not sensitive
        }
        
        return apply_spoiler_protection_to_world(
            slot_data,
            self,
            key_labels={
                "dungeon_1_boss": "???",
                "dungeon_2_boss": "???_1",
            }
        )
```

That's it! The framework handles the rest automatically.

### Key Points

- `apply_spoiler_protection_to_world()` takes your dict and wraps it in a `SpoilerDict`
- You provide `key_labels` mapping real keys to spoiler-free labels
- The returned dict looks like a normal dict to everything else
- The framework automatically adds `special_spoiler_data` to the slot data
- No changes needed to how you normally return slot data

## For Client Developers

### Automatic Data Extraction (No Code Needed!)

The spoiler system automatically extracts and stores `special_spoiler_data` when you receive a Connected packet. You don't need to do anything special - it just works!

Once connected, you can immediately use helper methods to access revealed keys:

```python
class MyContext(CommonContext):
    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            # That's it! special_spoiler_data is already available
            
            # Use helper methods to access real data
            if hasattr(self, 'get_revealed_key'):
                real_key = self.get_revealed_key("???")
                print(f"Real key: {real_key}")
```

### Helper Methods

Once connected, you have access to these automatic methods:

```python
# Get the real key for a spoiler-free label
real_key = ctx.get_revealed_key("???")
# Returns: "dungeon_1_boss"

# Get the value for a real key
value = ctx.get_revealed_value("dungeon_1_boss")
# Returns: "key_1"

# Get all label->key mappings
all_keys = ctx.get_all_revealed_keys()
# Returns: {"???": "dungeon_1_boss", "???_1": "dungeon_2_boss"}

# Get all key->value mappings
all_items = ctx.get_all_revealed_items()
# Returns: {"dungeon_1_boss": "key_1", "dungeon_2_boss": "key_2"}
```

## How It Works

### Server Side

1. World returns `SpoilerDict` from `fill_slot_data()`
2. Patcher extracts real keys/values and stores in `special_spoiler_data`
3. When serialized to JSON, dict keys become spoiler-free labels
4. `special_spoiler_data` is included as a field in the JSON

### What the Client Receives (JSON)

```json
{
  "??": "key_1",
  "???_1": "key_2",
  "version": 1,
  "special_spoiler_data": {
    "real_keys": {
      "??": "dungeon_1_boss",
      "???_1": "dungeon_2_boss"
    },
    "real_items": {
      "dungeon_1_boss": "key_1",
      "dungeon_2_boss": "key_2"
    }
  }
}
```

### Client Processing

1. Client receives JSON with spoiler-free labels
2. Client calls `process_slot_data_with_spoiler_info()` 
3. `special_spoiler_data` is extracted and stored
4. Helper methods provide access to real data

## Data Integrity

- **Equality**: Two `SpoilerDict`s are equal if data is equal, regardless of labels
- **Serialization**: Data integrity is preserved through JSON
- **Modification**: New keys get auto-generated labels
- **Validation**: Use `validate_spoiler_dict()` to check for issues

## Troubleshooting

### Client can't find revealed keys

Make sure the spoiler module is imported (it's automatic when worlds are loaded). The system automatically extracts `special_spoiler_data` on Connected.

### Keys appear wrong in client slot data

That's expected! The slot data will show spoiler-free labels. Use `special_spoiler_data` to map back.

### Comparison/validation fails

Check that you're comparing the actual data. The `__eq__` method compares dict contents, not labels.

## Examples

### Example 1: Simple Hide Everything

```python
def fill_slot_data(self):
    data = {"location": "item", "other": "data"}
    return apply_spoiler_protection_to_world(data, self)
    # Auto-generates labels: ???, ???_1, etc.
```

### Example 2: Custom Semantic Labels

```python
def fill_slot_data(self):
    data = {
        "boss_1_drop": "treasure",
        "boss_2_drop": "artifact",
        "game_version": 1
    }
    return apply_spoiler_protection_to_world(
        data, self,
        key_labels={
            "boss_1_drop": "First Prize",
            "boss_2_drop": "Second Prize",
        }
    )
```

### Example 3: Client Lookup (Automatic!)

```python
class MyContext(CommonContext):
    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            # It's automatic! No special calls needed.
            
            # Iterate through revealed keys
            for spoiler_label, real_key in self.get_all_revealed_keys().items():
                real_value = self.get_revealed_value(real_key)
                print(f"{spoiler_label} ({real_key}) = {real_value}")
```

## Advanced Usage

See these files for more:

- `ExampleWorld.py` - Detailed world examples
- `SpoilerDictUtils.py` - Utility functions for validation, merging, etc.
- `README.md` - Complete API reference
- `test_spoiler_dict.py` - Test suite with usage patterns

## FAQ

**Q: Do I need to modify my world code much?**
A: No! Just wrap your returned dict in `apply_spoiler_protection_to_world()`.

**Q: Will this break existing worlds?**
A: No. Worlds that don't use it are unaffected. Worlds that use it work with or without the spoiler system.

**Q: Can I use regular dict operations?**
A: Yes! SpoilerDict is a dict subclass, so `[]`, `get()`, `update()`, etc all work.

**Q: What about JSON serialization?**
A: Handled automatically. Spoiler-free labels become the keys in JSON.

**Q: Can I migrate existing worlds?**
A: Yes! See `SpoilerDictUtils.batch_convert_dicts()` for helpers.

**Q: Is there performance overhead?**
A: Minimal. Just key label lookups during iteration.
