# Spoiler Dict System - Architecture & Integration

## System Overview

The Spoiler Dict system is a standalone module in `/worlds/spoiler/` that provides automatic spoiler-free key labels for slot data without modifying core Archipelago code.

## Component Interaction

```
┌─────────────────────────────────────────────────────────────┐
│                    Archipelago Generation                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │  World.fill_slot_data() called          │
        │  (patched by SpoilerDict system)        │
        └─────────────────────────────────────────┘
                              │
         ┌────────────────────┴────────────────────┐
         │                                         │
         ▼                                         ▼
    Original dict              SpoilerDict with labels
    (returned by world)        (wrapped by patcher)
         │                                         │
         └────────────────────┬────────────────────┘
                              │
                              ▼
                ┌──────────────────────────────┐
                │ patch_slotdata_with_spoiler_ │
                │ data() extracts metadata     │
                └──────────────────────────────┘
                              │
                              ▼
        Slot data with special_spoiler_data
        ┌──────────────────────────────────────┐
        │ {                                    │
        │   "??": "item_1",        // spoiler- │
        │   "???_1": "item_2",     // free     │
        │   "version": 1,          // labels   │
        │   "special_spoiler_data": {          │
        │     "real_keys": {...},              │
        │     "real_items": {...}              │
        │   }                                  │
        │ }                                    │
        └──────────────────────────────────────┘
                              │
                              ▼
                    Network Transmission
                   (JSON serialization)
                              │
         ┌────────────────────┴────────────────────┐
         │                                         │
         ▼                                         ▼
    Connected Response         Client receives
    (to all clients)           slot_data with labels
         │                     and special_spoiler_data
         │                              │
         ▼                              ▼
                    ┌──────────────────────────┐
                    │  CommonClient.on_package │
                    │  (Connected)             │
                    └──────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │ process_slot_data_with_  │
                    │ spoiler_info() called    │
                    └──────────────────────────┘
                                   │
                                   ▼
                    ctx.special_spoiler_data
                    populated with mappings
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │ Helper methods available │
                    │ get_revealed_key()       │
                    │ get_revealed_value()     │
                    │ get_all_revealed_keys()  │
                    │ get_all_revealed_items() │
                    └──────────────────────────┘
```

## File Structure

```
worlds/spoiler/
├── __init__.py                      # Main module, World patching
├── SpoilerDict.py                   # Core dict subclass
├── CommonClientSpoilerHandler.py    # CommonClient patching
├── SpoilerDictUtils.py              # Utility functions
├── ExampleWorld.py                  # Usage examples
├── test_spoiler_dict.py             # Test suite
├── README.md                        # Complete API docs
├── QUICKSTART.md                    # Quick start guide
└── ARCHITECTURE.md                  # This file
```

## Patching Strategy

### 1. World Patching (SpoilerDict.__init__.py)

**Location**: `World.__getattribute__`

**How it works**:
```python
_original_world_getattribute = World.__getattribute__

def _patched_world_getattribute(self, name: str):
    if name == 'fill_slot_data':
        original_method = _original_world_getattribute(self, name)
        def wrapped_fill_slot_data():
            result = original_method()
            # Extract SpoilerDict data and add special_spoiler_data
            result = patch_slotdata_with_spoiler_data(result)
            return result
        return wrapped_fill_slot_data
    return _original_world_getattribute(self, name)
```

**Benefits**:
- Works on all worlds without modification
- Transparent to normal dict operations
- Preserves original world behavior if no SpoilerDict used

### 2. CommonClient Patching (CommonClientSpoilerHandler.py)

**Location**: `CommonContext.__init__` and added methods

**How it works**:
```python
def patched_init(self, ...):
    original_init(self, ...)
    self.special_spoiler_data = {}  # Add attribute

# Add helper methods
CommonContext.get_revealed_key = get_revealed_key
CommonContext.get_revealed_value = get_revealed_value
CommonContext.get_all_revealed_keys = get_all_revealed_keys
CommonContext.get_all_revealed_items = get_all_revealed_items
```

**Benefits**:
- Non-invasive method injection
- Works with any CommonContext subclass
- Methods are optional (graceful if not used)

## Data Flow Detailed

### Generation Phase

1. **World Generation**
   ```python
   # World's fill_slot_data() returns normal dict or SpoilerDict
   slot_data = {
       "secret_1": "value_1",
       "secret_2": "value_2",
   }
   return apply_spoiler_protection_to_world(slot_data, self, ...)
   ```

2. **SpoilerDict Creation**
   ```python
   # SpoilerDict wraps the data
   SpoilerDict(
       real_data={"secret_1": "value_1", "secret_2": "value_2"},
       key_labels={"secret_1": "???", "secret_2": "???_1"}
   )
   ```

3. **Patcher Interception**
   ```python
   # When fill_slot_data() is called, patcher wraps it:
   # - Detects SpoilerDict instances
   # - Extracts real_keys and real_items
   # - Adds special_spoiler_data field
   ```

4. **Metadata Extraction**
   ```python
   {
       "data": SpoilerDict(...),  # Gets JSON serialized
       "special_spoiler_data": {
           "real_keys": {"???": "secret_1", "???_1": "secret_2"},
           "real_items": {"secret_1": "value_1", "secret_2": "value_2"}
       }
   }
   ```

### Network Transmission

5. **JSON Serialization**
   ```python
   # SpoilerDict.__iter__ and .keys() return spoiler-free labels
   json_dict = {
       "???": "value_1",
       "???_1": "value_2",
       "special_spoiler_data": {...}
   }
   ```

