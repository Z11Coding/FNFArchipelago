"""
No Logic Archipelago Client
Automatically checks progression item copy locations when progression items are received.
"""

import logging
import asyncio
import sys
from typing import Dict, Set, Optional, List
from CommonClient import CommonContext, ClientStatus, gui_enabled, get_base_parser, handle_url_arg, server_loop, ClientCommandProcessor
from NetUtils import NetworkItem

logger = logging.getLogger("NoLogic")
client_logger = logging.getLogger("Client") # Use the main client logger for general connection and item receipt logs. Will show in Client UI.


class NoLogicCommandProcessor(ClientCommandProcessor):
    """Command processor for No Logic client."""
    
    def _cmd_status(self) -> bool:
        """Display progression item status."""
        if not self.ctx.server or not self.ctx.slot:
            self.output("Not connected to a server.")
            return False
        
        if not isinstance(self.ctx, NoLogicContext):
            self.output("Not connected to a No Logic world.")
            return False
        
        if not self.ctx.claim_dict:
            self.output("No Logic: No progression items loaded")
            return True
        
        # Display count based on mode
        if self.ctx.progression_mode == 0:  # Normal mode
            collected = len(self.ctx.collected_progression_items)
            total = len(self.ctx.claim_dict)
            self.output(f"\nNo Logic Progression Items: {collected}/{total}")
        else:  # Shard mode - show total shard count
            total_shards = sum(self.ctx.shards_received_by_id.values())
            # In global mode: total = shard_count. In per-world: total = num_item_types * shard_count
            if self.ctx.progression_item_type == 1:  # Global
                if self.ctx.using_per_player_claim_dict:
                    # Per-player mode: each player has their own shard count
                    total_possible_shards = sum(self.ctx.item_shard_count_map.values()) if self.ctx.progression_mode == 3 else self.ctx.shard_count
                else:
                    total_possible_shards = self.ctx.shard_count
            else:  # Per-world
                total_possible_shards = len(self.ctx.shard_item_ids) * self.ctx.shard_count
            self.output(f"\nNo Logic Progression Items: {total_shards}/{total_possible_shards}")
        
        self.output("=" * 60)
        
        # Show shard status if in shard mode
        if self.ctx.progression_mode > 0:
            shard_info = self.ctx.get_shard_display_info()
            self.output(f"Shard Status: {shard_info}\n")
        
        # Display per-entry status
        if self.ctx.using_per_player_claim_dict:
            # Per-player mode: display each player's progression
            total_shards = sum(self.ctx.shards_received_by_id.values())
            
            # Calculate total possible shards for display (global count)
            if self.ctx.progression_mode == 2:
                total_possible_shards = self.ctx.shard_count  # Global shard count
            elif self.ctx.progression_mode == 3:
                total_possible_shards = sum(self.ctx.item_shard_count_map.values()) if self.ctx.item_shard_count_map else 0
            else:
                total_possible_shards = self.ctx.shard_count
            
            for player_id in sorted(self.ctx.claim_dict.keys()):
                player_locations = self.ctx.claim_dict[player_id]
                
                if total_possible_shards > 0:
                    # All players use the same global shard count for unlocking
                    locations_unlocked = int(len(player_locations) * total_shards / total_possible_shards)
                    pct = (total_shards / total_possible_shards * 100) if total_possible_shards > 0 else 0
                    is_completed = locations_unlocked == len(player_locations)
                    status = "[X]" if is_completed else "[ ]"
                    
                    # Get player name and game
                    player_name = self.ctx.player_names.get(player_id, f"Player {player_id}")
                    game = self.ctx.slot_info[player_id].game if player_id in self.ctx.slot_info else "Unknown"
                    
                    self.output(f"  {status} ({player_name}) ({game}): {locations_unlocked}/{len(player_locations)} items ({pct:.{self.ctx.percentage_precision}f}%)")
        else:
            # Normal modes: display by item
            for key in self.ctx.claim_dict.keys():
                # Determine the item_id and player_id for this entry
                if self.ctx.using_per_player_claim_dict:
                    # Per-player mode: key is player_id, find the corresponding item_id
                    player_id = key
                    # Find the item_id for this player (first one that maps to this player)
                    item_id = None
                    for iid, pid in self.ctx.item_id_to_player.items():
                        if pid == player_id:
                            item_id = iid
                            break
                    if item_id is None:
                        continue  # Skip if we can't find the item_id
                else:
                    # Normal mode: key is item_id
                    item_id = key
                
                # Determine if item is "completed"
                # Normal mode: check if in collected_progression_items
                # Shard mode: check if ALL shards for THIS ITEM are collected
                if self.ctx.progression_mode == 0:
                    is_completed = item_id in self.ctx.collected_progression_items
                else:  # Shard mode - check if all shards of THIS SPECIFIC ITEM collected
                    shards_for_this_item = self.ctx.shards_received_by_id.get(item_id, 0)
                    is_completed = (shards_for_this_item == self.ctx.shard_count) and self.ctx.shard_count > 0
                
                status = "[X]" if is_completed else "[ ]"
                item_name = self.ctx.progression_item_names.get(item_id, f"Item {item_id}")
                
                if self.ctx.progression_mode == 0:  # Normal mode - show item count
                    item_count = len(self.ctx.claim_dict[key])
                    self.output(f"  {status} {item_name} (contains {item_count} items)")
                else:  # Shard mode - show per-player shard count
                    item_count = len(self.ctx.claim_dict[key])
                    shards_for_this = self.ctx.shards_received_by_id.get(item_id, 0)
                    self.output(f"  {status} {item_name} ({shards_for_this}/{self.ctx.shard_count} shards, {item_count} items)")
        
        self.output("=" * 60 + "\n")
        return True
    
    def _cmd_shard_status(self) -> bool:
        """Display current shard collection status (alias for status command)."""
        return self._cmd_status()
    
    def _cmd_precision(self, precision: str = "") -> bool:
        """Set or display the precision for percentage display.
        
        Usage: !precision [decimals]
        Example: !precision 2
        """
        if not isinstance(self.ctx, NoLogicContext):
            self.output("Not connected to a No Logic world.")
            return False
        
        if not precision:
            # Display current precision
            self.output(f"Current percentage precision: {self.ctx.percentage_precision} decimal places")
            return True
        
        try:
            new_precision = int(precision)
            if new_precision < 0:
                self.output("Precision must be 0 or greater.")
                return False
            if new_precision > 10:
                self.output("Precision must be 10 or less.")
                return False
            
            self.ctx.percentage_precision = new_precision
            self.output(f"Percentage precision set to {new_precision} decimal places")
            return True
        except ValueError:
            self.output(f"Invalid precision value: {precision}. Must be a number between 0 and 10.")
            return False
    
    def _cmd_hints(self) -> bool:
        """Check and display current hint points available."""
        if not self.ctx.server or not self.ctx.slot:
            self.output("Not connected to a server.")
            return False
        
        if not isinstance(self.ctx, NoLogicContext):
            self.output("Not connected to a No Logic world.")
            return False
        
        # Display hint points and cost locally
        self.output(f"Hint Points: {self.ctx.hint_points}")
        hint_cost_points = self.ctx.get_hint_cost_points()
        self.output(f"Hint Cost Per Hint: {self.ctx.hint_cost}% (= {hint_cost_points} points)")
        
        # Only broadcast to chat if we're NOT the No Logic slot
        if not self.ctx.nologic_slot_found:
            import asyncio
            msg = {
                "cmd": "Say",
                "text": f"Checking hint points availability..."
            }
            asyncio.create_task(self.ctx.send_msgs([msg]))
        
        return True


