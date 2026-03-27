# Copyright (c) 2024
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from typing import Dict, Set, List, ClassVar, Type
from BaseClasses import Region, Item, Location, ItemClassification, MultiWorld
from worlds.AutoWorld import World, WebWorld
from .Options import *
import logging

logger = logging.getLogger("NoLogic")

# Make NoLogicOptions accessible at module level for framework discovery
__all__ = ["NoLogicWorld", "NoLogicOptions"]

# Reserved ID ranges for No Logic world
# These allow us to generate items without knowing the multiworld size upfront
NOLOGIC_BASE_ID = 100_000
RESERVED_PROGRESSION_ITEMS = 500  # Enough for 500 parallel worlds
RESERVED_LOCATIONS = 1000  # One per Progression item + extras


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
    
    # Reserve item ID space for progression items (one per possible world)
    # Actual items will be created dynamically based on multiworld composition
    item_name_to_id = {
        **{f"__RESERVED_PROG_{i}__": NOLOGIC_BASE_ID + i for i in range(RESERVED_PROGRESSION_ITEMS)},
        "Filler": NOLOGIC_BASE_ID + RESERVED_PROGRESSION_ITEMS,
    }
    
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
        
        # Handle item locality enforcement
        self._enforce_item_locality(other_worlds)

    def _enforce_item_locality(self, other_worlds: List[int]) -> None:
        """
        Enforce item locality for progression items based on the locality option.
        
        - Local (0): Items can ONLY go to their target world (added to target's local_items)
        - Non-local (1): Items can go anywhere (no restrictions)
        """
        if not self.progression_items:
            return
        
        locality_option = self.options.progression_item_locality
        
        if locality_option == 0:  # local
            logger.info("No Logic: Enforcing LOCAL progression items (must stay in target worlds)")
            
            # For per-world progression items, mark each as local to its world
            if self.options.progression_item_type == 0:  # Per-world
                for target_player, item_name in self.progression_items.items():
                    target_world = self.multiworld.worlds[target_player]
                    # Add to target world's local_items to enforce locality
                    if hasattr(target_world.options, 'local_items'):
                        target_world.options.local_items.value.add(item_name)
                        logger.debug(f"No Logic: {item_name} marked as local to player {target_player}")
            
            # For global progression item, it should go to ANY world (not useful as local)
            # So we issue a warning
            elif self.options.progression_item_type == 1:  # Global
                logger.warning("No Logic: Global progression item with LOCAL setting is unusual - "
                               "a global item cannot effectively be local to all worlds. "
                               "Consider using Per-World distribution with Local locality.")
        
        elif locality_option == 1:  # non_local
            logger.info("No Logic: Progression items are NON-LOCAL (can go anywhere)")
            # No restrictions needed - items are unrestricted by default

    def create_regions(self) -> None:
        """Create regions with locations for No Logic."""
        region = Region("No Logic Region", self.player, self.multiworld)

        def get_unused_location_id():
             # Generate unique location IDs for progression item locations
            used_ids = set(loc.address for loc in self.multiworld.get_locations())
            for i in range(RESERVED_LOCATIONS):
                candidate_id = NOLOGIC_BASE_ID + RESERVED_PROGRESSION_ITEMS + 1 + i
                if candidate_id not in used_ids:
                    return candidate_id
            raise NoLogicException("Exceeded reserved location ID space for No Logic world.")

        
        # Create one location per progression item (if any)
        for other_player, location_name in self.progression_locations.items():
            if location_name:
                location = Location(self.player, location_name, get_unused_location_id(), region) # All Items and locations need to have unique IDs, including each progression item location. We can use the reserved ID space for this.
                region.locations.append(location)

                self.options.exclude_locations.value.add(location_name)  # Exclude progression item locations from randomization
                logger.debug(f"No Logic: Created location for progression item: {location_name}")
        
        # If no progression items, create at least one location for the filler item
        if not self.progression_locations:
            location = Location(self.player, "No Logic Check", get_unused_location_id(), region)
            region.locations.append(location)
        
        self.multiworld.regions += [region]

    def create_items(self) -> None:
        """Create progression items for other worlds and filler items."""
        created_items = []

        def get_unused_item_id():
            # Generate unique item IDs for progression items and fillers
            used_ids = set(item.code for item in self.multiworld.itempool)
            for i in range(RESERVED_PROGRESSION_ITEMS + 1):  # +1 for filler
                candidate_id = NOLOGIC_BASE_ID + i
                if candidate_id not in used_ids:
                    return candidate_id
            raise NoLogicException("Exceeded reserved item ID space for No Logic world.")
        
        # Create progression items
        if self.progression_items:
            seen_names = set()
            for other_player, item_name in self.progression_items.items():
                if item_name not in seen_names:
                    item = self.create_item(item_name)
                    item.code = get_unused_item_id()  # Assign unique ID
                    item.player = self.player  # Might make it tied to other player later, for now keeping it like this for safety.
                    self.multiworld.itempool.append(item)
                    created_items.append(item_name)
                    seen_names.add(item_name)
                    logger.info(f"No Logic: Created progression item: {item_name}")
        
        # Create filler to match location count
        locations = self.multiworld.get_locations(self.player)
        items_created = len(created_items)
        needed_fillers = len(locations) - items_created
        
        for i in range(max(0, needed_fillers)):
            filler = self.create_item("Filler")
            self.multiworld.itempool.append(filler)

        logger.info(f"No Logic: Created {len(created_items)} progression items and {max(0, needed_fillers)} filler items for {len(locations)} locations.")

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

    def post_fill(self) -> None:
        """
        After fill, handle locality settings for progression items.
        Use ItemLinks to make progression items available to their respective worlds.
        """
        if not self.progression_items:
            return
        
        logger.info(f"No Logic (P{self.player}): Handling progression item locality...")
        
        locality_option = self.options.progression_item_locality
        
        if locality_option == 1:  # non_local
            logger.info("No Logic: Progression items are non-local (can go anywhere)")
        elif locality_option == 0:  # local
            logger.info("No Logic: Progression items are local (must stay in their worlds)")
        
        import time
        # Log only No Logic world's items and locations
        logger.info("No Logic: Items in item pool:")
        for item in self.multiworld.itempool:
            if item.player == self.player:
                logger.info(f"  - {item.name}: {item.code}")
        
        logger.info("No Logic: Locations:")
        for loc in self.multiworld.get_locations(self.player):
            if loc.player == self.player:
                logger.info(f"  - {loc.name}: {loc.address}")
        time.sleep(10)  # Ensure logs are seen before potential exceptions

    def create_item(self, name: str) -> Item:
        """Create an item for the No Logic world."""
        if name == "Filler":
            return Item(name, ItemClassification.filler, self.item_name_to_id["Filler"], self.player)
        elif name.endswith("'s Progression") or name == "Universal Progression":
            # Progression items are progression-classified so they can be used with ItemLinks
            return Item(name, ItemClassification.progression, None, self.player)
        raise ValueError(f"Unknown item: {name}")

    def get_filler_item_name(self) -> str:
        """Return filler item name."""
        return "Filler"

