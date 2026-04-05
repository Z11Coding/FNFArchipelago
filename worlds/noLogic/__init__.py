# Copyright (c) 2024
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from collections.abc import Callable, Mapping, Sequence
from typing import Dict, Set, List, ClassVar, Type, Optional, Tuple, Any, Union, TypeVar, Generic, get_type_hints
import inspect
from BaseClasses import Region, Item, Location, ItemClassification, MultiWorld
from worlds.AutoWorld import World, WebWorld
from worlds.LauncherComponents import Component, components, Type as ComponentType
from worlds.generic.Rules import forbid_item
from .Options import *
import logging
import MultiServer
from Utils import parse_yaml
from pathlib import Path
import string
from collections import Counter

MultiServer.load_server_cert = None  # Ensure closure is cleared to avoid issues with dynamic logic changes

logger = logging.getLogger("NoLogic")

# Make NoLogicOptions accessible at module level for framework discovery
__all__ = ["NoLogicWorld", "NoLogicOptions"]

# Register NoLogic Client with the launcher
def launch_client(*args):
    from worlds.LauncherComponents import launch
    from .NoLogicClient import launch as NLMain
    launch(NLMain, name="No Logic Client", args=args)

components.append(Component("No Logic Client", func=launch_client, component_type=ComponentType.CLIENT, supports_uri=True, description="Collects progression items from other worlds when they are received."))

# Reserved ID ranges for No Logic world
NOLOGIC_BASE_ID = 100_000
RESERVED_PROGRESSION_ITEMS = 100_000  # Enough for most multiworlds... hopefully.
RESERVED_LOCATIONS = 100_000  # One per Progression item + extras


T = TypeVar('T')

# Type alias for valid return_as types (any Sequence or Mapping type)
ReturnAsType = Union[Type[list], Type[dict]]


def _is_mapping_type(tp: type) -> bool:
    """Check if a type is dict-like (Mapping)."""
    try:
        return issubclass(tp, Mapping)
    except TypeError:
        return False


def _is_sequence_type(tp: type) -> bool:
    """Check if a type is list-like (Sequence)."""
    try:
        return issubclass(tp, Sequence)
    except TypeError:
        return False

# Making this as a tool for later. Don't mind me.
class FuncStack(list, Generic[T]):
    """
    A generic stack to call multiple functions in sequence with type-constrained returns.
    
    Supports:
    - Configurable return collection (list, dict, or other Sequence/Mapping types) via return_as parameter
    - Automatic return type extraction from function annotations
    - Per-function type constraints (explicit or auto-detected)
    - Type validation with error raising on mismatch
    
    Examples:
        >>> stack = FuncStack(return_as=list)
        >>> stack.push(lambda: 42)
        >>> stack.push(lambda: "hello")
        >>> stack()  # Returns [42, "hello"]
        
        >>> def get_int() -> int: return 10
        >>> def get_str() -> str: return "test"
        >>> stack = FuncStack(return_as=dict, global_return_type=int)
        >>> stack.push(get_int)  # Auto-detected return type: int
        >>> stack.push(get_str, return_type=str)  # Override with explicit type
        >>> stack()  # Returns {"get_int": 10, "get_str": "test"}
        
        >>> stack = FuncStack(return_as=dict)
        >>> stack.push(get_int)  # Auto-detected: return type int from annotation
        >>> stack()
    """
    
    def __init__(
        self,
        return_as: ReturnAsType = list,
        global_return_type: Optional[type] = None
    ):
        """
        Initialize FuncStack with return collection configuration.
        
        Args:
            return_as: Collection type to use for returns - list (default), dict, or other Sequence/Mapping
            global_return_type: Optional type constraint applied to all functions unless overridden per-function
            
        Raises:
            TypeError: If return_as is not a Sequence or Mapping type
        """
        super().__init__()
        
        # Validate return_as type
        if not (_is_sequence_type(return_as) or _is_mapping_type(return_as)):
            raise TypeError(
                f"return_as must be a Sequence or Mapping type (list, dict, etc.), "
                f"got {return_as}"
            )
        
        self.return_as = return_as
        self.global_return_type = global_return_type
        self.func_type_constraints: Dict[Callable, Optional[type]] = {}
    
    def _extract_return_type(self, func: Callable) -> Optional[type]:
        """
        Extract return type annotation from a function.
        
        Args:
            func: The function to inspect
            
        Returns:
            The return type annotation if present and not NoneType, otherwise None
        """
        try:
            hints = get_type_hints(func)
            return_type = hints.get('return')
            
            # Return None if no annotation or annotation is NoneType
            if return_type is not None and return_type is not type(None):
                return return_type
            
        except Exception:
            # get_type_hints can fail for various reasons (forward refs, etc.)
            pass
        
        return None
    
    def push(self, func: Callable, return_type: Optional[type] = None) -> None:
        """
        Add a function to the stack with optional return type constraint.
        
        Automatically extracts return type from function annotations if not provided.
        
        Args:
            func: The function to add
            return_type: Optional type constraint for this function (overrides auto-detected type and global constraint)
        """
        self.append(func)
        
        # Use explicit return_type if provided, otherwise try to auto-detect
        if return_type is not None:
            self.func_type_constraints[func] = return_type
        else:
            auto_detected = self._extract_return_type(func)
            self.func_type_constraints[func] = auto_detected
    
    def pop(self) -> Optional[Callable]:
        """Remove and return the top function from the stack."""
        if self:
            func = super().pop()
            self.func_type_constraints.pop(func, None)
            return func
        return None
    
    def __call__(self, *args, **kwargs) -> Union[List[Any], Dict[str, Any]]:
        """
        Execute all functions in order and return results based on return_as type.
        
        Type constraints are validated if specified (auto-detected, per-function, or global).
        Raises TypeError if a function's return value doesn't match its constraint.
        
        Args:
            *args: Positional arguments passed to each function
            **kwargs: Keyword arguments passed to each function
            
        Returns:
            Sequence of return values if return_as is a Sequence type (list, tuple, etc.)
            Mapping of {function_name: return_value} if return_as is a Mapping type (dict, etc.)
            
        Raises:
            TypeError: If a function's return value doesn't match its type constraint
        """
        # Initialize result collection based on return_as type
        is_mapping = _is_mapping_type(self.return_as)
        results = {} if is_mapping else []
        
        for i, func in enumerate(self):
            result = func(*args, **kwargs)
            
            # Determine applicable type constraint (explicit > auto-detected > global)
            expected_type = self.func_type_constraints.get(func) or self.global_return_type
            
            # Validate type constraint if specified
            if expected_type and not isinstance(result, expected_type):
                func_name = getattr(func, '__name__', f'func_{i}')
                raise TypeError(
                    f"Function {func_name} returned {type(result).__name__}, "
                    f"expected {expected_type.__name__}"
                )
            
            # Collect result in specified format
            if is_mapping:
                func_name = getattr(func, '__name__', f'func_{i}')
                results[func_name] = result
            else:
                results.append(result)
        
        return results
    def as_generator(self, *args, **kwargs):
        """
        Execute all functions in order and yield results one by one.
        
        Type constraints are validated if specified (auto-detected, per-function, or global).
        Raises TypeError if a function's return value doesn't match its constraint.
        
        Args:
            *args: Positional arguments passed to each function
            **kwargs: Keyword arguments passed to each function
            
        Yields:
            Each function's return value in order
            
        Raises:
            TypeError: If a function's return value doesn't match its type constraint
        """
        for i, func in enumerate(self.copy()): # Use a copy of the list to allow modifications during iteration
            result = func(*args, **kwargs)
            
            # Determine applicable type constraint (explicit > auto-detected > global)
            expected_type = self.func_type_constraints.get(func) or self.global_return_type
            
            # Validate type constraint if specified
            if expected_type and not isinstance(result, expected_type):
                func_name = getattr(func, '__name__', f'func_{i}')
                raise TypeError(
                    f"Function {func_name} returned {type(result).__name__}, "
                    f"expected {expected_type.__name__}"
                )
            
            yield result
    
    def combine_to_single_function(self) -> Callable:
        """
        Combine all functions in the stack into a single callable that executes them in sequence.
        
        Creates a standalone function with no dependency on the FuncStack instance.
        The returned function is independent and can be used after the FuncStack is destroyed.
        
        Returns:
            A callable that executes all functions in order and returns results based on return_as configuration
        """
        # Capture all state needed for the standalone function
        functions_copy = list(self).copy()  # Copy of all functions
        constraints_copy = dict(self.func_type_constraints).copy()  # Copy of type constraints
        return_as_type = self.return_as.copy()  # Return collection type (list, dict, etc.)
        global_type = self.global_return_type  # Global type constraint
        
        def combined(*args, **kwargs) -> Union[List[Any], Dict[str, Any]]:
            """
            Standalone function that executes all captured functions in order.
            
            Type constraints are validated if specified.
            Raises TypeError if a function's return value doesn't match its constraint.
            
            Args:
                *args: Positional arguments passed to each function
                **kwargs: Keyword arguments passed to each function
                
            Returns:
                Sequence of return values if return_as is a Sequence type
                Mapping of {function_name: return_value} if return_as is a Mapping type
                
            Raises:
                TypeError: If a function's return value doesn't match its type constraint
            """
            is_mapping = _is_mapping_type(return_as_type)
            results = {} if is_mapping else []
            
            for i, func in enumerate(functions_copy):
                result = func(*args, **kwargs)
                
                # Determine applicable type constraint (explicit > auto-detected > global)
                expected_type = constraints_copy.get(func) or global_type
                
                # Validate type constraint if specified
                if expected_type and not isinstance(result, expected_type):
                    func_name = getattr(func, '__name__', f'func_{i}')
                    raise TypeError(
                        f"Function {func_name} returned {type(result).__name__}, "
                        f"expected {expected_type.__name__}"
                    )
                
                # Collect result in specified format
                if is_mapping:
                    func_name = getattr(func, '__name__', f'func_{i}')
                    results[func_name] = result
                else:
                    results.append(result)
            
            return results
        
        return combined