class NoLogicContext(CommonContext):
    """Context for No Logic client with progression item tracking."""
    
    game = "No Logic"
    tags = CommonContext.tags | {"NoLogic"}
    command_processor = NoLogicCommandProcessor
    items_handling = 0b101  # Receive + Collect (no send)
    
    def __init__(self, server_address=None, password=None):
        super().__init__(server_address, password)
        self.progression_items: Dict[int, str] = {}  # {player_id: progression_item_name}
        self.claim_dict: Dict[int, List[int]] = {}  # {progression_item_id or player_id: [location_ids]}
        self.collected_progression_items: Set[int] = set()
        self.auto_checked_locations: Set[int] = set()
        self.auto_checked_locations_by_player: Dict[int, Set[int]] = {}  # {player_id: {location_ids}} for per-player tracking
        self.progression_item_names: Dict[int, str] = {}  # {item_id: "Player X's Progression"}
        self.item_id_to_player: Dict[int, int] = {}  # {item_id: player_id}
        self.player_location_to_player_id: Dict[int, int] = {}  # {location_id: player_id} for location->player mapping in per-player mode
        self.nologic_tab = None
        self.nologic_slot_found = False
        self.last_item_sync_index: int = 0  # Track which items we've processed
        self._check_task: Optional[asyncio.Task] = None  # Periodic progression check task
        
        # Shard tracking
        self.progression_mode: int = 0  # 0=Normal, 1=Shards-All, 2=Shards-Percentage, 3=Shards-Percentage of Items
        self.progression_item_type: int = 0  # 0=Per-world, 1=Global
        self.global_shards_behavior: int = 0  # 0=Shared pool, 1=Per-player
        self.using_per_player_claim_dict: bool = False  # Whether claim_dict uses player_id or item_id as keys
        self.shard_count: int = 0  # Number of shards per player (only if progression_mode 1 or 2)
        self.shard_percentage: int = 0  # Percentage for mode 3
        self.item_shard_count_map: Dict[int, int] = {}  # {item_id: shard_count} for mode 3
        self.shard_item_ids: Set[int] = set()  # All shard item IDs being tracked
        self.shards_received_by_id: Dict[int, int] = {}  # {item_id: count of shards received}
        self.hint_points: int = 0  # Current hint points available
        self.hint_cost: int = 0  # Hint cost percentage (received from server)
        
        # Trap tracking (Phase 9 from world)
        self.trap_mode: int = 0  # 0=Disabled, 1=Global, 2=Per-World, 3=Finders-Keepers
        self.trap_weight: int = 0  # Percentage (0-100%)
        self.trap_dict: Dict[int, List] = {}  # {player_id: [locations]} - varies by mode
        self.trap_item_ids_by_name: Dict[str, int] = {}  # {trap_name: item_id}
        self.trap_item_ids: Set[int] = set()  # All trap item IDs being tracked
        self.trap_item_count_received: Dict[int, int] = {}  # {trap_item_id: count_received} - tracks index for array
        
        # Percentage display formatting
        self.percentage_precision: int = 0  # Number of decimal places for percentage display (0-10)
    
    def load_game_state(self):
        """Load No Logic specific game state from slot_data."""
        slot_data = getattr(self, 'slot_data', None)
        logger.info(f"NoLogic: load_game_state called, slot_data available: {slot_data is not None}")
        
        if slot_data:
            logger.info(f"NoLogic: slot_data keys: {slot_data.keys()}")
            
            # Convert progression_items keys from strings to ints (JSON converts keys to strings)
            progression_items_raw = slot_data.get("progression_items", {})
            self.progression_items = {}
            for key, value in progression_items_raw.items():
                try:
                    self.progression_items[int(key)] = value
                except (ValueError, TypeError):
                    self.progression_items[key] = value
            logger.info(f"NoLogic: progression_items: {self.progression_items}")
            
            # Get the mapping from item_id to player_id
            item_id_to_player_raw = slot_data.get("item_id_to_player", {})
            self.item_id_to_player = {}
            for key, value in item_id_to_player_raw.items():
                try:
                    self.item_id_to_player[int(key)] = int(value)
                except (ValueError, TypeError):
                    self.item_id_to_player[key] = value
            
            # Load shard configuration FIRST to determine if we're in per-player mode
            self.progression_mode = slot_data.get("progression_mode", 0)
            self.progression_item_type = slot_data.get("progression_item_type", 0)
            self.global_shards_behavior = slot_data.get("global_shards_behavior", 0)  # 0=Shared pool, 1=Per-player
            self.using_per_player_claim_dict = slot_data.get("using_per_player_claim_dict", False)
            self.shard_count = slot_data.get("shard_count", 0)
            self.shard_percentage = slot_data.get("shard_percentage", 0)
            
            # Convert string keys to int keys and build progression_item_names mapping
            self.claim_dict = {}
            self.progression_item_names = {}
            claim_dict_raw = slot_data.get("claim_dict", {})
            logger.info(f"NoLogic: claim_dict_raw: {claim_dict_raw}")
            logger.info(f"NoLogic: using_per_player_claim_dict: {self.using_per_player_claim_dict}")
            
            for key, value in claim_dict_raw.items():
                try:
                    dict_key = int(key)
                    self.claim_dict[dict_key] = value
                    
                    if self.using_per_player_claim_dict:
                        # In per-player mode, dict_key is player_id
                        # Get the shard item name from progression_items
                        if dict_key in self.progression_items:
                            shard_item_name = self.progression_items[dict_key]
                            # Find the actual item_id for this shard item
                            # It's the item_id that maps to this player
                            for item_id, player_id in self.item_id_to_player.items():
                                if player_id == dict_key:
                                    self.progression_item_names[item_id] = shard_item_name
                                    logger.debug(f"NoLogic: Mapped shard item_id {item_id} -> '{shard_item_name}' for player {dict_key}")
                                    break
                    else:
                        # In normal mode, dict_key is item_id
                        # Build the progression item name from the player mapping
                        if dict_key in self.item_id_to_player:
                            player_id = self.item_id_to_player[dict_key]
                            if player_id in self.progression_items:
                                self.progression_item_names[dict_key] = self.progression_items[player_id]
                except (ValueError, TypeError):
                    self.claim_dict[key] = value
            
            # Build player->locations mapping for per-player mode to track checked locations per player
            if self.using_per_player_claim_dict:
                for player_id, location_ids in self.claim_dict.items():
                    self.auto_checked_locations_by_player[player_id] = set()
                    for loc_id in location_ids:
                        self.player_location_to_player_id[loc_id] = player_id
            
            # Load per-item shard count map for mode 3
            item_shard_count_map_raw = slot_data.get("item_shard_count_map", {})
            self.item_shard_count_map = {}
            for key, value in item_shard_count_map_raw.items():
                try:
                    self.item_shard_count_map[int(key)] = int(value)
                except (ValueError, TypeError):
                    self.item_shard_count_map[key] = value
            
            if self.progression_mode > 0 and (self.shard_count > 0 or self.item_shard_count_map):
                mode_name = f"Mode {self.progression_mode}"
                if self.progression_mode == 1:
                    mode_name = "Shards-All"
                elif self.progression_mode == 2:
                    mode_name = "Shards-Percentage"
                elif self.progression_mode == 3:
                    mode_name = "Shards-Percentage of Items"
                logger.info(f"NoLogic: Shard mode enabled - {mode_name}, Item Type: {'Global' if self.progression_item_type == 1 else 'Per-world'}, Per-player mode: {self.using_per_player_claim_dict}")
                
                # In shard mode, track which item_ids are shard items
                # In per-player mode: use item_ids from progression_item_names (mapped from player_ids)
                # In normal mode: use item_ids from claim_dict.keys()
                if self.using_per_player_claim_dict:
                    self.shard_item_ids = set(self.progression_item_names.keys())
                else:
                    self.shard_item_ids = set(self.claim_dict.keys())
                
                # Initialize shard count tracking for each shard item
                for item_id in self.shard_item_ids:
                    self.shards_received_by_id[item_id] = 0
                logger.info(f"NoLogic: Tracking {len(self.shard_item_ids)} shard item types: {self.shard_item_ids}")
            
            if self.claim_dict:
                logger.info(f"NoLogic: Loaded claim dict with {len(self.claim_dict)} progression item entries")
                logger.info(f"NoLogic: progression_item_names mapping: {self.progression_item_names}")
            else:
                logger.warning("NoLogic: Claim dict is empty")
            
            # Load trap configuration (Phase 9)
            self.trap_mode = slot_data.get("trap_mode", 0)
            self.trap_weight = slot_data.get("trap_weight", 0)
            
            # Load trap_dict and convert string keys to int keys
            trap_dict_raw = slot_data.get("trap_dict", {})
            self.trap_dict = {}
            for key, value in trap_dict_raw.items():
                try:
                    self.trap_dict[int(key)] = value
                except (ValueError, TypeError):
                    self.trap_dict[key] = value
            
            # Load trap item IDs mapping
            trap_item_ids_raw = slot_data.get("trap_item_ids_by_name", {})
            self.trap_item_ids_by_name = dict(trap_item_ids_raw)  # Keep as string keys for name lookups
            self.trap_item_ids = set(trap_item_ids_raw.values())  # Extract all trap item IDs
            
            if self.trap_mode > 0 and self.trap_weight > 0 and self.trap_dict:
                mode_names = {1: "Global", 2: "Per-World", 3: "Finders-Keepers"}
                mode_name = mode_names.get(self.trap_mode, f"Mode {self.trap_mode}")
                logger.info(f"NoLogic: Trap system enabled - Mode: {mode_name}, Weight: {self.trap_weight}%, Trap Item IDs: {self.trap_item_ids}")
        else:
            logger.warning("NoLogic: No slot_data available yet")
    
    def get_shard_display_info(self) -> str:
        """Get display string for shard progression items."""
        if self.progression_mode == 0:  # Normal mode
            return "(contains x items)"
        elif self.progression_mode == 1:  # Shards-All mode
            total_shards = sum(self.shards_received_by_id.values())
            # In global mode: total = shard_count. In per-world: total = num_item_types * shard_count
            if self.progression_item_type == 1:  # Global
                total_possible = self.shard_count
            else:  # Per-world
                total_possible = len(self.shard_item_ids) * self.shard_count
            return f"({total_shards}/{total_possible} shards collected)"
        elif self.progression_mode == 2:  # Shards-Percentage mode
            if self.using_per_player_claim_dict and self.progression_item_type == 1:
                # Per-player global mode: use the global shard count (not summed across players)
                total_shards = sum(self.shards_received_by_id.values())
                total_possible_shards = self.shard_count  # Global shard count
                
                if total_possible_shards > 0:
                    # Show per-player status inline
                    player_statuses = []
                    for player_id, player_locations in self.claim_dict.items():
                        locations_unlocked = int(len(player_locations) * total_shards / total_possible_shards)
                        player_statuses.append(f"P{player_id}:{locations_unlocked}/{len(player_locations)}")
                    pct = (total_shards / total_possible_shards * 100) if total_possible_shards > 0 else 0
                    return f"({total_shards}/{total_possible_shards} shards, {', '.join(player_statuses)} - {pct:.{self.percentage_precision}f}%)"
                return "(0/0 shards, 0%)"
            elif self.shard_count > 0 and self.claim_dict:
                total_shards = sum(self.shards_received_by_id.values())
                # In global mode: total = shard_count. In per-world: total = num_item_types * shard_count
                if self.progression_item_type == 1:  # Global
                    total_possible = self.shard_count
                else:  # Per-world
                    total_possible = len(self.shard_item_ids) * self.shard_count
                
                percentage = (total_shards / total_possible * 100) if total_possible > 0 else 0
                
                # Get the actual total items from all shard location lists
                total_items = sum(len(locations) for locations in self.claim_dict.values())
                items_unlocked = int(total_items * total_shards / total_possible) if total_possible > 0 else 0
                
                return f"({items_unlocked}/{total_items} items, {percentage:.{self.percentage_precision}f}%)"
            return "(0/0 items, 0%)"
        elif self.progression_mode == 3:  # Shards-Percentage of Items mode
            if self.using_per_player_claim_dict and self.progression_item_type == 1:
                # Per-player global mode: calculate total possible shards across all players
                total_shards = sum(self.shards_received_by_id.values())
                # Calculate total possible shards across all players
                total_possible_shards = sum(self.item_shard_count_map.values()) if self.item_shard_count_map else 0
                
                if total_possible_shards > 0:
                    # Show per-player status inline
                    player_statuses = []
                    for player_id, player_locations in self.claim_dict.items():
                        locations_unlocked = int(len(player_locations) * total_shards / total_possible_shards)
                        pct = (total_shards / total_possible_shards * 100) if total_possible_shards > 0 else 0
                        player_statuses.append(f"P{player_id}:{locations_unlocked}/{len(player_locations)}")
                    return f"({total_shards}/{total_possible_shards} shards, {', '.join(player_statuses)} - {pct:.{self.percentage_precision}f}%)"
                return "(0/0 shards, 0%)"
            elif self.item_shard_count_map and self.claim_dict:
                total_shards = sum(self.shards_received_by_id.values())
                # Total possible shards is the sum of all item-specific shard counts
                total_possible = sum(self.item_shard_count_map.values())
                
                percentage = (total_shards / total_possible * 100) if total_possible > 0 else 0
                
                # Get the actual total items from all shard location lists
                total_items = sum(len(locations) for locations in self.claim_dict.values())
                items_unlocked = int(total_items * total_shards / total_possible) if total_possible > 0 else 0
                
                return f"({items_unlocked}/{total_items} items, {total_shards}/{total_possible} shards, {percentage:.{self.percentage_precision}f}%)"
            return "(0/0 items, 0/0 shards, 0%)"
        return ""
    
    def get_hint_cost_points(self) -> int:
        """Calculate the actual hint cost in points based on hint_cost percentage and total locations.
        
        hint_cost is a percentage. The actual cost in points = percentage x 0.01 x total_locations
        Total locations = len(missing_locations) + len(locations_checked)
        """
        if not self.hint_cost:
            return 0
        
        # Calculate total locations available to this player
        total_locations = len(self.missing_locations) + len(self.locations_checked)
        if total_locations == 0:
            return 0
        
        # Apply the percentage to get points cost (minimum 1 if hint_cost is non-zero)
        return max(1, int(self.hint_cost * 0.01 * total_locations))
    
    def update_shard_count(self) -> None:
        """Update shard count based on items received (per shard item type)."""
        if self.progression_mode == 0 or not self.shard_item_ids:
            return
        
        logger.debug(f"NoLogic: update_shard_count - slot={self.slot}, items_received count={len(self.items_received)}")
        
        # Count shards received for each shard item ID
        # Note: In shard mode, items are sent FROM other players TO us, so we don't filter by player
        for item_id in self.shard_item_ids:
            shard_count = 0
            for item in self.items_received:
                if item.item == item_id:
                    shard_count += 1
                    logger.debug(f"NoLogic: Found shard - item_id={item.item}, sender_player={item.player}")
            logger.debug(f"NoLogic: Shard item ID {item_id} - found {shard_count} shards")
            self.shards_received_by_id[item_id] = shard_count
    
    def on_package(self, cmd: str, args: dict) -> None:
        """Handle incoming packages from server."""
        # Let parent process first to populate slot_info and slot_data
        super().on_package(cmd, args)
        
        # Handle chat messages for hint requests
        if cmd == "PrintJSON":
            self._handle_chat_message(args)
        
        elif cmd == "Connected":
            logger.info(f"NoLogic: Connected message received")
            logger.info(f"NoLogic: Available args keys: {args.keys()}")
            
            # Extract hint cost from Connected message (it's a percentage)
            if "hint_cost" in args:
                self.hint_cost = int(args["hint_cost"])
                hint_cost_points = self.get_hint_cost_points()
                logger.info(f"NoLogic: Hint cost set to {self.hint_cost}% (= {hint_cost_points} points for {len(self.missing_locations) + len(self.locations_checked)} total locations)")
            
            # Extract slot_data directly from Connected message if not yet set
            if not getattr(self, 'slot_data', None) and 'slot_data' in args:
                self.slot_data = args['slot_data']
                logger.info(f"NoLogic: Extracted slot_data from Connected message")
            
            # Extract slot_info to find No Logic world
            # slot_info values are NetworkSlot namedtuples: (name, game, type, ...)
            slot_info = self.slot_info
            
            # Find the No Logic slot
            nologic_slot = None
            for slot_num, slot_data in slot_info.items():
                if slot_data[1] == "No Logic":  # slot_data[1] is the game name
                    nologic_slot = (slot_num, slot_data[0])  # (slot_num, slot_name)
                    self.nologic_slot_found = True
                    break
            
            if not nologic_slot:
                available_games = [slot_data[1] for slot_data in slot_info.values()]
                logger.error("NoLogic: No 'No Logic' world found in slot_info")
                logger.error(f"NoLogic: Available worlds: {available_games}")
                self.disconnected_intentionally = True
                return
            
            slot_num, slot_name = nologic_slot
            self.slot = int(slot_num) if isinstance(slot_num, str) else slot_num
            
            logger.info(f"NoLogic: Found No Logic world at slot {self.slot}")
            self.load_game_state()
            
            # Sync any items already received from the server
            self.last_item_sync_index = 0
            self._check_progression_items()
            
            # Update shard count
            self.update_shard_count()
            
            # Initialize hint points from args if available
            if "hint_points" in args:
                self.hint_points = args["hint_points"]
            
            if self.nologic_tab:
                self.nologic_tab.update_status()
            
            # Send connection info messages
            import asyncio
            asyncio.create_task(self._send_connection_info())
            
            # Start periodic progression item checking
            if hasattr(self, '_check_task') and self._check_task is not None:
                # Cancel old task if it exists
                if not self._check_task.done():
                    self._check_task.cancel()
            import random
            self._check_task = asyncio.create_task(self._periodic_progression_check(random.randrange(30, 60)))  # Random, because why not?
        
        elif cmd == "ReceivedItems":
            self._handle_received_items(args)
        
        elif cmd == "RoomUpdate":
            # Extract hint points from room update if available
            if "hint_points" in args:
                self.hint_points = args["hint_points"]
                logger.debug(f"NoLogic: Updated hint points to {self.hint_points}")
    
    
    def _handle_chat_message(self, args: dict) -> None:
        """Handle chat messages and detect @progression hint requests or @nologic_hints queries.
        
        Only processes Chat-type PrintJSON messages. For Chat messages, the sender is in the 'slot' field
        and the message text is extracted from the 'data' list of JSONMessagePart objects.
        """
        # Only process Chat type messages, ignore other PrintJSON types (Join, Part, Hint, etc.)
        if args.get("type") != "Chat":
            return
        
        # Extract message text from the data list (list of JSONMessagePart dicts)
        data = args.get("data", [])
        if not isinstance(data, list) or not data:
            return
        
        # Concatenate all text parts to get the full message
        message_text = "".join(part.get("text", "") for part in data if isinstance(part, dict))
        
        # Check for @nologic_hints command (other players querying hint status)
        if "@nologic_hints" in message_text.lower():
            try:
                # Respond with current hint points in chat
                import asyncio
                hint_cost_points = self.get_hint_cost_points()
                hint_info = (
                    f"No Logic Hint Status - Available: {self.hint_points}, "
                    f"Cost per hint: {self.hint_cost}% (= {hint_cost_points} points)"
                )
                msg = {
                    "cmd": "Say",
                    "text": hint_info
                }
                asyncio.create_task(self.send_msgs([msg]))
                logger.info(f"NoLogic: Responded to @nologic_hints query with hint status")
                return
            except Exception as e:
                logger.debug(f"NoLogic: Error responding to @nologic_hints: {e}")
                return
        
        # Check if message contains the @progression command
        if "@progression" not in message_text.lower():
            return
        
        try:
            # Extract sender information from the Chat message
            # For Chat-type PrintJSON messages, the sender is in the 'slot' field
            sender_player = args.get("slot")
            
            if sender_player is None:
                logger.debug("NoLogic: Could not determine sender of chat message")
                return
            
            # Find this player's progression item ID
            target_item_id = None
            for item_id, player_id in self.item_id_to_player.items():
                if player_id == sender_player:
                    target_item_id = item_id
                    break
            
            if target_item_id is None:
                logger.debug(f"NoLogic: Player {sender_player} is not tracked in progression items")
                return
            
            # Get the progression item name for this player
            target_item_name = self.progression_item_names.get(target_item_id)
            if not target_item_name:
                logger.debug(f"NoLogic: Could not find item name for ID {target_item_id}")
                return
            
            # Check if we have enough hint points
            hint_cost_points = self.get_hint_cost_points()
            if self.hint_points >= hint_cost_points:
                # Send hint command
                import asyncio
                asyncio.create_task(self._send_hint_request(target_item_name))
                logger.info(f"NoLogic: Detected @progression command from player {sender_player}, sending hint for '{target_item_name}'")
            else:
                # Not enough hint points - send message with deficit info
                needed = hint_cost_points - self.hint_points
                import asyncio
                asyncio.create_task(self._send_insufficient_hints_message(needed))
                logger.info(f"NoLogic: Player {sender_player} requested hint but insufficient points ({self.hint_points}/{hint_cost_points})")
        
        except Exception as e:
            logger.debug(f"NoLogic: Error processing @progression command: {e}")
    
    async def _send_hint_request(self, item_name: str) -> None:
        """Send a hint request for the specified item."""
        if not self.server:
            return
        
        try:
            # Use the !hint command format
            msg = {
                "cmd": "Say",
                "text": f"!hint {item_name}"
            }
            await self.send_msgs([msg])
            logger.debug(f"NoLogic: Sent hint request for '{item_name}'")
        except Exception as e:
            logger.error(f"NoLogic: Error sending hint request for '{item_name}': {e}")
    
    async def _send_insufficient_hints_message(self, needed_points: int) -> None:
        """Send a message indicating insufficient hint points."""
        if not self.server:
            return
        
        try:
            hint_cost_points = self.get_hint_cost_points()
            msg = {
                "cmd": "Say",
                "text": f"Insufficient hint points! Need {needed_points} more (have {self.hint_points}, need {hint_cost_points})"
            }
            await self.send_msgs([msg])
            logger.debug(f"NoLogic: Sent insufficient hints message")
        except Exception as e:
            logger.error(f"NoLogic: Error sending insufficient hints message: {e}")
    
    async def _send_connection_info(self) -> None:
        """Send connection info messages describing available commands."""
        if not self.server:
            return
        
        try:
            # Send info about available commands
            # Note: @commands are for other players to broadcast to, not client-runner specific commands
            messages = [
                "[AUTOMATED] No Logic Client connected and ready!",
                "Available @ commands: @progression (request hint from this client), @nologic_hints (query hint status)"
            ]
            
            for text in messages:
                msg = {
                    "cmd": "Say",
                    "text": text
                }
                await self.send_msgs([msg])
            
            logger.info(f"NoLogic: Sent connection info messages")
        except Exception as e:
            logger.error(f"NoLogic: Error sending connection info messages: {e}")
    
    def _handle_received_items(self, args: dict) -> None:
        """Check for progression item receipts and auto-check locations."""
        self._check_progression_items()
    
    def _check_progression_items(self) -> None:
        """Process all items received to detect progression item changes."""
        # Update shard count if in shard mode
        if self.progression_mode > 0:
            self.update_shard_count()
        
        # Collect all locations to check in one pass
        all_locations_to_check = []
        
        # Special handling: Global percentage modes with per-player claim_dict
        # Process each player's locations with their shard progress applied
        if self.using_per_player_claim_dict and self.progression_item_type == 1:
            # Per-player global mode: claim_dict keys are player_ids
            # All players unlock based on the GLOBAL shard count, not individual player counts
            total_shards = sum(self.shards_received_by_id.values())
            
            if self.progression_mode == 2:  # Shards-Percentage mode
                if self.shard_count > 0:
                    # Apply global shard count to each player's locations
                    for player_id, player_locations in self.claim_dict.items():
                        # All players use the same global shard count for unlocking
                        locations_to_unlock = int(len(player_locations) * total_shards / self.shard_count)
                        locations_to_check = player_locations[:locations_to_unlock]
                        all_locations_to_check.extend(locations_to_check)
                        
                        if locations_to_check:
                            logger.info(f"NoLogic: Global Percentage mode - player {player_id}: unlocking {len(locations_to_check)}/{len(player_locations)} locations ({total_shards}/{self.shard_count} shards)")
            
            elif self.progression_mode == 3:  # Shards-Percentage of Items mode
                # Global mode: use the global shard count (sum of all items' percentages)
                total_possible_shards = sum(self.item_shard_count_map.values()) if self.item_shard_count_map else 0
                
                if total_possible_shards > 0:
                    # Apply global shard count to each player's locations
                    for player_id, player_locations in self.claim_dict.items():
                        # All players use the same global shard count for unlocking
                        locations_to_unlock = int(len(player_locations) * total_shards / total_possible_shards)
                        locations_to_check = player_locations[:locations_to_unlock]
                        all_locations_to_check.extend(locations_to_check)
                        
                        if locations_to_check:
                            logger.info(f"NoLogic: Global Percentage of Items mode - player {player_id}: unlocking {len(locations_to_check)}/{len(player_locations)} locations ({total_shards}/{total_possible_shards} shards)")
        
        for network_item in self.items_received[self.last_item_sync_index:]:
            # Check if this is a progression item we're tracking
            if network_item.item in self.claim_dict.keys() or (self.using_per_player_claim_dict and network_item.item in self.item_id_to_player):
                # Skip per-player global modes - already handled above
                if self.using_per_player_claim_dict and self.progression_item_type == 1:
                    continue
                
                # In normal mode, only process the first time we receive each progression item
                # In shard mode, process every shard received (so we can progressively unlock locations)
                is_first_receipt = network_item.item not in self.collected_progression_items
                
                if self.progression_mode == 0 and not is_first_receipt:
                    # Normal mode: skip if we've already processed this item
                    continue
                
                # Determine the claim_dict key based on mode
                if self.using_per_player_claim_dict:
                    # Per-player mode: key is player_id, not item_id
                    claim_dict_key = self.item_id_to_player.get(network_item.item)
                else:
                    # Normal mode: key is item_id
                    claim_dict_key = network_item.item
                
                if claim_dict_key not in self.claim_dict:
                    logger.warning(f"NoLogic: Received progression item (ID: {network_item.item}) but claim_dict key {claim_dict_key} not found")
                    continue
                
                # Add to collected only in normal mode
                if self.progression_mode == 0:
                    item_name = self.progression_item_names.get(network_item.item, f"Item {network_item.item}")
                    logger.info(f"NoLogic: Received progression item '{item_name}' (ID: {network_item.item})")
                    self.collected_progression_items.add(network_item.item)
                else:
                    # Shard mode: log the shard receipt
                    item_name = self.progression_item_names.get(network_item.item, f"Item {network_item.item}")
                    shards_for_this = self.shards_received_by_id.get(network_item.item, 0)
                    logger.info(f"NoLogic: Received shard for '{item_name}' (ID: {network_item.item}) - now have {shards_for_this} shards")
                
                # Get locations to auto-check
                all_locations = self.claim_dict[claim_dict_key]
                
                # In percentage mode, only check proportional locations based on shard count
                if self.progression_mode == 2:  # Shards-Percentage mode
                    # Use only THIS shard item's count, not the global total
                    shards_for_this_item = self.shards_received_by_id.get(network_item.item, 0)
                    
                    if self.shard_count > 0:
                        # Calculate how many locations should be unlocked based on THIS item's shard progress
                        locations_to_unlock = int(len(all_locations) * shards_for_this_item / self.shard_count)
                        # Take the first N locations (they're pre-shuffled by the world)
                        locations_to_check = all_locations[:locations_to_unlock]
                        logger.info(f"NoLogic: Percentage mode - unlocking {locations_to_unlock}/{len(all_locations)} locations for this player ({shards_for_this_item}/{self.shard_count} shards)")
                    else:
                        locations_to_check = []
                elif self.progression_mode == 3:  # Shards-Percentage of Items mode
                    # Mode 3: Each item_id has its own shard count based on the number of items
                    shards_for_this_item = self.shards_received_by_id.get(network_item.item, 0)
                    item_shard_count = self.item_shard_count_map.get(network_item.item, 1)
                    
                    if item_shard_count > 0:
                        # Calculate how many locations should be unlocked based on THIS item's shard progress
                        locations_to_unlock = int(len(all_locations) * shards_for_this_item / item_shard_count)
                        # Take the first N locations (they're pre-shuffled by the world)
                        locations_to_check = all_locations[:locations_to_unlock]
                        logger.info(f"NoLogic: Percentage of Items mode - unlocking {locations_to_unlock}/{len(all_locations)} locations for this item ({shards_for_this_item}/{item_shard_count} shards)")
                    else:
                        locations_to_check = []
                elif self.progression_mode == 1:  # Shards-All mode
                    # Only unlock all locations when ALL shards are collected
                    shards_for_this_item = self.shards_received_by_id.get(network_item.item, 0)
                    if shards_for_this_item == self.shard_count and self.shard_count > 0:
                        locations_to_check = all_locations
                        logger.info(f"NoLogic: Shards-All mode - unlocking all {len(all_locations)} locations (collected all {self.shard_count} shards)")
                    else:
                        locations_to_check = []
                else:  # Normal mode (0)
                    # Normal mode: check all locations immediately
                    locations_to_check = all_locations
                
                # Collect locations instead of checking immediately
                all_locations_to_check.extend(locations_to_check)
        
        # Sync already-checked locations on first connect (when last_item_sync_index is 0 before this call)
        # This ensures that if locations were already checked in previous session, we track them
        if self.last_item_sync_index == 0 and self.using_per_player_claim_dict and all_locations_to_check:
            # Mark these locations as already checked in our per-player tracking
            for loc_id in all_locations_to_check:
                player_id = self.player_location_to_player_id.get(loc_id)
                if player_id is not None and player_id in self.auto_checked_locations_by_player:
                    self.auto_checked_locations_by_player[player_id].add(loc_id)
            logger.info(f"NoLogic: Synced {len(all_locations_to_check)} already-checked locations on first connect")
        
        # Check for trap items received and auto-check trap locations
        if self.trap_mode > 0 and self.trap_weight > 0 and self.trap_item_ids:
            for network_item in self.items_received[self.last_item_sync_index:]:
                if network_item.item in self.trap_item_ids:
                    # This is a trap item
                    if network_item.item not in self.trap_item_count_received:
                        self.trap_item_count_received[network_item.item] = 0
                    
                    self.trap_item_count_received[network_item.item] += 1
                    trap_count = self.trap_item_count_received[network_item.item]
                    
                    trap_name = None
                    for name, item_id in self.trap_item_ids_by_name.items():
                        if item_id == network_item.item:
                            trap_name = name
                            break
                    
                    logger.info(f"NoLogic: Received trap item '{trap_name}' (ID: {network_item.item})")
                    
                    # Get ONE trap location to check based on trap mode
                    trap_location_to_check = None
                    
                    if self.trap_mode == 1:  # Global mode
                        # Global: check one location from EVERY player's trap locations, cycling through their list
                        for player_id, locations in self.trap_dict.items():
                            if locations:
                                # Use trap_count to cycle through this player's locations
                                location_index = (trap_count - 1) % len(locations)
                                trap_location_to_check = locations[location_index]
                                logger.info(f"NoLogic: Global trap - checking player {player_id}'s location {trap_location_to_check} (index {location_index})")
                                all_locations_to_check.append(trap_location_to_check)
                    
                    elif self.trap_mode == 2:  # Per-World mode
                        # Per-world: check the location for the player who received the trap, cycling through their locations
                        finding_player = network_item.player
                        if finding_player in self.trap_dict:
                            locations = self.trap_dict[finding_player]
                            if locations:
                                # Use trap_count to cycle through this player's locations
                                location_index = (trap_count - 1) % len(locations)
                                trap_location_to_check = locations[location_index]
                                logger.info(f"NoLogic: Per-World trap - checking player {finding_player}'s location {trap_location_to_check} (index {location_index})")
                                all_locations_to_check.append(trap_location_to_check)
                    
                    elif self.trap_mode == 3:  # Finders-Keepers mode
                        # Finders-Keepers: match trap to its source location, then check trap region location
                        finding_player = network_item.player
                        trap_source_location = network_item.location
                        
                        if finding_player in self.trap_dict:
                            location_pairs = self.trap_dict[finding_player]
                            # Find the tuple where first element matches the source location
                            for source_loc, trap_region_loc in location_pairs:
                                if source_loc == trap_source_location:
                                    logger.info(f"NoLogic: Finders-Keepers trap - player {finding_player} found trap at {source_loc}, checking trap region location {trap_region_loc}")
                                    all_locations_to_check.append(trap_region_loc)
                                    break
        
        # Update tab if exists
        if self.nologic_tab:
            self.nologic_tab.update_status()
        
        # Send all collected location checks at once
        if all_locations_to_check:
            import asyncio
            asyncio.create_task(self._auto_check_locations(all_locations_to_check))
        
        # Check if goal is achieved based on mode
        if self.claim_dict:
            if self.progression_mode == 0:
                # Normal mode: all progression items collected
                if len(self.collected_progression_items) == len(self.claim_dict):
                    logger.info("NoLogic: All progression items collected! Goal achieved!")
                    self.finished_game = True
                    self.status = ClientStatus.CLIENT_GOAL
            else:
                # Shard mode: all shards of all types collected
                total_shards = sum(self.shards_received_by_id.values())
                if self.progression_mode == 3:  # Shards-Percentage of Items mode
                    total_possible = sum(self.item_shard_count_map.values())
                elif self.progression_item_type == 1:  # Global (modes 1 and 2)
                    total_possible = self.shard_count
                else:  # Per-world (modes 1 and 2)
                    total_possible = len(self.shard_item_ids) * self.shard_count
                if total_shards == total_possible and total_possible > 0:
                    logger.info(f"NoLogic: All {total_shards} shards collected! Goal achieved!")
                    self.finished_game = True
                    self.status = ClientStatus.CLIENT_GOAL
        
        # Update sync index
        self.last_item_sync_index = len(self.items_received)
    
    async def _auto_check_locations(self, location_ids: List[int]) -> None:
        """Auto-check the specified locations."""
        if not location_ids:
            return
        
        unchecked_locations = [loc_id for loc_id in location_ids if loc_id not in self.auto_checked_locations]
        
        if unchecked_locations:
            logger.info(f"NoLogic: Sending {len(unchecked_locations)} location checks")
            msg = {
                "cmd": "LocationChecks",
                "locations": unchecked_locations
            }
            await self.send_msgs([msg])
            self.auto_checked_locations.update(unchecked_locations)
            
            # Track which player each location belongs to (for per-player mode)
            if self.using_per_player_claim_dict:
                for loc_id in unchecked_locations:
                    player_id = self.player_location_to_player_id.get(loc_id)
                    if player_id is not None and player_id in self.auto_checked_locations_by_player:
                        self.auto_checked_locations_by_player[player_id].add(loc_id)
    
    async def server_auth(self, password_requested: bool = False) -> None:
        """Authenticate with the server and auto-detect No Logic world."""
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        
        await self.get_username()
        # Don't specify a slot name - let server respond with slot_info
        # We'll find the No Logic slot from the Connected message
        await self.send_connect(name=self.auth, password=self.password)
    
    async def _periodic_progression_check(self, interval: float = 5.0) -> None:
        """Periodically send sync requests to the server to check for item updates."""
        import asyncio
        
        while self.server_address:  # Continue while connected
            try:
                await asyncio.sleep(interval)
                # Send a Sync message to request item updates from server
                await self.send_msgs([{"cmd": "Sync"}])
            except Exception as e:
                logger.error(f"NoLogic: Error in periodic sync check: {e}")
                break

    async def get_username(self):
        client_logger.info("This Client only can connect to a No Logic slot.")
        return await super().get_username()
    
    async def disconnect(self, allow_autoreconnect: bool = False) -> None:
        """Disconnect from server and reset all state."""
        self.nologic_slot_found = False
        
        # Cancel periodic check task
        import asyncio
        if hasattr(self, '_check_task') and self._check_task is not None:
            if not self._check_task.done():
                self._check_task.cancel()
            self._check_task = None
        
        # Clear all server-specific state
        self.progression_items.clear()
        self.claim_dict.clear()
        self.collected_progression_items.clear()
        self.auto_checked_locations.clear()
        self.auto_checked_locations_by_player.clear()
        self.player_location_to_player_id.clear()
        self.progression_item_names.clear()
        self.item_id_to_player.clear()
        self.shard_item_ids.clear()
        self.shards_received_by_id.clear()
        self.item_shard_count_map.clear()
        self.last_item_sync_index = 0
        
        # Reset progression and shard configuration
        self.progression_mode = 0
        self.progression_item_type = 0
        self.shard_count = 0
        self.shard_percentage = 0
        self.hint_points = 0
        self.hint_cost = 0
        
        # Clear trap state
        self.trap_mode = 0
        self.trap_weight = 0
        self.trap_dict.clear()
        self.trap_item_ids_by_name.clear()
        self.trap_item_ids.clear()
        self.trap_item_count_received.clear()
        
        # Reset finished_game flag
        self.finished_game = False
        
        # Update UI if connected
        if self.nologic_tab:
            self.nologic_tab.update_status()
        
        await super().disconnect(allow_autoreconnect)
    
    def make_gui(self):
        """Return the No Logic Manager class."""
        return NoLogicManager


