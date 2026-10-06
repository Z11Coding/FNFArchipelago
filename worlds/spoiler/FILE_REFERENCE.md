# Spoiler System - File Reference

## Complete File Listing

```
worlds/spoiler/
├── SpoilerDict.py                   [Core Implementation]
├── __init__.py                      [Main Module & World Patching]
├── CommonClientSpoilerHandler.py    [CommonClient Integration]
├── SpoilerDictUtils.py              [Utility Functions]
├── ExampleWorld.py                  [Usage Examples]
├── test_spoiler_dict.py             [Test Suite]
├── README.md                        [Complete API Reference]
├── QUICKSTART.md                    [Quick Start Guide]
├── ARCHITECTURE.md                  [System Architecture]
├── IMPLEMENTATION_SUMMARY.md        [This Overview]
└── FILE_REFERENCE.md                [File Descriptions]
```

## File Descriptions

### Core Implementation Files

#### SpoilerDict.py (~300 lines)
**Purpose**: Core dict subclass with spoiler-free labels

**Exports**:
- `SpoilerDict` - Main class

**Key Methods**:
- `revealed_keys()` - Get actual keys
- `revealed_items()` - Get actual (key, value) pairs
- `revealed_values()` - Get values
- `set_label()` - Set custom label for a key
- `get_label()` - Get label for a key
- `get_revealed_key_for_label()` - Reverse lookup
- `copy()` - Copy preserving labels
- `update()` - Update dict
- `to_dict()` - Convert to regular dict
- `from_dict()` - Create from regular dict

**Key Features**:
- Subclasses dict for full compatibility
- Iteration shows spoiler-free labels
- Direct access ([], get()) uses real keys
- Proper __eq__ for data comparison
- JSON serialization uses spoiler-free labels

**Use When**: You need a dict that hides keys behind spoiler labels

#### __init__.py (~220 lines)
**Purpose**: Main module with World patching

**Exports**:
- `apply_spoiler_protection_to_world()` - Wrap slot_data in SpoilerDict
- `convert_dict_to_spoiler_dict()` - Convert regular dict
- `extract_spoiler_metadata_for_slotdata()` - Get metadata
- `patch_slotdata_with_spoiler_data()` - Add special_spoiler_data
- `initialize_spoiler_patcher()` - Initialize patches

**Patches**:
- `World.__getattribute__` - Intercepts fill_slot_data

**Auto-Initialization**:
- Patches applied automatically on import
- Includes CommonClientSpoilerHandler

**Use When**: Setting up spoiler protection in a world

#### CommonClientSpoilerHandler.py (~250 lines)
**Purpose**: CommonClient integration for spoiler data

**Exports**:
- `process_slot_data_with_spoiler_info()` - Extract spoiler data

**Patches**:
- `CommonContext.__init__` - Adds special_spoiler_data attribute
- `CommonContext` - Adds helper methods

**Added Methods to CommonContext**:
- `get_revealed_key(label, data_key=None)` - Get real key for label
- `get_revealed_value(real_key, data_key=None)` - Get value for key
- `get_all_revealed_keys(data_key=None)` - Get all label->key mappings
- `get_all_revealed_items(data_key=None)` - Get all key->value mappings

**Auto-Initialization**:
- Patches applied automatically on import

**Use When**: Clients need to access revealed keys from special_spoiler_data

### Utility Files

#### SpoilerDictUtils.py (~320 lines)
**Purpose**: Utility functions for working with SpoilerDicts

**Exports**:
- `batch_convert_dicts()` - Convert nested dicts to SpoilerDict
- `inject_default_labels()` - Set default labels for keys
- `validate_spoiler_dict()` - Check for validation issues
- `print_spoiler_dict_debug_info()` - Pretty-print debug info
- `compare_spoiler_dicts()` - Compare two instances
- `merge_spoiler_dicts()` - Merge multiple instances
- `get_spoiler_json_preview()` - See JSON representation
- `create_reverse_label_lookup()` - Create label->key mapping

**Use When**: 
- Validating SpoilerDict instances
- Debugging labels
- Converting existing dicts
- Comparing spoiler dicts
- Seeing what JSON will look like

### Documentation Files

#### README.md (~400 lines)
**Purpose**: Complete API reference and usage guide

**Contents**:
- Features overview
- Quick start examples
- Complete API reference for all classes/functions
- How it works explanation
- Data integrity information
- Thread safety notes
- Limitations
- Multiple usage examples
- Troubleshooting guide

**Read This For**: Complete understanding of API and usage

#### QUICKSTART.md (~250 lines)
**Purpose**: 5-minute quick start for developers

**Contents**:
- What is this?
- Setup instructions
- For World Developers - how to protect slot data
- For Client Developers - how to access revealed keys
- How it works (simplified)
- Data integrity
- Troubleshooting
- FAQ

**Read This For**: Getting started quickly

#### ARCHITECTURE.md (~400 lines)
**Purpose**: Deep dive into system architecture

**Contents**:
- System overview with diagrams
- Component interactions
- File structure
- Patching strategy
- Detailed data flow (4 phases)
- Key design decisions with rationale
- Compatibility considerations
- Performance analysis
- Security notes (not secure, spoiler only)
- Future extensions
- Testing guide
- Troubleshooting guide
- Related systems

**Read This For**: Understanding how the system works internally