6. **Network Send**
   - Slot data as JSON is sent in Connected response
   - special_spoiler_data included as-is

### Reception Phase

7. **Client Receives**
   ```python
   {
       "???": "value_1",
       "???_1": "value_2",
       "special_spoiler_data": {...}
   }
   ```

8. **Processing**
   ```python
   # In on_package() with cmd == "Connected":
   process_slot_data_with_spoiler_info(self, args.get("slot_data", {}))
   
   # This extracts special_spoiler_data and stores it in ctx
   ```

9. **Access**
   ```python
   # Client can now use helper methods:
   real_key = ctx.get_revealed_key("???")  # "secret_1"
   value = ctx.get_revealed_value("secret_1")  # "value_1"
   ```

## Key Design Decisions

### 1. Subclassing dict

**Decision**: SpoilerDict extends dict

**Rationale**:
- 100% compatibility with existing dict-expecting code
- JSON serialization works automatically
- Type checks and isinstance() work correctly
- All dict methods available

**Trade-off**: Some complexity in method overriding

### 2. Separate special_spoiler_data

**Decision**: Store real data separately, not mixed in slot_data

**Rationale**:
- Keeps the layer clean and separate
- Easy to strip if needed
- Doesn't interfere with normal slot data
- Clients can ignore if not needed

**Trade-off**: Adds a field to slot_data

### 3. Label-based hiding

**Decision**: Use arbitrary spoiler-free labels instead of obfuscation

**Rationale**:
- More flexible (can have semantic labels)
- Reversible (can always map back)
- Works with any data type as values
- Can be used with human-readable labels

**Trade-off**: Not actual encryption/hiding

### 4. World-level patching

**Decision**: Patch at World.__getattribute__ instead of fill_slot_data directly

**Rationale**:
- Works on all worlds without modification
- Can patch before world initialization
- Preserves inheritance chain
- Minimal performance impact

**Trade-off**: Some complexity in interception logic

### 5. Automatic client-side processing

**Decision**: Patch `process_server_cmd` to automatically extract special_spoiler_data on Connected

**Rationale**:
- Zero manual calls needed in clients
- Fully transparent integration
- Helper methods always available
- Graceful fallback for clients that don't use it

**Trade-off**: None - this is strictly better than manual extraction

## Compatibility

### Backward Compatibility

- Worlds without SpoilerDict work unchanged
- Worlds with SpoilerDict also work unchanged
- Systems that don't know about special_spoiler_data ignore it
- Datapackage validation unaffected (equality based on data, not labels)

### Forward Compatibility

- Can add new metadata fields to special_spoiler_data
- Can version the format if needed
- Helper methods in CommonClient can be extended

## Performance Considerations

### Server Side
- Minimal overhead: One attribute lookup during fill_slot_data
- No additional I/O or computation for non-SpoilerDict worlds
- Label lookup in iteration is negligible

### Network
- Additional field (special_spoiler_data) adds ~200 bytes per world
- No performance impact for worlds not using SpoilerDict

### Client Side
- One-time extraction of special_spoiler_data on Connected
- Helper method calls do dict lookups (O(1))
- No ongoing performance impact

## Security Considerations

**Note**: This is NOT a security feature. It's spoiler protection, not encryption.

- Labels are not secret (sent in JSON with data)
- Anyone with access to slot data can reveal keys
- Not suitable for actual security needs
- Use actual encryption/authorization for sensitive data

**Intended Use**: Prevent accidental spoilers for players, not defend against determined cheating.

## Future Extensions

Possible enhancements:

1. **Hierarchical Labels**: Support nested spoiler dicts
2. **Format Versioning**: Track metadata format version
3. **Label Rotation**: Periodically change labels for added obscurity
4. **Partial Revelation**: Reveal some keys at certain game points
5. **Client-side Filtering**: Only send revealed data to specific clients
6. **Analytics**: Track which revealed keys are accessed

## Testing

Run tests with:
```bash
python -m pytest worlds/spoiler/test_spoiler_dict.py -v
```

Covers:
- SpoilerDict core functionality
- Equality and hashing
- Label management
- World patching
- Utility functions
- Integration scenarios

## Deployment

1. Copy the `/worlds/spoiler/` folder to target Archipelago installation
2. Import the module to activate patches:
   ```python
   from worlds import spoiler  # Activates ALL patches automatically
   ```
3. Worlds can start using `apply_spoiler_protection_to_world()`
4. **Clients automatically handle everything** - no code needed!
   - special_spoiler_data is automatically extracted on Connected
   - Helper methods are automatically available

## Troubleshooting Guide

### Patches not applying
- Ensure `from worlds import spoiler` is called before World creation
- Check logs for patch initialization messages

### special_spoiler_data missing
- Verify world uses `apply_spoiler_protection_to_world()`
- Check that SpoilerDict is actually returned

### Client can't access revealed data
- Verify the spoiler module is imported (automatic when worlds load)
- Check that special_spoiler_data is being populated in ctx
- Ensure helper methods exist on context (they should be auto-injected)

### Datapackage validation fails
- Ensure SpoilerDict.__eq__ is comparing data correctly
- Check that no other fields were modified
- Verify keys are identical (labels don't matter)

## Related Systems

- **YAML Embedder**: Similar patching approach, inspired this design
- **Data Package**: Handles checksums and validation
- **CommonClient**: Base system for client connections
- **World**: Base system for world definitions

## References

- See README.md for complete API documentation
- See QUICKSTART.md for usage patterns
- See ExampleWorld.py for implementation examples
- See test_spoiler_dict.py for test patterns