if gui_enabled:
    from kvui import MDLabel  # Import from kvui FIRST before any kivy imports
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.scrollview import ScrollView
    
    class NoLogicTab(BoxLayout):
        """Tab widget for displaying progression items."""
        
        def __init__(self, ctx: NoLogicContext, **kwargs):
            super().__init__(orientation="vertical", **kwargs)
            
            self.ctx = ctx
            self.ctx.nologic_tab = self
            
            # Header with status
            header = BoxLayout(orientation="horizontal", size_hint_y=None, height=60)
            self.status_label = MDLabel(
                text="No Logic - Waiting to connect...",
                halign="center",
                size_hint_y=None,
                height=60
            )
            header.add_widget(self.status_label)
            self.add_widget(header)
            
            # Scrollable list of progression items
            scroll = ScrollView(size_hint=(1, 1))
            self.items_grid = GridLayout(
                cols=1,
                spacing=10,
                size_hint_y=None,
                padding=10
            )
            self.items_grid.bind(minimum_height=self.items_grid.setter("height"))
            scroll.add_widget(self.items_grid)
            self.add_widget(scroll)
        
        def update_status(self):
            """Update the progression items display."""
            # Check connection state first
            if not self.ctx.nologic_slot_found:
                self.status_label.text = "No Logic - Waiting to connect..."
                self.items_grid.clear_widgets()
                return
            
            if not self.ctx.claim_dict:
                self.status_label.text = "No Logic - No progression items loaded"
                self.items_grid.clear_widgets()
                return
            
            # Display count based on mode
            if self.ctx.progression_mode == 0:  # Normal mode
                collected = len(self.ctx.collected_progression_items)
                total = len(self.ctx.claim_dict)
                self.status_label.text = f"No Logic - Progression Items: {collected}/{total}"
            else:  # Shard mode - show correct total based on item type
                total_shards = sum(self.ctx.shards_received_by_id.values())
                # In mode 3 (Percentage of Items): total varies per item, sum all item shard counts
                if self.ctx.progression_mode == 3 and self.ctx.item_shard_count_map:  # 3 = Shards - Percentage of Items
                    total_possible = sum(self.ctx.item_shard_count_map.values())
                # In global mode: total = shard_count. In per-world: total = num_item_types * shard_count
                elif self.ctx.progression_item_type == 1:  # Global
                    total_possible = self.ctx.shard_count
                else:  # Per-world
                    total_possible = len(self.ctx.shard_item_ids) * self.ctx.shard_count
                self.status_label.text = f"No Logic - Progression Items: {total_shards}/{total_possible}"
            
            # Update item list
            self.items_grid.clear_widgets()
            
            # Handle per-player mode specially (display each player's progress)
            if self.ctx.using_per_player_claim_dict:
                
                for player_id in sorted(self.ctx.claim_dict.keys()):
                    player_locations = self.ctx.claim_dict[player_id]
                    
                    # Count how many of this player's locations have actually been checked
                    checked_for_player = len(self.ctx.auto_checked_locations_by_player.get(player_id, set()))
                    
                    # Calculate percentage based on actual checked locations vs total locations
                    if len(player_locations) > 0:
                        pct = (checked_for_player / len(player_locations) * 100)
                    else:
                        pct = 0
                    
                    # Get player name and game
                    player_name = self.ctx.player_names.get(player_id, f"Player {player_id}")
                    game_name = "Unknown"
                    if player_id in self.ctx.slot_info:
                        game_name = self.ctx.slot_info[player_id].game
                    
                    player_display = f"{player_name} ({game_name})"
                    
                    # Per-player completion: all of this player's items are unlocked
                    is_completed = checked_for_player == len(player_locations)
                    status = "[X]" if is_completed else "[ ]"
                    
                    if self.ctx.progression_mode == 2:  # Shards-Percentage
                        label_text = f"{status} {player_display}: {checked_for_player}/{len(player_locations)} items ({pct:.{self.ctx.percentage_precision}f}%)"
                    elif self.ctx.progression_mode == 3:  # Shards-Percentage of Items
                        label_text = f"{status} {player_display}: {checked_for_player}/{len(player_locations)} items ({pct:.{self.ctx.percentage_precision}f}%)"
                    else:  # Mode 1 (Shards-All)
                        label_text = f"{status} {player_display}: {checked_for_player}/{len(player_locations)} items ({pct:.{self.ctx.percentage_precision}f}%)"
                    
                    label = MDLabel(
                        text=label_text,
                        size_hint_y=None,
                        height=40
                    )
                    self.items_grid.add_widget(label)
            else:
                # Normal modes: display by item
                for claim_dict_key in sorted(self.ctx.claim_dict.keys()):
                    # Determine the actual item_id
                    if self.ctx.using_per_player_claim_dict:
                        # This shouldn't happen, but just in case
                        player_id = claim_dict_key
                        item_id = None
                        for iid, pid in self.ctx.item_id_to_player.items():
                            if pid == player_id:
                                item_id = iid
                                break
                        if item_id is None:
                            continue
                    else:
                        # Normal mode: key is item_id
                        item_id = claim_dict_key
                    
                    # In shard mode, only mark as complete when ALL shards are collected FOR THAT ITEM
                    if self.ctx.progression_mode == 0:
                        status = "[X]" if item_id in self.ctx.collected_progression_items else "[ ]"
                    else:  # Shard mode - check if all shards collected FOR THIS SPECIFIC ITEM
                        shards_for_this_item = self.ctx.shards_received_by_id.get(item_id, 0)
                        # For mode 3, use the item-specific shard count from the map
                        if self.ctx.progression_mode == 3 and self.ctx.item_shard_count_map:  # 3 = Shards - Percentage of Items
                            max_shards_for_item = self.ctx.item_shard_count_map.get(item_id, self.ctx.shard_count)
                        else:
                            max_shards_for_item = self.ctx.shard_count
                        status = "[X]" if (shards_for_this_item == max_shards_for_item) and max_shards_for_item > 0 else "[ ]"
                    
                    item_name = self.ctx.progression_item_names.get(item_id, f"Item {item_id}")
                    
                    # Show item count in shard mode
                    if self.ctx.progression_mode > 0:
                        item_count = len(self.ctx.claim_dict[claim_dict_key])
                        shards_for_this = self.ctx.shards_received_by_id.get(item_id, 0)
                        # For mode 3, use the item-specific shard count in the label
                        if self.ctx.progression_mode == 3 and self.ctx.item_shard_count_map:  # 3 = Shards - Percentage of Items
                            max_shards_for_item = self.ctx.item_shard_count_map.get(item_id, self.ctx.shard_count)
                        else:
                            max_shards_for_item = self.ctx.shard_count
                        label_text = f"{status} {item_name} ({shards_for_this}/{max_shards_for_item} shards, {item_count} items)"
                    else:  # Normal mode
                        item_count = len(self.ctx.claim_dict[claim_dict_key])
                        label_text = f"{status} {item_name} (contains {item_count} items)"
                    
                    label = MDLabel(
                        text=label_text,
                        size_hint_y=None,
                        height=40
                    )
                    self.items_grid.add_widget(label)