#### IMPLEMENTATION_SUMMARY.md (~300 lines)
**Purpose**: Overall implementation summary

**Contents**:
- What was created (overview)
- Files created with descriptions
- Key features checklist
- Usage patterns
- Network protocol example
- Design highlights
- Separation of concerns
- Distribution model
- Files modified (none!)
- Testing instructions
- Code quality notes
- Summary statistics

**Read This For**: High-level overview of the implementation

#### FILE_REFERENCE.md (This File)
**Purpose**: Quick reference for all files

**Use This For**: Finding which file contains what

### Example & Test Files

#### ExampleWorld.py (~200 lines)
**Purpose**: Example implementations

**Contents**:
- `ExampleSpoilerWorld` - Basic usage with automatic labels
- `AdvancedSpoilerWorld` - Custom semantic labels
- `ManualSpoilerDictWorld` - Manual SpoilerDict creation
- `example_client_usage()` - Client-side usage pattern

**Use This For**: 
- Learning how to implement spoiler protection
- Understanding different usage patterns
- Copy-paste starting point for your world

#### test_spoiler_dict.py (~350 lines)
**Purpose**: Comprehensive test suite

**Contains**:
- TestSpoilerDict - Core dict functionality tests
- TestApplySpoilerProtection - World patching tests
- TestPatchSlotData - Slot data patching tests
- TestSpoilerDictUtils - Utility function tests

**Test Commands**:
```bash
# Run all tests
python -m pytest worlds/spoiler/test_spoiler_dict.py -v

# Run specific test class
python -m pytest worlds/spoiler/test_spoiler_dict.py::TestSpoilerDict -v

# Run specific test
python -m pytest worlds/spoiler/test_spoiler_dict.py::TestSpoilerDict::test_basic_creation -v
```

**Use This For**:
- Validating the system works
- Learning test patterns
- Understanding usage through tests

## Quick Navigation Guide

### "I want to..."

**...understand the big picture**
→ IMPLEMENTATION_SUMMARY.md

**...get started in 5 minutes**
→ QUICKSTART.md

**...see all API methods**
→ README.md

**...understand how it works internally**
→ ARCHITECTURE.md

**...see example implementations**
→ ExampleWorld.py

**...implement spoiler protection in my world**
→ QUICKSTART.md (For World Developers section)

**...access revealed keys in my client**
→ QUICKSTART.md (For Client Developers section)

**...work with SpoilerDict programmatically**
→ README.md (API Reference section)

**...debug/validate SpoilerDict instances**
→ SpoilerDictUtils.py + ARCHITECTURE.md

**...understand the design decisions**
→ ARCHITECTURE.md (Key Design Decisions section)

**...verify everything works**
→ Run test_spoiler_dict.py

## Module Import Hierarchy

```
from worlds.spoiler import SpoilerDict
from worlds.spoiler import apply_spoiler_protection_to_world
from worlds.spoiler import convert_dict_to_spoiler_dict
from worlds.spoiler import patch_slotdata_with_spoiler_data
from worlds.spoiler import process_slot_data_with_spoiler_info
from worlds.spoiler.SpoilerDictUtils import (
    batch_convert_dicts,
    validate_spoiler_dict,
    print_spoiler_dict_debug_info,
    compare_spoiler_dicts,
    merge_spoiler_dicts,
    get_spoiler_json_preview,
    create_reverse_label_lookup,
)
```

## Initialization Flow

1. **On Import**: `from worlds import spoiler`
   - SpoilerDict.py loaded
   - __init__.py loads and patches World.__getattribute__
   - __init__.py imports CommonClientSpoilerHandler
   - CommonClientSpoilerHandler.py patches CommonContext

2. **On World Creation**: 
   - Patched __getattribute__ intercepts fill_slot_data
   - Returns wrapped version that adds special_spoiler_data

3. **On Client Connected**:
   - Clients call process_slot_data_with_spoiler_info()
   - special_spoiler_data extracted and stored
   - Helper methods become available

## Dependencies

**None outside Archipelago!**
- Only uses standard library (typing, logging, json)
- Works with any Python version that Archipelago supports
- No external packages required

## Compatibility

- ✅ Python 3.8+
- ✅ All Archipelago versions with World/CommonContext
- ✅ Existing worlds (no modification needed)
- ✅ Regular dicts (no issues)
- ✅ JSON serialization
- ✅ Datapackage validation

## File Sizes (Approximate)

| File | Lines | Purpose |
|------|-------|---------|
| SpoilerDict.py | 300 | Core implementation |
| __init__.py | 220 | World patching |
| CommonClientSpoilerHandler.py | 250 | Client integration |
| SpoilerDictUtils.py | 320 | Utilities |
| ExampleWorld.py | 200 | Examples |
| test_spoiler_dict.py | 350 | Tests |
| README.md | 400 | API docs |
| QUICKSTART.md | 250 | Quick start |
| ARCHITECTURE.md | 400 | Architecture |
| IMPLEMENTATION_SUMMARY.md | 300 | Overview |
| FILE_REFERENCE.md | 250 | This file |
| **TOTAL** | **~3,500** | |

## Total Content

- **1000+ lines of code** (core implementation)
- **1500+ lines of documentation**
- **350+ lines of tests**
- **Zero breaking changes to Archipelago**

All contained in: `/worlds/spoiler/`

Ready to use immediately!