# Generic YAML Parser for reading player names
class GenericYAMLPlayer:
    """Generic YAML parser for extracting player name from any player YAML file."""
    
    @staticmethod
    def read_player_name(yaml_path: Optional[str]) -> Tuple[Optional[str], bool]:
        """
        Read player name from a YAML file, ignoring No Logic players.
        
        Args:
            yaml_path: Path to the YAML file
            
        Returns:
            Tuple of (player_name, success): Name extracted from YAML and success flag
                The name may contain {number} placeholders which will be resolved by build_item_name_to_id_with_yaml()
        """
        if not yaml_path:
            return None, False
        
        try:
            yaml_file = Path(yaml_path)
            if not yaml_file.exists():
                return None, False
            
            with open(yaml_file, 'r', encoding='utf-8-sig') as f:
                yaml_content = f.read()
            
            parsed_data = parse_yaml(yaml_content)
            
            if not isinstance(parsed_data, dict):
                return None, False
            
            # Skip if this is a No Logic player
            if parsed_data.get('game') == 'No Logic':
                return None, False
            
            for key in ['name']:
                if key in parsed_data and isinstance(parsed_data[key], str):
                    name = parsed_data[key].strip()
                    if name:
                        return name, True
            
            return None, False
        except Exception:
            return None, False


