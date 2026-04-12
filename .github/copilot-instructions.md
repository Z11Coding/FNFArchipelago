# Friday Night Funkin' Archipelago World - AI Coding Guide

## Project Overview

This is a **Friday Night Funkin'** world implementation for Archipelago multiworld randomizer. The project focuses on `worlds/fridaynightfunkin/` - the core Archipelago framework serves as the testing environment and dependency base.

### FNF World Architecture

- **Main Implementation**: `worlds/fridaynightfunkin/` contains the complete FNF world
  - `__init__.py` - FunkinWorld class with generation logic
  - `Items.py` - Song items, progression items, and mod content
  - `Locations.py` - Week progression, song completion checks
  - `Options.py` - Player configuration (mods, unlock types, song lists)
  - `ModHandler.py` - Dynamic mod loading and ID management
  - `FunkinUtils.py` - FNF-specific utilities and helpers

- **Framework Dependencies**: Core Archipelago files provide the foundation:
  - `BaseClasses.py` - World, Item, Location base classes
  - `Generate.py` - World generation pipeline
  - `CommonClient.py` - Client networking framework
  - `Options.py` - Options system framework

## FNF Development Focus

### Primary Codebase: `worlds/fridaynightfunkin/`
All FNF-specific development happens in this directory. The rest of the repository provides the Archipelago testing environment and framework dependencies.

### World Structure
```python
# worlds/fridaynightfunkin/__init__.py pattern
class FunkinWorld(World):
    def create_items(self) -> None:
        # Item pool creation based on songs and mods
    
    def create_regions(self) -> None:
        # Week/song progression structure
    
    def get_filler_item_name(self) -> str:
        # Default item for extra locations
```

### Mod Integration
- **ModHandler.py** - Extracts mod data and manages player-specific IDs
- Mods add songs/content dynamically during generation
- Use `get_player_specific_ids()` for unique item/location IDs per player

### Options System
```python
# Options.py pattern - inherit from Option base classes
class SongStarter(FreeText):
    """Starting songs for the player."""
    display_name = "Starting Songs"
    default = ""

# Group in dataclass for type safety
@dataclass 
class FunkinOptions(PerGameCommonOptions):
    song_starter: SongStarter
    unlock_type: UnlockType
```

## Development Workflows

### FNF World Testing
- Test FNF world specifically: `python -c "from worlds.fridaynightfunkin import FunkinWorld; print('World loads successfully')"`
- Run FNF generation: `python Generate.py --player_files_path players/ --seed 12345`
- Run world tests: `python -m pytest test/worlds/` (if FNF tests exist)

### Framework Testing
- Test generation: `python Generate.py --player_files_path players/ --seed 12345`
- Test all worlds: `python -m pytest test/worlds/`
- Run framework: The core Archipelago files serve as testing environment

### FNF Item/Location Development
1. Update `worlds/fridaynightfunkin/Items.py` or `Locations.py` with new definitions
2. Assign unique ID ranges (check existing base_id assignments for FNF world)
3. Update `create_items()`/`create_regions()` in `worlds/fridaynightfunkin/__init__.py`
4. Add any new options to `worlds/fridaynightfunkin/Options.py`

### Client Development
- Inherit from `CommonClient` for network protocol handling
- Implement `on_package()` for receiving items from server
- Send location checks with `send_msgs([{"cmd": "LocationChecks", "locations": [...]}])`
- Handle reconnection and save state persistence

### APWorld Packaging
- Create `.apworld` zip file containing world folder
- Include `archipelago.json` with metadata:
```json
{
    "version": 6,
    "compatible_version": 5,
    "game": "Friday Night Funkin'"
}
```

## Critical Patterns

### ID Management
- Base IDs must be unique across all worlds - reserve ranges in coordination
- Use consistent offsets: `base_id + offset` for related items
- Location IDs typically `base_id + 1000, +2000, etc.`

### Error Handling
```python
# Custom errors for clarity
class LocationIDMismatchError(Exception):
    """Raised when location IDs don't match expected values"""
    def __init__(self, location_name, expected_id, actual_id, player_name):
        # Include context for debugging
```

### Threading Safety
- World generation is thread-safe by design
- Use `self.multiworld.random` not `random` module
- Client networking runs on separate threads

### File Paths
- Use `Utils.user_path()` for user data directories
- All paths should be OS-agnostic with `pathlib` or forward slashes
- Reference data files relative to world package root

## Dependencies & Build

- **Core**: Python 3.8+, websockets, PyYAML, Jinja2
- **GUI**: Kivy for launcher and client interfaces  
- **Build**: `setup.py` generates frozen executables with cx_Freeze
- **Web**: Flask + Pony ORM for WebHostLib database operations

Install dev environment:
```bash
pip install -r requirements.txt
python ModuleUpdate.py  # Updates dependencies
```

## Common Gotchas

- **Case sensitivity**: apworld files must be lowercase
- **Import timing**: Always call `ModuleUpdate.update()` before other AP imports
- **Option validation**: Options validate on world creation, not definition
- **ID conflicts**: Check existing worlds before assigning ID ranges
- **Client state**: Handle multiple item receipts gracefully (items can be received multiple times)