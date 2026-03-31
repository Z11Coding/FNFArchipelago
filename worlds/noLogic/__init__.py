# Copyright (c) 2024
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from typing import Dict, Set, List, ClassVar, Type, Optional, Tuple
from BaseClasses import Region, Item, Location, ItemClassification, MultiWorld
from worlds.AutoWorld import World, WebWorld
from worlds.LauncherComponents import Component, components, Type as ComponentType
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
# These allow us to generate items without knowing the multiworld size upfront
NOLOGIC_BASE_ID = 100_000
RESERVED_PROGRESSION_ITEMS = 500  # Enough for 500 parallel worlds
RESERVED_LOCATIONS = 10000  # One per Progression item + extras


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
            else:
                # Fallback to reserved name
                reserved_name = f"__RESERVED_PROG_{player_idx}__"
                item_id = NOLOGIC_BASE_ID + player_idx
                item_mapping[reserved_name] = item_id
    else:
        # Fallback to all reserved names if players folder doesn't exist
        for i in range(RESERVED_PROGRESSION_ITEMS):
            item_mapping[f"__RESERVED_PROG_{i}__"] = NOLOGIC_BASE_ID + i
    
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
        
        # Dynamically assign the logic removal method based on Respect Early Locations option
        if self.options.respect_early_locations:
            NoLogicWorld.stage_pre_fill = NoLogicWorld._remove_all_logic
            logger.info("No Logic: Logic removal will run at stage_pre_fill (respecting early locations).")
        else:
            NoLogicWorld.stage_connect_entrances = NoLogicWorld._remove_all_logic
            logger.info("No Logic: Logic removal will run at stage_connect_entrances (ignoring early locations).")
        
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
        
        - Local (0): Each progression item can ONLY be in its target player's locations
        - Non-Local (1): Each progression item CANNOT be in its target player's locations (must go elsewhere)
        - Anywhere (2): No restrictions, items can go anywhere
        
        Note: This setting is ignored if using the Universal Progression item (global mode).
        """
        if not self.progression_items:
            return
        
        # Skip locality enforcement if using global progression item
        if self.options.progression_item_type == 1:  # Global
            logger.info("No Logic: Global progression item active - skipping locality enforcement")
            return
        
        locality_option = self.options.progression_item_locality
        nologic_player = self.player
        
        if locality_option == 0:  # Local - items stay in their target world
            logger.info("No Logic: Enforcing LOCAL progression items (each item stays in its target world)")
            
            # For each progression item associated with a player, restrict it to that player's locations only
            for target_player, prog_item_name in self.progression_items.items():
                # Add rules to all locations that are NOT from the target player
                for location in self.multiworld.get_locations():
                    # Skip No Logic locations and target player's own locations
                    if location.player == nologic_player or location.player == target_player:
                        continue
                    
                    # Get the original item rule if one exists
                    original_rule = getattr(location, 'item_rule', None)
                    
                    # Create a closure to capture both the original rule, target player, and item name
                    def make_item_rule(orig_rule, target_p, item_name):
                        def item_rule(item):
                            # Block the target player's progression item from going here
                            if item.player == target_p and item.name == item_name:
                                return False
                            # If there was an original rule, respect it
                            if orig_rule is not None:
                                return orig_rule(item)
                            return True
                        return item_rule
                    
                    # Set the new item rule
                    location.item_rule = make_item_rule(original_rule, target_player, prog_item_name)
        
        elif locality_option == 1:  # Non-Local - items cannot be in their target world
            logger.info("No Logic: Enforcing NON-LOCAL progression items (items cannot be in their target world)")
            
            # For each progression item associated with a player, prevent it from being in that player's locations
            for target_player, prog_item_name in self.progression_items.items():
                # Add rules to the target player's locations to block their own progression item
                for location in self.multiworld.get_locations(target_player):
                    # Get the original item rule if one exists
                    original_rule = getattr(location, 'item_rule', None)
                    
                    # Create a closure to capture both the original rule and target player
                    def make_item_rule(orig_rule, target_p, item_name):
                        def item_rule(item):
                            # Block the target player's progression item from going to their own locations
                            if item.player == target_p and item.name == item_name:
                                return False
                            # If there was an original rule, respect it
                            if orig_rule is not None:
                                return orig_rule(item)
                            return True
                        return item_rule
                    
                    # Set the new item rule
                    location.item_rule = make_item_rule(original_rule, target_player, prog_item_name)
        
        elif locality_option == 2:  # Anywhere - no restrictions
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
        
        if self.progression_items:
            seen_names = set()
            for other_player, item_name in self.progression_items.items():
                if item_name not in seen_names:
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
                    seen_names.add(item_name)
                    logger.info(f"No Logic: Created progression item: {item_name} (ID: {item.code})")
        
        # Create filler to match base location count (progression locations will be added in post_fill)
        items_created = len(created_items)
        base_locations = [loc for loc in all_locations if loc.parent_region.name != "Progression"]
        needed_fillers = len(base_locations) - items_created
        
        for i in range(max(0, needed_fillers)):
            filler = self.create_item("Filler")
            self.multiworld.itempool.append(filler)

        logger.info(f"No Logic: Created {len(created_items)} progression items and {max(0, needed_fillers)} filler items.")

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
        
        entrance_count = 0
        location_count = 0
        
        # Remove all access rules from all entrances (if enabled)
        if remove_entrances:
            for region in multiworld.get_regions():
                for entrance in region.exits:
                    entrance.access_rule = lambda state: True
                    entrance_count += 1
            logger.info(f"No Logic: Removed {entrance_count} access rules from entrances.")
        else:
            logger.info("No Logic: Entrance logic kept intact (disabled via option).")
        
        # Remove all access rules from all locations
        for location in multiworld.get_locations():
            location.access_rule = lambda state: True
            location_count += 1
        
        logger.info(f"No Logic: Removed {location_count} access rules from locations.")

    @classmethod
    def stage_post_fill(cls, multiworld: MultiWorld) -> None:
        """After fill, create progression item copy locations, lock items to them, and enforce item locality."""
        # Find and process the No Logic world
        for player in multiworld.player_ids:
            if isinstance(multiworld.worlds[player], NoLogicWorld):
                no_logic_world: NoLogicWorld = multiworld.worlds[player]
                no_logic_world._create_progression_locations(multiworld)
                
                # Enforce item locality after locations are created
                # This ensures No Logic rules aren't overridden by other worlds
                other_worlds = [
                    p for p in multiworld.player_ids
                    if not isinstance(multiworld.worlds[p], NoLogicWorld)
                ]
                no_logic_world._enforce_item_locality(other_worlds)
    
    def _create_progression_locations(self, multiworld: MultiWorld) -> None:
        """Create progression item copy locations and lock items to them."""
        if not self.progression_items:
            return
        
        logger.info(f"No Logic (P{self.player}): Creating progression item copy locations...")
        
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
            if prog_item_name not in self.progression_item_ids_by_name:
                continue
            
            player_name = multiworld.player_name[other_player]
            target_world = multiworld.worlds[other_player]
            prog_item_id = self.progression_item_ids_by_name[prog_item_name]
            
            # Collect progression items from target world
            progression_items_to_lock = []
            for item in multiworld.itempool:
                if item.player != other_player:
                    continue
                if item.classification == ItemClassification.progression:
                    progression_items_to_lock.append(item)
                elif self.options.include_lesser_progression and item.classification in [
                    ItemClassification.progression_skip_balancing,
                    ItemClassification.progression_deprioritized,
                    ItemClassification.progression_deprioritized_skip_balancing
                ]:
                    progression_items_to_lock.append(item)
            
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
            logger.info("No Logic: No progression_item_ids_by_name found")
            return  # No progression items were created
        
        progression_item_ids = set(self.progression_item_ids_by_name.values())
        logger.info(f"No Logic: Tracking progression item IDs: {progression_item_ids}")
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
        return {
            "progression_items": self.progression_items,
            "claim_dict": getattr(self, 'nologic_claim_dict', {}),
            "item_id_to_player": self.progression_item_id_to_player,
            "player_location_mapping": getattr(self, 'nologic_player_location_mapping', {}),
            "player_name_mapping": getattr(self, 'nologic_player_name_mapping', {}),
            "include_lesser_progression": self.options.include_lesser_progression.value
        }

    def create_item(self, name: str) -> Item:
        """Create an item for the No Logic world."""
        if name == "Filler":
            return Item(name, ItemClassification.filler, self.item_name_to_id["Filler"], self.player)
        elif name.endswith("'s Progression"):
            # Per-world progression items are progression-classified so they can be used with ItemLinks
            return Item(name, ItemClassification.progression, None, self.player)
        elif name == "Universal Progression":
            # Global progression item with dedicated ID from mapping
            return Item(name, ItemClassification.progression, self.item_name_to_id["Universal Progression"], self.player)
        raise ValueError(f"Unknown item: {name}")

    def get_filler_item_name(self) -> str:
        """Return filler item name."""
        return "Filler"