def build_item_name_to_id_with_yaml() -> Dict[str, int]:
    """
    Build item_name_to_id mapping by scanning player files for names.
    Resolves player names using Archipelago's name formatting syntax ({number}, {player}, etc).
    Also registers shard versions of progression items for use in shard mode.
    Dynamically assigns shard IDs to ensure no collisions.
    """
    item_mapping = {
        "Filler": NOLOGIC_BASE_ID + RESERVED_PROGRESSION_ITEMS,
        "Universal Progression": NOLOGIC_BASE_ID + RESERVED_PROGRESSION_ITEMS + 1,
    }
    
    # Try to read from players folder
    players_dir = Path("players")
    if players_dir.exists():
        yaml_files = list(players_dir.glob("*.yaml")) + list(players_dir.glob("*.yml"))
        
        # Read all player names from YAML files
        name_counter = Counter()
        for player_idx, yaml_file in enumerate(sorted(yaml_files)[:RESERVED_PROGRESSION_ITEMS]):
            player_id = player_idx + 1  # Player IDs start at 1
            player_name, success = GenericYAMLPlayer.read_player_name(str(yaml_file))
            
            if success and player_name:
                # Apply Archipelago's name formatting logic
                resolved_name = _resolve_player_name(player_name, player_id, name_counter)
                progression_name = f"{resolved_name}'s Progression"
                item_id = NOLOGIC_BASE_ID + player_idx
                item_mapping[progression_name] = item_id
                # Also register the shard version with next available ID
                shard_name = f"{progression_name} Shard"
                next_available_id = max(item_mapping.values()) + 1
                item_mapping[shard_name] = next_available_id
            else:
                # Fallback to reserved name
                reserved_name = f"__RESERVED_PROG_{player_idx}__"
                item_id = NOLOGIC_BASE_ID + player_idx
                item_mapping[reserved_name] = item_id
                # Also register the shard version with next available ID
                shard_name = f"{reserved_name}SHARD__"
                next_available_id = max(item_mapping.values()) + 1
                item_mapping[shard_name] = next_available_id
    else:
        # Fallback to all reserved names if players folder doesn't exist
        for i in range(RESERVED_PROGRESSION_ITEMS):
            reserved_name = f"__RESERVED_PROG_{i}__"
            item_mapping[reserved_name] = NOLOGIC_BASE_ID + i
            # Also register the shard version with next available ID
            shard_name = f"{reserved_name}SHARD__"
            next_available_id = max(item_mapping.values()) + 1
            item_mapping[shard_name] = next_available_id
    
    return item_mapping

# a copy to be as accurate as possible.
class SafeFormatter(string.Formatter):
    """Archipelago's SafeFormatter for handling name substitutions."""
    def get_value(self, key, args, kwargs):
        if isinstance(key, int):
            if key < len(args):
                return args[key]
            else:
                return "{" + str(key) + "}"
        else:
            return kwargs.get(key, "{" + key + "}")


def _resolve_player_name(name: str, player: int, name_counter: Counter) -> str:
    """
    Resolve Archipelago's name formatting syntax using the same logic as Generate.py's handle_name.
    
    Substitutes:
    - {number}: How many times this name has been used (1-based)
    - {NUMBER}: Same as {number}, but blank if 1
    - {player}: The player ID
    - {PLAYER}: Same as {player}, but blank if 1
    """
    name_counter[name.lower()] += 1
    number = name_counter[name.lower()]
    
    # Replace %number% and %player% syntax with {number} and {player}
    resolved = "%".join([x.replace("%number%", "{number}").replace("%player%", "{player}") 
                        for x in name.split("%%")])
    
    # Apply SafeFormatter with substitution values
    resolved = SafeFormatter().vformat(resolved, (), {
        "number": number,
        "NUMBER": (number if number > 1 else ''),
        "player": player,
        "PLAYER": (player if player > 1 else '')
    })
    
    return resolved.strip()

# Custom Exceptions
class NoLogicException(Exception):
    """Base exception for No Logic world errors."""
    pass


class MultipleNoLogicWorldsError(NoLogicException):
    """Raised when more than one No Logic world is detected in the multiworld."""
    pass


class NoOtherWorldsError(NoLogicException):
    """Raised when No Logic is the only world in the multiworld."""
    pass


class NoLogicWeb(WebWorld):
    theme = "grass"
    option_groups = no_logic_option_groups


class NoLogicItem(Item):
    target_player: Optional[int] = None  # Player ID this item is associated with (for progression items)


