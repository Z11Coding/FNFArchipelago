"""AP Hook - Extracts Archipelago world metadata."""

import sys
import os
import json
import argparse
import dataclasses
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, get_args, get_origin
from Options import OptionGroup
import Main


# Custom Exceptions
class APHookError(Exception):
    """Base exception for AP Hook errors."""
    pass


class ModuleImportError(APHookError):
    """Raised when a module cannot be imported."""
    pass


class OptionsExtractionError(APHookError):
    """Raised when options metadata cannot be extracted."""
    pass


class WorldDataExtractionError(APHookError):
    """Raised when world data cannot be extracted."""
    pass


class OutputSaveError(APHookError):
    """Raised when output file cannot be saved."""
    pass


@dataclass
class WorldData:
    """Container for single world's items, locations, and options data."""
    game_name: str
    items: Dict[str, int] = field(default_factory=dict)
    locations: Dict[str, int] = field(default_factory=dict)
    item_groups: Dict[str, List[str]] = field(default_factory=dict)
    location_groups: Dict[str, List[str]] = field(default_factory=dict)
    description: str = ""
    options: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    option_groups: List[OptionGroup] = field(default_factory=list)
    version: str = "unknown"
    required_client_version: Optional[Tuple[int, int, int]] = None
    required_server_version: Optional[Tuple[int, int, int]] = None