else:
    # Stub for CLI mode
    class NoLogicTab:
        def __init__(self, ctx: NoLogicContext, **kwargs):
            self.ctx = ctx
            self.ctx.nologic_tab = self
        
        def update_status(self):
            pass


# Create the actual GameManager subclass that will be returned by make_gui()
if gui_enabled:
    from kvui import GameManager
    
    class NoLogicManager(GameManager):
        """Manager/UI for No Logic client."""
        
        base_title = "No Logic Client"
        
        def build(self):
            """Build the No Logic GUI with progression item tab."""
            container = super().build()
            
            # Create and add the No Logic tab
            tab = NoLogicTab(self.ctx)
            self.add_client_tab("No Logic", tab)
            
            return container
else:
    # For CLI mode, just create a simple manager that does nothing
    class NoLogicManager:
        """Simple manager for CLI mode."""
        
        def __init__(self, ctx: NoLogicContext):
            self.ctx = ctx
            self.base_title = "No Logic Client"


async def main(args):
    """Main async entry point."""
    ctx = NoLogicContext(args.connect, args.password)
    ctx.auth = args.name
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
    
    if gui_enabled:
        ctx.run_gui()
    else:
        ctx.run_cli()
    
    await ctx.exit_event.wait()
    await ctx.shutdown()


def launch(*args):
    """Launch the No Logic client."""
    parser = get_base_parser(description="No Logic Archipelago Client")
    parser.add_argument("--name", default=None, help="Slot Name to connect as")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")
    
    parsed_args = handle_url_arg(parser.parse_args(args))
    
    asyncio.run(main(parsed_args))


if __name__ == "__main__":
    launch(*sys.argv[1:])