class NoLogicWorld(World):
    """
    No Logic - A world that removes all logic from the session,
    making every location in every world immediately accessible from the game start.
    
    Optionally provides per-world Progression items that can be linked to progression items
    from other worlds, granting immediate access to all content.
    """

    game = "No Logic"
    web = NoLogicWeb()
    options: NoLogicOptions
    options_dataclass: ClassVar[Type[PerGameCommonOptions]] = NoLogicOptions
    topology_present = False
    
    # Client-related settings
    required_client_version = (0, 5, 0)
    # Initialize item_name_to_id with proper player names from YAML files
    item_name_to_id = build_item_name_to_id_with_yaml()
    
    # Reserve location ID space for progression item locations
    location_name_to_id = {
        **{f"__RESERVED_LOC_{i}__": NOLOGIC_BASE_ID + RESERVED_PROGRESSION_ITEMS + 1 + i 
           for i in range(RESERVED_LOCATIONS)},
    }

    origin_region_name = "No Logic Region"

    def __init__(self, multiworld: MultiWorld, player: int):
        super().__init__(multiworld, player)
        self.progression_items: Dict[int, str] = {}  # {world_player_id: item_name}
        self.progression_locations: Dict[int, str] = {}  # {world_player_id: location_name}
        self.progression_region: Region = None  # Will be created in create_regions
        self.progression_item_hints: list = []  # Hints for progression items (created in stage_fill)
        self.progression_item_id_to_player: Dict[int, int] = {}  # Maps item_id to player_id
        self.progression_items_placed_worlds: Set[int] = set()  # Tracks which worlds have received a progression item
        self.progression_items_provided_by_worlds: Dict[int, Set[Tuple[Item, int]]] = {}  # Items MANUALLLY provided by each world as (Item, count) tuples.
    
    @staticmethod
    def _read_incompatibilities() -> Set[str]:
        """
        Read the incompatibilities.md file and return a set of incompatible game names.
        
        Returns:
            Set of game names that are incompatible with No Logic
        """
        try:
            incomp_file = Path(__file__).parent / "docs" / "incompatibilities.md"
            if not incomp_file.exists():
                return set()
            
            with open(incomp_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            incompatible_games = set()
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('- '):
                    game_name = line[2:].strip()
                    if game_name:
                        incompatible_games.add(game_name)
            
            return incompatible_games
        except Exception as e:
            logger.warning(f"No Logic: Could not read incompatibilities file: {e}")
            return set()
    
    def create_item_copy(self, item: Item) -> Item:
        """Creates an exact copy of an item, used for creating progression item copies.
        This will not only copy every field, but also the type, in case of a subclass with extra information.
        """
        item_copy = type(item)(item.name, item.classification)
        # Grab all attributes first.
        for attr, value in vars(item).items():
            setattr(item_copy, attr, value)
        return item_copy
        

    def generate_early(self) -> None:
        """
        Scan the multiworld to identify all other worlds and prepare progression items.
        This runs before create_items, so we can set up items for all other players.
        Also handles item locality enforcement via local_items/non_local_items.
        """
        # Check for multiple No Logic worlds
        no_logic_count = sum(1 for player in self.multiworld.player_ids 
                             if isinstance(self.multiworld.worlds[player], NoLogicWorld))
        if no_logic_count > 1:
            raise MultipleNoLogicWorldsError(
                f"Found {no_logic_count} No Logic worlds. Only one No Logic world is allowed per multiworld session."
            )
        
        # Identify all non-No-Logic worlds
        other_worlds = [
            player for player in self.multiworld.player_ids
            if not isinstance(self.multiworld.worlds[player], NoLogicWorld)
        ]
        
        # Check if there are any other worlds besides No Logic
        if not other_worlds:
            raise NoOtherWorldsError(
                "No Logic world requires at least one other world in the multiworld. "
                "No Logic cannot be used alone."
            )
        
        # Warn the host and ask for confirmation
        world_names = [self.multiworld.player_name[p] for p in other_worlds]
        logger.warning("=" * 60)
        logger.warning("WARNING: No Logic Mode has been activated!")
        logger.warning("All access rules will be removed from ALL worlds.")
        logger.warning(f"Affected worlds: {', '.join(world_names)}")
        logger.warning(f"Culprit: {self.player_name}")
        logger.warning("=" * 60)
        
        response: str
        import sys
        if "--allow-no-logic" in sys.argv:
            logger.warning("No Logic: --allow-no-logic flag detected, proceeding without confirmation.")
            response = "y"
        else:
            try:
                response = input("No Logic Mode is active. All logic will be removed from the multiworld. Proceed? (y/n): ").strip().lower()
            except EOFError:
                raise NoLogicException("No Logic Mode requires confirmation from the host. Use --allow-no-logic to skip confirmation.")
        if response != "y":
            raise NoLogicException("Generation cancelled by host. No Logic Mode was not confirmed.")

        # Check for incompatible games
        incompatible_games = self._read_incompatibilities()
        if incompatible_games:
            incompatible_in_multiworld = []
            for player in other_worlds:
                world = self.multiworld.worlds[player]
                if world.game in incompatible_games:
                    incompatible_in_multiworld.append(f"{world.game} (P{player})")
            
            if incompatible_in_multiworld:
                logger.warning("=" * 60)
                logger.warning("WARNING: Incompatible worlds detected with No Logic!")
                logger.warning(f"Incompatible: {', '.join(incompatible_in_multiworld)}")
                logger.warning("This combination may cause generation or bugs when hosting.")
                logger.warning("=" * 60)
                response = input("Would you like to proceed anyway? (y/n): ").strip().lower()
                if response != "y":
                    raise NoLogicException("Generation cancelled by host due to incompatible worlds.")

        for worlds in self.multiworld.worlds.values():
            if not isinstance(worlds, NoLogicWorld):
                # Check if a world has a nologic_exemptions function and if it doesn't, create a dummy one that returns an empty set to avoid issues with logic removal.
                if not hasattr(worlds, "nologic_exemptions"):
                    setattr(worlds, "nologic_exemptions", lambda: set())
        
        # Dynamically assign the pre_fill stage based on Respect Early Locations option
        if self.options.respect_early_locations:
            # If respecting early locations, run both removal AND locality enforcement at pre_fill
            def combined_pre_fill(multiworld: MultiWorld):
                NoLogicWorld._remove_all_logic(multiworld)
                # Enforce locality immediately after removal
                for player in multiworld.player_ids:
                    if isinstance(multiworld.worlds[player], NoLogicWorld):
                        no_logic_world:NoLogicWorld = multiworld.worlds[player]
                        other_worlds = [
                            p for p in multiworld.player_ids
                            if not isinstance(multiworld.worlds[p], NoLogicWorld)
                        ]
                        no_logic_world._enforce_item_locality(other_worlds)
            
            NoLogicWorld.stage_pre_fill = combined_pre_fill
            logger.info("No Logic: Logic removal and locality enforcement at stage_pre_fill (respecting early locations).")
        else:
            # Otherwise, just remove logic at pre_fill and enforce locality at pre_fill by itself.
            NoLogicWorld.stage_connect_entrances = NoLogicWorld._remove_all_logic
            def locality(multiworld: MultiWorld):
                for player in multiworld.player_ids:
                        if isinstance(multiworld.worlds[player], NoLogicWorld):
                            no_logic_world:NoLogicWorld = multiworld.worlds[player]
                            other_worlds = [
                                p for p in multiworld.player_ids
                                if not isinstance(multiworld.worlds[p], NoLogicWorld)
                            ]
                            no_logic_world._enforce_item_locality(other_worlds)
            NoLogicWorld.stage_pre_fill = locality
            logger.info("No Logic: Logic removal at stage_connect_entances (not respecting early locations).")
        
        if not self.options.add_progression_item:
            logger.info("No Logic: Progression items disabled via options")
            return
        
        logger.info("No Logic: Scanning multiworld for progression items...")
        logger.info(f"No Logic: Found {len(other_worlds)} worlds to create progression items for: {
            [self.multiworld.player_name[p] for p in other_worlds]
        }")
        
        # Create progression item names based on distribution type
        if self.options.progression_item_type == 0:  # Per-world
            for other_player in other_worlds:
                player_name = self.multiworld.player_name[other_player]
                item_name = f"{player_name}'s Progression"
                self.progression_items[other_player] = item_name
                self.progression_locations[other_player] = f"Unlock {item_name}"
                logger.debug(f"No Logic: Prepared {item_name}")
        else:  # Global
            # All worlds share one global progression item
            global_item_name = "Universal Progression"
            for other_player in other_worlds:
                self.progression_items[other_player] = global_item_name
            # Only create one location for the global item
            self.progression_locations[other_worlds[0]] = "Unlock Universal Progression"
            logger.info(f"No Logic: Using global progression item: {global_item_name}")

    def _enforce_item_locality(self, other_worlds: List[int]) -> None:
        """
        Enforce item locality for progression items based on the locality option.
        
        - Local (0): Each progression item can ONLY be in its target player's locations (or No Logic)
        - Non-Local (1): Each progression item CANNOT be in its target player's locations (must go elsewhere)
        - One Per World (2): Non-local variant where only ONE progression item total is allowed per world
        - Anywhere (3): No restrictions, items can go anywhere
        
        Note: This setting is ignored if using the Universal Progression item (global mode).

        TODO: Improve on by making it ID based, instead of name based, and make work for when "Progression Shards" get added.
        """
        if not self.progression_items:
            return
        
        # Skip locality enforcement if using global progression item
        if self.options.progression_item_type == 1:  # Global
            logger.info("No Logic: Global progression item active - skipping locality enforcement")
            return
        
        locality_option = self.options.progression_item_locality
        nologic_player = self.player
        
        if locality_option == 0:  # Local - items don't cross between other worlds
            logger.info("No Logic: Enforcing LOCAL progression items (items stay within their world, not crossing between other players)")
            
            # Build a map of progression item names to their target players
            # This is the "owner" of each progression item
            item_to_owner = {name: player for player, name in self.progression_items.items()}
            
            # Iterate through all locations and apply custom item rules
            for location in self.multiworld.get_locations():
                # Skip No Logic's own locations - they can accept any progression item
                if location.player == nologic_player:
                    continue
                
                # Check if this location's player has their own progression item
                allowed_item = self.progression_items.get(location.player)
                
                if allowed_item:
                    # This location's player has a progression item
                    # At this location, allow:
                    # 1. This player's own progression item
                    # 2. Any non-progression items
                    # Block all OTHER progression items (they can't cross to other worlds)
                    original_rule = location.item_rule
                    location.item_rule = lambda i, allow_item=allowed_item, item_map=item_to_owner, orig_rule=original_rule: (
                        orig_rule(i) and (i.name == allow_item or i.name not in item_map)
                    )
        
        elif locality_option == 1:  # Non-Local - items cannot be in their target world
            logger.info("No Logic: Enforcing NON-LOCAL progression items (items cannot be in their target world)")
            
            # For each progression item associated with a player, prevent it from being in that player's locations
            for target_player, prog_item_name in self.progression_items.items():
                # Block this item from the target player's own locations
                for location in self.multiworld.get_locations(target_player):
                    forbid_item(location, prog_item_name, target_player)
        
        elif locality_option == 2:  # One Per World - ensure only one progression item per world total
            logger.info("No Logic: Enforcing ONE progression item per world (non-local variant)")
            
            # Build a map of progression item names
            progression_item_names = set(self.progression_items.values())
            nologic_player_id = self.player
            
            # Apply rules to all non-No Logic locations
            for location in self.multiworld.get_locations():
                # Skip No Logic's own locations - they can accept multiple progression items
                if location.player == nologic_player_id:
                    continue
                
                original_rule = location.item_rule
                world_player = location.player
                
                def make_one_per_world_rule(orig_rule, world, prog_names, placed_worlds):
                    """
                    Create a rule that allows only one progression item per world.
                    Tracks which worlds have received items in the placed_worlds set.
                    """
                    def rule(item: Item, orig_rule=orig_rule, world=world, prog_names=prog_names, placed_worlds=placed_worlds) -> bool:
                        # Check original rule first
                        if not orig_rule(item):
                            return False
                        
                        # Allow non-progression items
                        if item.name not in prog_names:
                            return True
                        
                        # This is a progression item
                        # If world already has one, reject
                        if world in placed_worlds:
                            return False
                        
                        # World doesn't have one yet, accept and track it
                        placed_worlds.add(world)
                        logger.info(f"No Logic: Progression item {item.name} placed in world P{world}, marked as received")
                        return True
                    
                    return rule
                
                location.item_rule = make_one_per_world_rule(original_rule, world_player, progression_item_names, self.progression_items_placed_worlds)
        
        elif locality_option == 3:  # Anywhere - no restrictions
            logger.info("No Logic: Progression items can go ANYWHERE (no restrictions)")
            # No item rules needed - items are unrestricted by default

    def create_regions(self) -> None:
        """Create the No Logic regions (main and progression)."""
        region = Region("No Logic Region", self.player, self.multiworld)
        self.multiworld.regions += [region]
        
        # Create progression region for items (will be populated in post_fill)
        self.progression_region = Region("Progression", self.player, self.multiworld)
        self.multiworld.regions += [self.progression_region]
        
        # Create entrance between regions
        entrance = region.add_exits(["Progression"])[0]
        entrance.connect(self.progression_region)
        
        # Add a placeholder location if no other content
        location = Location(self.player, "No Logic Check", NOLOGIC_BASE_ID + RESERVED_PROGRESSION_ITEMS, region)
        region.locations.append(location)

    @classmethod
    def stage_create_items(cls, multiworld:MultiWorld) -> None:
        """Get items from other worlds, that have decided they wanted progression items to do more."""
        self: NoLogicWorld = [multiworld.worlds[player] for player in multiworld.player_ids if isinstance(multiworld.worlds[player], NoLogicWorld)][0]
        for player in self.multiworld.player_ids:
            if player == self.player:
                continue
            
            world = self.multiworld.worlds[player]
            if hasattr(world, "nologic_progression_hook") and callable(getattr(world, "nologic_progression_hook")):
                provided_items = world.nologic_progression_hook(self.multiworld)
                if provided_items:
                    items_to_add: Set[Tuple[Item, int]] = set()
                    
                    # Case 1: Single tuple (Item, int)
                    if isinstance(provided_items, tuple) and len(provided_items) == 2 and isinstance(provided_items[0], Item) and isinstance(provided_items[1], int):
                        items_to_add.add(provided_items)
                        logger.info(f"No Logic: World P{player} provided 1 progression item (with count {provided_items[1]}) for No Logic")
                    
                    # Case 2: Single Item
                    elif isinstance(provided_items, Item):
                        items_to_add.add((provided_items, 1))
                        logger.info(f"No Logic: World P{player} provided 1 progression item for No Logic")
                    
                    # Case 3: List or iterable
                    elif isinstance(provided_items, (list, tuple)):
                        for item in provided_items:
                            # Case 3a: List of Items
                            if isinstance(item, Item):
                                items_to_add.add((item, 1))
                            # Case 3b: List of tuples (Item, int)
                            elif isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], Item) and isinstance(item[1], int):
                                items_to_add.add(item)
                        if items_to_add:
                            logger.info(f"No Logic: World P{player} provided {len(items_to_add)} progression items for No Logic")
                    else:
                        logger.error(f"World of P{player} returned invalid type from nologic_progression_hook: {type(provided_items)}. Expected Item, tuple(Item, int), or list of those.")
                        raise NoLogicException(f"Invalid return type from nologic_progression_hook in world P{player}. Expected Item, tuple(Item, int), or list of those, but instead got {type(provided_items)}.")
                    
                    if items_to_add:
                        self.progression_items_provided_by_worlds[player] = items_to_add
                    

    def create_items(self) -> None:
        """Create progression items for No Logic."""
        created_items = []
        all_locations = self.multiworld.get_locations(self.player)

        def get_unused_item_id():
            # Generate unique item IDs for progression items (skip reserved IDs from mapping)
            filler_id = self.item_name_to_id["Filler"]
            universal_prog_id = self.item_name_to_id["Universal Progression"]
            used_ids = set(item.code for item in self.multiworld.itempool)
            for i in range(RESERVED_PROGRESSION_ITEMS):
                candidate_id = NOLOGIC_BASE_ID + i
                if candidate_id not in used_ids and candidate_id != filler_id and candidate_id != universal_prog_id:
                    return candidate_id
            raise NoLogicException("Exceeded reserved item ID space for No Logic world.")
        
        # Create progression items from NoLogic
        self.progression_item_ids_by_name: Dict[str, int] = {}  # {item_name: item_id}
        
        # Check if shard mode is enabled
        progression_mode = self.options.progression_item_mode.value
        is_shard_mode = progression_mode in [1, 2]  # 1=Shards-All, 2=Shards-Percentage
        shard_count = self.options.progression_shard_count.value if is_shard_mode else 0
        
        # Store mode info for slot_data
        self.progression_mode = progression_mode
        self.progression_shard_count = shard_count
        
        if self.progression_items:
            seen_names = set()
            for other_player, item_name in self.progression_items.items():
                if item_name not in seen_names:
                    if is_shard_mode:
                        # Shard mode: create multiple shard items with separate ID
                        shard_item_name = f"{item_name} Shard"
                        
                        # Get ID from pre-registered mapping
                        if shard_item_name not in self.item_name_to_id:
                            raise NoLogicException(f"Shard item '{shard_item_name}' not found in item_name_to_id mapping. An error must've occurred while reading yamls.")
                        
                        shard_id = self.item_name_to_id[shard_item_name]
                        
                        # Update progression_items to reference the shard item
                        self.progression_items[other_player] = shard_item_name
                        
                        # Create shard copies with the mapped ID
                        for i in range(shard_count):
                            shard_item = NoLogicItem(shard_item_name, ItemClassification.progression, shard_id, self.player)
                            self.multiworld.itempool.append(shard_item)
                            created_items.append(shard_item_name)
                        
                        self.progression_item_ids_by_name[shard_item_name] = shard_id
                        logger.info(f"No Logic: Created {shard_count} shard items '{shard_item_name}' (ID: {shard_id}, Mode: {'All' if progression_mode == 1 else 'Percentage'})")
                    else:
                        # Normal mode: create single progression item (existing behavior)
                        item = self.create_item(item_name)
                        
                        # Check if item name already exists in item_name_to_id mapping
                        if item_name in self.item_name_to_id:
                            item.code = self.item_name_to_id[item_name]
                        else:
                            # Use an unused ID
                            item.code = get_unused_item_id()
                        
                        item.player = self.player
                        self.multiworld.itempool.append(item)
                        self.progression_item_ids_by_name[item_name] = item.code
                        created_items.append(item_name)
                        logger.info(f"No Logic: Created progression item: {item_name} (ID: {item.code})")
                    
                    seen_names.add(item_name)
        
        # Create filler to match base location count (progression locations will be added in post_fill)
        items_created = len(created_items)
        base_locations = [loc for loc in all_locations if loc.parent_region.name != "Progression"]
        needed_fillers = len(base_locations) - items_created
        
        for i in range(max(0, needed_fillers)):
            filler = self.create_item("Filler")
            self.multiworld.itempool.append(filler)

        logger.info(f"No Logic: Created {len(created_items)} progression items and {max(0, needed_fillers)} filler items. Shard mode: {is_shard_mode}")

    # def stage_create_items(self) -> None:
    #     items_to_link:dict[int, list[str]] = {}
    #     for player, item in self.progression_items.items():
    #         # Link items that are progression items to their respective worlds' progression items
    #         if item in self.multiworld.itempool:
    #             for item in self.multiworld.itempool:
    #                 if item.player == player and item.classification in [ItemClassification.progression, ItemClassification.progression_skip_balancing, ItemClassification.progression_deprioritized, ItemClassification.progression_deprioritized_skip_balancing]:
    #                     logger.debug(f"No Logic: Linked {item.name} (P{self.player}) to {item.name} (P{player})")
    #                     items_to_link[player].append(item.name)
    #         for player, item_names in items_to_link.items():
    #             self.options.item_links.value.append({"name": self.progression_items[player], "item_pool": item_names, "link_replacement": False})
                    
    def set_rules(self) -> None:
        """Minimal rules setup - stage_pre_fill will handle delogicking."""
        pass

    @classmethod
    def _remove_all_logic(cls, multiworld: MultiWorld) -> None:
        """
        Remove all logic from all worlds when No Logic is present.
        Dynamically assigned as stage_pre_fill or stage_connect_entrances
        based on the Respect Early Locations option.
        """
        # Check if No Logic world is actually in the multiworld
        has_no_logic = any(
            isinstance(multiworld.worlds[player], NoLogicWorld)
            for player in multiworld.player_ids
        )
        
        if not has_no_logic:
            return
        
        # Find the No Logic player to read options
        no_logic_player = None
        for player in multiworld.player_ids:
            if isinstance(multiworld.worlds[player], NoLogicWorld):
                no_logic_player = player
                break
        
        no_logic_world: NoLogicWorld = multiworld.worlds[no_logic_player]
        remove_entrances = bool(no_logic_world.options.remove_entrance_logic.value)
        
        logger.info("No Logic: Removing access rules from the multiworld...")
        from BaseClasses import Location, Entrance
        from worlds import AutoWorld

        excemptions: Set[Location | Entrance] = set()

        for world in multiworld.worlds.values():
            if not isinstance(world, NoLogicWorld):
                logger.info(f"No Logic: Asking World for exceptions to logic removal for {world.player_name}...")
                excemptions.update(AutoWorld.call_single(multiworld, "nologic_exemptions", player=world.player))
                
        
        entrance_count = 0
        location_count = 0
        
        # Remove all access rules from all entrances (if enabled)
        if remove_entrances:
            for region in multiworld.get_regions():
                for entrance in set(region.exits).union(region.entrances) - excemptions:
                    entrance.access_rule = lambda state: True
                    entrance_count += 1
            logger.info(f"No Logic: Removed {entrance_count} access rules from entrances.")
        else:
            logger.info("No Logic: Entrance logic kept intact (disabled via option).")
        
        # Remove all access rules from all locations
        for location in set(multiworld.get_locations()) - excemptions:
            location.access_rule = lambda state: True
            location_count += 1
        
        logger.info(f"No Logic: Removed {location_count} access rules from locations.")
        
        # # Enforce item locality after removing access rules
        # other_worlds = [
        #     p for p in multiworld.player_ids
        #     if not isinstance(multiworld.worlds[p], NoLogicWorld)
        # ]
        # no_logic_world._enforce_item_locality(other_worlds)


    @classmethod
    def stage_post_fill(cls, multiworld: MultiWorld) -> None:
        """After fill, create progression item copy locations and lock items to them."""
        # Find and process the No Logic world
        for player in multiworld.player_ids:
            if isinstance(multiworld.worlds[player], NoLogicWorld):
                no_logic_world: NoLogicWorld = multiworld.worlds[player]
                no_logic_world._create_progression_locations(multiworld)
    
    def _create_progression_locations(self, multiworld: MultiWorld) -> None:
        """Create progression item copy locations and lock items to them."""
        if not self.progression_items:
            logger.warning("No Logic: No progression items defined, skipping location creation")
            return
        
        logger.info(f"No Logic (P{self.player}): Creating progression item copy locations...")
        logger.info(f"No Logic: progression_item_ids_by_name = {self.progression_item_ids_by_name}")
        logger.info(f"No Logic: progression_items = {self.progression_items}")
        
        def get_unused_location_id():
            used_ids = set(loc.address for loc in multiworld.get_locations())
            for i in range(RESERVED_LOCATIONS):
                candidate_id = NOLOGIC_BASE_ID + RESERVED_PROGRESSION_ITEMS + 1 + i
                if candidate_id not in used_ids:
                    return candidate_id
            raise NoLogicException("Exceeded reserved location ID space for No Logic world.")
        
        # Store location tracking for slot_data
        claim_dict: Dict[int, List[int]] = {}
        player_location_mapping: Dict[int, Dict[str, List[int]]] = {}
        player_name_mapping: Dict[str, List[int]] = {}
        
        # Create locations for progression item copies
        for other_player, prog_item_name in self.progression_items.items():
            # prog_item_name is already the correct name (either base or shard, depending on mode)
            if prog_item_name not in self.progression_item_ids_by_name:
                logger.warning(f"No Logic: Item '{prog_item_name}' not found in progression_item_ids_by_name, skipping")
                continue
            
            logger.info(f"No Logic: Creating locations for {prog_item_name} (Player {other_player})")
            
            player_name = multiworld.player_name[other_player]
            target_world = multiworld.worlds[other_player]
            prog_item_id = self.progression_item_ids_by_name[prog_item_name]

            if hasattr(target_world, "nologic_progression_hook") and getattr(target_world, "nologic_progression_override", False):
                logger.info(f"No Logic: World P{other_player} has nologic_progression_override, skipping automatic item collection for location creation")
                continue
            
            # Collect progression items from target world
            progression_items_to_lock: List[Item] = []
            for item in multiworld.itempool:
                if item.player != other_player:
                    continue
                if item.classification == ItemClassification.progression or \
                (self.options.include_unusual_progression_items and ItemClassification.progression in item.classification) or \
                (self.options.include_useful_progression_items and item.classification == (ItemClassification.progression | ItemClassification.useful)):
                    progression_items_to_lock.append(item)
                elif self.options.include_lesser_progression and item.classification in [
                    ItemClassification.progression_skip_balancing,
                    ItemClassification.progression_deprioritized,
                    ItemClassification.progression_deprioritized_skip_balancing
                ]:
                    progression_items_to_lock.append(item)

            for item, count in self.progression_items_provided_by_worlds.get(other_player, []):
                for _ in range(count):
                    progression_items_to_lock.append(self.create_item_copy(item))
            
            # Create location for each progression item copy and lock it
            location_ids = []
            item_name_counts: Dict[str, int] = {}  # Track count of each item name to differentiate duplicates
            for prog_item in progression_items_to_lock:
                # Track duplicate item names
                if prog_item.name not in item_name_counts:
                    item_name_counts[prog_item.name] = 0
                else:
                    item_name_counts[prog_item.name] += 1
                
                # Create unique location name for duplicates
                loc_name = f"Copy of {prog_item.name} (from {player_name})"
                if item_name_counts[prog_item.name] > 0:
                    loc_name += f" #{item_name_counts[prog_item.name] + 1}"
                
                location = Location(self.player, loc_name, get_unused_location_id(), self.progression_region)
                self.progression_region.locations.append(location)
                self.options.exclude_locations.value.add(loc_name)
                location_ids.append(location.address)
                
                # Create and lock a copy of the item
                item_copy = target_world.create_item(prog_item.name)
                item_copy.classification = prog_item.classification
                location.place_locked_item(item_copy)
                logger.debug(f"No Logic: Locked {prog_item.name} into {location.name}")
            
            # In global mode, multiple players share the same item ID, so append instead of replace
            if prog_item_id in claim_dict:
                claim_dict[prog_item_id].extend(location_ids)
                logger.info(f"No Logic: Appended {len(location_ids)} locations to existing item ID {prog_item_id} (global mode)")
            else:
                claim_dict[prog_item_id] = location_ids
            
            # Track which player this item_id belongs to
            self.progression_item_id_to_player[prog_item_id] = other_player
            
            # Track locations by player ID and name
            if other_player not in player_location_mapping:
                player_location_mapping[other_player] = {}
            player_location_mapping[other_player][prog_item_name] = location_ids
            player_name_mapping[player_name] = location_ids
        
        # Store mappings on self for slot_data
        self.nologic_claim_dict = claim_dict
        self.nologic_player_location_mapping = player_location_mapping
        self.nologic_player_name_mapping = player_name_mapping
        
        # Shuffle claim_dict for percentage mode NOW (before threaded output)
        if hasattr(self, 'progression_mode') and self.progression_mode == 2:  # 2 = Shards - Percentage
            shuffled_claim_dict = {}
            for item_id in sorted(claim_dict.keys()):
                # Create a shuffled copy of the item list for this progression item
                item_list = claim_dict[item_id].copy()
                self.multiworld.random.shuffle(item_list)
                shuffled_claim_dict[item_id] = item_list
            self.nologic_claim_dict = shuffled_claim_dict
        
        logger.info(f"No Logic: Created {len(claim_dict)} progression item copy groups")
    
    def modify_multidata(self, multidata: dict) -> None:
        """Inject progression item hints into the multidata as precollected hints."""
        if not self.options.auto_hint_progression_items:
            logger.info("No Logic: Auto-hint progression items disabled")
            return
        
        logger.info("No Logic: Adding auto-hints for progression items to multidata...")
        from NetUtils import Hint, HintStatus
        
        # Get reference to precollected_hints from multidata
        precollected_hints: dict[int, set[Hint]] = multidata.get("precollected_hints", {})
        logger.info(f"No Logic: precollected_hints exists: {bool(precollected_hints)}")
        
        # Build set of progression item IDs we're tracking
        if not hasattr(self, 'progression_item_ids_by_name'):
            logger.warning("No Logic: No progression_item_ids_by_name found, cannot add hints")
            return  # No progression items were created
        
        progression_item_ids = set(self.progression_item_ids_by_name.values())
        logger.info(f"No Logic: Looking for these progression item IDs: {progression_item_ids}")
        logger.info(f"No Logic: Item ID to player mapping: {self.progression_item_id_to_player}")
        
        # Find where each progression item has been filled into the multiworld
        hints_added = 0
        for location in self.multiworld.get_filled_locations():
            if not location.item or not isinstance(location.address, int):
                continue
            
            # Check if this location contains one of our progression items
            if location.item.code not in progression_item_ids:
                continue
            
            logger.info(f"No Logic: Found progression item {location.item.name} (ID: {location.item.code}) at {location.name} (P{location.player})")
            
            # Look up target player directly from the mapping
            target_player = self.progression_item_id_to_player.get(location.item.code)
            if not target_player:
                logger.warning(f"No Logic: Could not find target player for item ID {location.item.code}")
                continue
            
            logger.info(f"No Logic: Target player is {target_player}")
            
            # Debug: Log item details before creating hint
            logger.info(f"No Logic: Creating hint with - item_player: {location.item.player}, item_name: {location.item.name}, item_code: {location.item.code}, item_flags: {location.item.flags}")
            
            # The item code should be the progression item ID, not the original item code
            progression_item_code = location.item.code
            logger.info(f"No Logic: Using progression item code: {progression_item_code}")
            
            # Create hint: point to where this progression item was filled in the multiworld
            # receiving_player: No Logic receives the progression item
            # finding_player: target_player sees the hint about where their item is
            hint = Hint(
                receiving_player=self.player,
                finding_player=location.player,
                location=location.address,
                item=progression_item_code,
                found=False,
                entrance="",
                item_flags=0,
                status=HintStatus.HINT_PRIORITY
            )
            
            # Add hint for the target player (finding player equivalent)
            if target_player in self.multiworld.groups:
                # In a group - add to all group members
                for group_member in self.multiworld.groups[target_player]["players"]:
                    if group_member not in precollected_hints:
                        precollected_hints[group_member] = set()
                    precollected_hints[group_member].add(hint)
            else:
                # Standalone - add to the player directly
                if target_player not in precollected_hints:
                    precollected_hints[target_player] = set()
                precollected_hints[target_player].add(hint)
            
            # Add hint for No Logic world (receiving player equivalent)
            if self.player in self.multiworld.groups:
                # In a group - add to all group members
                for group_member in self.multiworld.groups[self.player]["players"]:
                    if group_member not in precollected_hints:
                        precollected_hints[group_member] = set()
                    precollected_hints[group_member].add(hint)
            else:
                # Standalone - add to the player directly
                if self.player not in precollected_hints:
                    precollected_hints[self.player] = set()
                precollected_hints[self.player].add(hint)
            
            hints_added += 1
            logger.info(f"No Logic: Added hint #{hints_added}: {location.item.name} at {location.name} (P{location.player})")
        
        # Update multidata with the modified hints
        multidata["precollected_hints"] = precollected_hints
        logger.info(f"No Logic: Added {hints_added} progression item hints to precollected hints")
    
    def fill_slot_data(self) -> dict:
        """Return slot data for the client."""
        # Get the claim dict (already shuffled if in percentage mode during _create_progression_locations)
        claim_dict = getattr(self, 'nologic_claim_dict', {})
        
        slot_data = {
            "progression_items": self.progression_items,
            "claim_dict": claim_dict,
            "item_id_to_player": self.progression_item_id_to_player,
            "player_location_mapping": getattr(self, 'nologic_player_location_mapping', {}),
            "player_name_mapping": getattr(self, 'nologic_player_name_mapping', {}),
            "include_lesser_progression": self.options.include_lesser_progression.value,
            "progression_mode": getattr(self, 'progression_mode', 0),  # 0=Normal, 1=Shards-All, 2=Shards-Percentage
            "shard_count": getattr(self, 'progression_shard_count', 0),  # Number of shards (only relevant if progression_mode > 0)
            "progression_item_type": self.options.progression_item_type.value,  # 0=Per-world, 1=Global
        }
        
        return slot_data

    def create_item(self, name: str) -> Item:
        """Create an item for the No Logic world."""
        if name == "Filler":
            return Item(name, ItemClassification.filler, self.item_name_to_id["Filler"], self.player)
        elif name.endswith("'s Progression"):
            # Per-world progression items are progression-classified so they can be used with ItemLinks
            return NoLogicItem(name, ItemClassification.progression, None, self.player)
        elif name == "Universal Progression":
            # Global progression item with dedicated ID from mapping
            return NoLogicItem(name, ItemClassification.progression, self.item_name_to_id["Universal Progression"], self.player)
        raise ValueError(f"Unknown item: {name}")

    def get_filler_item_name(self) -> str:
        """Return filler item name."""
        return "Filler"