@dataclass
class APData:
    """Container mapping game names to their world metadata."""
    worlds: Dict[str, WorldData] = field(default_factory=dict)
    version: str = "unknown"
    failed_worlds: List[str] = field(default_factory=list)
    
    @property
    def total_worlds(self) -> int:
        """Count of loaded worlds."""
        return len(self.worlds)
    
    @property
    def total_items(self) -> int:
        """Sum of all items across worlds."""
        return sum(len(world.items) for world in self.worlds.values())
    
    @property
    def total_locations(self) -> int:
        """Sum of all locations across worlds."""
        return sum(len(world.locations) for world in self.worlds.values())
    
    @property
    def total_options(self) -> int:
        """Sum of all options across worlds."""
        return sum(len(world.options) for world in self.worlds.values())
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize APData to JSON-compatible dictionary."""
        return {
            "worlds": {
                game_name: {
                    "items": world.items,
                    "locations": world.locations,
                    "item_groups": world.item_groups,
                    "location_groups": world.location_groups,
                    "description": world.description,
                    "options": world.options,
                    "option_groups": world.option_groups,
                    "world_version": world.version,
                    "required_client_version": world.required_client_version,
                    "required_server_version": world.required_server_version,
                }
                for game_name, world in self.worlds.items()
            },
            "metadata": {
                "total_worlds": self.total_worlds,
                "total_items": self.total_items,
                "total_locations": self.total_locations,
                "total_options": self.total_options,
                "ap_version": self.version,
                "failed_worlds": self.failed_worlds,
            }
        }

global_ap_path: Optional[str] = None


def setup_archipelago_path(ap_path: Optional[str] = None) -> str:
    """Setup and validate Archipelago path, returns resolved path."""
    if ap_path is None:
        ap_path = r"C:\ProgramData\Archipelago"
    
    ap_path = str(Path(ap_path).resolve())
    
    if not os.path.isdir(ap_path):
        raise FileNotFoundError(f"Archipelago path not found: {ap_path}")
    
    sys.meta_path = ap_path
    
    has_lib_worlds = os.path.isdir(os.path.join(ap_path, "lib", "worlds"))
    has_module_update = os.path.isfile(os.path.join(ap_path, "ModuleUpdate.py"))
    
    if not (has_lib_worlds or has_module_update):
        raise FileNotFoundError(
            f"Path does not appear to be an Archipelago installation: {ap_path}"
        )
    
    if ap_path not in sys.path:
        sys.path.insert(0, ap_path)
    
    global global_ap_path
    global_ap_path = ap_path
    
    print(f"[*] Using Archipelago path: {ap_path}")
    return ap_path


def import_from_ap_path(module_name: str):
    """Import module from AP path, tries multiple locations."""
    import importlib
    import importlib.util as util
    try:
        return util.find_spec(module_name) and __import__(module_name)
    except ImportError as e:
        print(f"[!] ERROR: Failed to import {module_name} from default location: {e}")
    
    if global_ap_path and global_ap_path not in sys.path:
        sys.path.insert(0, global_ap_path)
        try:
            return util.find_spec(module_name) and __import__(module_name)
        except ImportError as e:
            print(f"[!] ERROR: Failed to import {module_name} from AP path: {e}")
    
    if global_ap_path:
        lib_path = os.path.join(global_ap_path, "lib")
        if os.path.isdir(lib_path) and lib_path not in sys.path:
            sys.path.insert(0, lib_path)
            try:
                return util.find_spec(module_name) and __import__(module_name)
            except ImportError as e:
                print(f"[!] ERROR: Failed to import {module_name} from lib path: {e}")
    
    error_msg = f"Cannot import module '{module_name}' from any location"
    print(f"[!] ERROR: {error_msg}")
    raise ModuleImportError(error_msg)


def initialize_archipelago() -> None:
    """Initialize Archipelago and run ModuleUpdate."""
    print("[*] Initializing Archipelago...")
    try:
        ModuleUpdate = import_from_ap_path("ModuleUpdate")
        ModuleUpdate.update()
        print("[*] ModuleUpdate complete")
    except Exception as e:
        error_msg = f"Could not initialize ModuleUpdate: {e}"
        print(f"[!] ERROR: {error_msg}")
        raise APHookError(error_msg)


def load_worlds() -> Tuple[Dict[str, Type], List[str]]:
    """Load all world sources and return world type mapping."""
    print("[*] Loading worlds...")
    
    try:
        worlds = import_from_ap_path("worlds")
        from worlds.AutoWorld import AutoWorldRegister
        
        failed = []
        for world_source in worlds.world_sources:
            if not world_source.load():
                failed.append(str(world_source))
        
        if failed:
            print(f"[!] Failed to load {len(failed)} world(s):")
            for f in failed:
                print(f"    - {f}")
        
        print(f"[*] Successfully loaded {len(AutoWorldRegister.world_types)} world(s)")
        return AutoWorldRegister.world_types, failed
    except Exception as e:
        print(f"[!] Error: Failed to import worlds: {e}")
        raise


def extract_schema_as_json_schema(schema_obj: Any) -> Dict[str, Any]:
    """
    Convert Schema to JSON.
    """
    try:
        from schema import Schema
    except ImportError:
        return {"error": "schema library not available"}
    
    if not isinstance(schema_obj, Schema):
        return {"error": f"Expected Schema object, got {type(schema_obj).__name__}"}
    
    try:
        json_schema = schema_obj.json_schema(
            schema_id="option_schema",
            use_refs=False  # Don't use $ref for simplicity in Godot
        )
        return json_schema
    except Exception as e:
        return {"error": f"Failed to convert schema: {str(e)}", "schema_type": type(schema_obj).__name__}


def extract_option_type_info(option_class: Type, option_groups: List[OptionGroup]) -> Dict[str, Any]:
    """Extract type info from option class via MRO inspection."""
    type_info: Dict[str, Any] = {}
    
    class_name = option_class.__name__
    type_info["type"] = class_name
    
    mro_bases = []
    for base in option_class.__mro__[1:]:
        if base.__name__ not in ("object", "Generic"):
            mro_bases.append(base.__name__)
    
    if mro_bases:
        type_info["inheritance_chain"] = mro_bases
    
    if any(base.__name__ == "Range" for base in option_class.__mro__):
        type_info["semantic_type"] = "range"
        if hasattr(option_class, "range_start"):
            type_info["min"] = option_class.range_start
        if hasattr(option_class, "range_end"):
            type_info["max"] = option_class.range_end
        if hasattr(option_class, "allow_below_range"):
            type_info["allow_below_range"] = option_class.allow_below_range
        if hasattr(option_class, "allow_above_range"):
            type_info["allow_above_range"] = option_class.allow_above_range
        if hasattr(option_class, "special_range_names") and option_class.special_range_names:
            type_info["special_range_names"] = option_class.special_range_names
    
    elif any(base.__name__ == "Choice" for base in option_class.__mro__):
        type_info["semantic_type"] = "choice"
        options = {}
        for attr_name in dir(option_class):
            if attr_name.startswith("option_"):
                option_key = attr_name[7:]
                option_value = getattr(option_class, attr_name)
                options[option_key] = option_value
        if options:
            type_info["options"] = options
    
    elif any(base.__name__ == "Toggle" for base in option_class.__mro__):
        type_info["semantic_type"] = "toggle"
        type_info["subtype"] = "boolean"
    
    elif any(base.__name__ == "FreeText" for base in option_class.__mro__):
        type_info["semantic_type"] = "freetext"
        type_info["subtype"] = "string"
    
    elif any(base.__name__ == "OptionList" for base in option_class.__mro__):
        type_info["semantic_type"] = "list"
        if hasattr(option_class, "valid_keys"):
            if option_class.valid_keys:
                type_info["valid_keys"] = list(option_class.valid_keys)
    elif any(base.__name__ == "OptionDict" for base in option_class.__mro__):
        type_info["semantic_type"] = "dict"
        if hasattr(option_class, "valid_keys") and option_class.valid_keys:
            type_info["valid_keys"] = list(option_class.valid_keys)
    elif any(base.__name__ == "OptionSet" for base in option_class.__mro__):
        type_info["semantic_type"] = "set"
        if hasattr(option_class, "valid_keys"):
            if option_class.valid_keys:
                type_info["valid_items"] = list(option_class.valid_keys)
    elif any(base.__name__ == "OptionCounter" for base in option_class.__mro__):
        type_info["semantic_type"] = "counter"
        if hasattr(option_class, "valid_keys") and option_class.valid_keys:
            type_info["valid_keys"] = list(option_class.valid_keys)
        
    def set_to_list(value):
        """Convert set to list, cuz yes."""
        if isinstance(value, (set, frozenset)):
            return [item for item in value] # I don't trust direct conversion, so using iteration.
        return value
    
    if hasattr(option_class, "default"):
        type_info["default"] = set_to_list(option_class.default)
    
    if option_groups:
        groups = [group for group in option_groups if option_class in group.options]
        if groups:
            type_info["group"] = groups[0].name
    
    # Extract JSON Schema rules for complex types
    complex_type_names = ("OptionDict", "OptionList", "OptionSet", "OptionCounter", 
                          "ItemDict", "ItemSet", "ItemLinks", "PlandoItems", "PlandoTexts", 
                          "PlandoConnections")
    
    if any(base.__name__ in complex_type_names for base in option_class.__mro__) and hasattr(option_class, "schema"):
        try:
            schema_obj = option_class.schema
            json_schema_rules = extract_schema_as_json_schema(schema_obj)
            if json_schema_rules and "error" not in json_schema_rules:
                type_info["json_schema"] = json_schema_rules
        except Exception as e:
            # Log schema extraction errors but don't fail the whole extraction
            type_info["schema_extraction_error"] = str(e)
    
    return type_info


def extract_options_metadata(options_dataclass: Type, option_groups: List[OptionGroup]) -> Dict[str, Dict[str, Any]]:
    """Extract metadata for all options in dataclass."""
    options_metadata: Dict[str, Dict[str, Any]] = {}
    try:
        fields = dataclasses.fields(options_dataclass)
    except TypeError as e:
        error_msg = f"Failed to extract options metadata from {options_dataclass.__name__}: {e}"
        print(f"[!] ERROR: {error_msg}")
        raise OptionsExtractionError(error_msg)
    
    import Options as options_module # Because fields are dumb...
    namespace = {name: getattr(options_module, name) for name in dir(options_module) if not name.startswith('_')}
    
    for field in fields:
        option_class = field.type
        
        if isinstance(option_class, str):
            if option_class in namespace:
                option_class = namespace[option_class]
            else:
                continue
        
        option_class = (option_class)
                
        option_name = field.name
        display_name = getattr(option_class, "display_name", option_name)
        docstring = option_class.__doc__ or ""
        
        type_info = extract_option_type_info(option_class, option_groups)
        
        options_metadata[option_name] = {
            "display_name": display_name,
            "class": option_class.__name__,
            "docstring": docstring if docstring else "",
            "type_info": type_info,
        }
    
    return options_metadata

def group_set_to_list(group:Dict):
    """Convert sets in option groups to lists for JSON serialization."""
    converted_group = {}
    for key, value in group.items():
        names = []
        for name in value: # I tried direct list converting, but it didn't work... so here's the manual way! YAY! :D
            names.append(name)
        converted_group[key] = names
    return converted_group

def extract_world_data(game_name: str, world_class: Type) -> WorldData:
    """Extract items, locations, options, and description from world class."""
    world_data = WorldData(game_name=game_name)

    from worlds.AutoWorld import World
    world_class: Type[World] = world_class
    
    if hasattr(world_class, "item_name_to_id"):
        world_data.items = dict(world_class.item_name_to_id)

    if hasattr(world_class, "item_name_groups"):
        world_data.item_groups = group_set_to_list(dict(world_class.item_name_groups))

    if hasattr(world_class, "location_name_to_id"):
        world_data.locations = dict(world_class.location_name_to_id)
    
    if hasattr(world_class, "location_name_groups"):
        world_data.location_groups = group_set_to_list(dict(world_class.location_name_groups))
    
    description = ""
    if hasattr(world_class, "web") and world_class.web is not None:
        web = world_class.web
        if hasattr(web, "game_description"):
            description = web.game_description
        world_data.option_groups = getattr(web, "option_groups", {})
    
    if not description and world_class.__doc__:
        description = inspect.getdoc(world_class).split("\n")[0]
    
    world_data.description = description
    
    if hasattr(world_class, "options_dataclass"):
        world_data.options = extract_options_metadata(world_class.options_dataclass, world_data.option_groups)

    world_data.version = world_class.world_version.as_simple_string() if hasattr(world_class, "world_version") else "unknown"
    world_data.required_client_version = getattr(world_class, "required_client_version", None)
    world_data.required_server_version = getattr(world_class, "required_server_version", None)
    
    return world_data


def extract_all_worlds_data(world_types: Dict[str, Type]) -> APData:
    """Extract data from all world types, returns APData with all worlds."""
    print("[*] Extracting world data...")
    
    ap_data = APData()
    # import Main

    ap_data.version = Main.__version__ if hasattr(Main, "__version__") else "unknown"
    
    for game_name, world_class in sorted(world_types.items()):
        try:
            world_data = extract_world_data(game_name, world_class)
            ap_data.worlds[game_name] = world_data
        except Exception as e:
            error_msg = f"Failed to extract data from {game_name}: {e}"
            print(f"[!] ERROR: {error_msg}")
            raise WorldDataExtractionError(error_msg)
    
    print(f"[*] Successfully extracted data from {len(ap_data.worlds)} world(s)")
    return ap_data


def format_output(ap_data: APData) -> str:
    """Serialize APData as formatted JSON string."""
    return json.dumps(ap_data.to_dict(), indent=2, default=str)


def display_summary(ap_data: APData) -> None:
    """Print summary of world counts to console."""
    print("\n" + "="*70)
    print("ARCHIPELAGO ENVIRONMENT SUMMARY")
    print("="*70)
    
    print(f"Total Worlds: {ap_data.total_worlds}")
    print(f"Total Items: {ap_data.total_items}")
    print(f"Total Locations: {ap_data.total_locations}")
    print(f"Total Options: {ap_data.total_options}")
    print(f"Archipelago Version: {ap_data.version}")
    print(f"Failed Worlds: {len(ap_data.failed_worlds)}")
    if ap_data.failed_worlds:
        for f in ap_data.failed_worlds:
            print(f"    - {f}")
    print("="*70 + "\n")


def save_output_file(formatted_output: str, output_path: str = "ap_hook_output.json") -> None:
    """Write JSON output to file."""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(formatted_output)
        print(f"[*] Output saved to: {output_path}")
    except Exception as e:
        error_msg = f"Failed to save output file {output_path}: {e}"
        print(f"[!] ERROR: {error_msg}")
        raise OutputSaveError(error_msg)


def main():
    """Load worlds, extract metadata, save JSON, and optionally open file."""
    try:
        print("\n[*] AP Hook - Archipelago Environment Metadata Extractor\n")

        import os
        
        ap_path = setup_archipelago_path(os.getcwd())
        initialize_archipelago()
        world_types = load_worlds()
        
        if not world_types:
            print("[!] No worlds loaded!")
            return
        
        ap_data = extract_all_worlds_data(world_types[0])
        ap_data.failed_worlds = world_types[1]
        display_summary(ap_data)
        formatted_output = format_output(ap_data)
        print(formatted_output)
        save_output_file(formatted_output, "ap_hook_output.json")

        print(f"[-] Command-line arguments: {sys.argv}")
        
        if not "Export World Data" in sys.argv:
            try:
                os.startfile("ap_hook_output.json")
            except Exception as e:
                print(f"[!] Could not open output file automatically: {e}")
        
        print("\n" + "="*70)
        
    except Exception as e:
        print(f"\n[!] Error: {e}")
        import traceback
        traceback.print_exc()
        print("\n[!] An error occurred. Please check the traceback above for details.")


if __name__ == "__main__":
    main()
