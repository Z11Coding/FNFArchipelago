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
                total_possible = self.ctx.shard_count
            else:  # Per-world
                total_possible = len(self.ctx.shard_item_ids) * self.ctx.shard_count
            self.output(f"\nNo Logic Progression Items: {total_shards}/{total_possible}")
        
        self.output("=" * 60)
        
        # Show shard status if in shard mode
        if self.ctx.progression_mode > 0:
            shard_info = self.ctx.get_shard_display_info()
            self.output(f"Shard Status: {shard_info}\n")
        
        for item_id in self.ctx.claim_dict.keys():
            # Determine if item is "completed"
            # Normal mode: check if in collected_progression_items
            # Shard mode: check if ALL shards are collected
            if self.ctx.progression_mode == 0:
                is_completed = item_id in self.ctx.collected_progression_items
            else:  # Shard mode - check if all shards of all types collected
                total_shards = sum(self.ctx.shards_received_by_id.values())
                if self.ctx.progression_item_type == 1:  # Global
                    total_possible = self.ctx.shard_count
                else:  # Per-world
                    total_possible = len(self.ctx.shard_item_ids) * self.ctx.shard_count
                is_completed = (total_shards == total_possible) and total_possible > 0
            
            status = "[X]" if is_completed else "[ ]"
            item_name = self.ctx.progression_item_names.get(item_id, f"Item {item_id}")
            
            if self.ctx.progression_mode == 0:  # Normal mode - show item count
                item_count = len(self.ctx.claim_dict[item_id])
                self.output(f"  {status} {item_name} (contains {item_count} items)")
            else:  # Shard mode - show per-player shard count
                item_count = len(self.ctx.claim_dict[item_id])
                shards_for_this = self.ctx.shards_received_by_id.get(item_id, 0)
                self.output(f"  {status} {item_name} ({shards_for_this}/{self.ctx.shard_count} shards, {item_count} items)")
        
        self.output("=" * 60 + "\n")
        return True
    
    def _cmd_shard_status(self) -> bool:
        """Display current shard collection status (alias for status command)."""
        return self._cmd_status()


class NoLogicContext(CommonContext):
    """Context for No Logic client with progression item tracking."""
    
    game = "No Logic"
    tags = CommonContext.tags | {"NoLogic"}
    command_processor = NoLogicCommandProcessor
    items_handling = 0b101  # Receive + Collect (no send)
    
    def __init__(self, server_address=None, password=None):
        super().__init__(server_address, password)
        self.progression_items: Dict[int, str] = {}  # {player_id: progression_item_name}
        self.claim_dict: Dict[int, List[int]] = {}  # {progression_item_id: [location_ids]}
        self.collected_progression_items: Set[int] = set()
        self.auto_checked_locations: Set[int] = set()
        self.progression_item_names: Dict[int, str] = {}  # {item_id: "Player X's Progression"}
        self.item_id_to_player: Dict[int, int] = {}  # {item_id: player_id}
        self.nologic_tab = None
        self.nologic_slot_found = False
        self.last_item_sync_index: int = 0  # Track which items we've processed
        self._check_task: Optional[asyncio.Task] = None  # Periodic progression check task
        
        # Shard tracking
        self.progression_mode: int = 0  # 0=Normal, 1=Shards-All, 2=Shards-Percentage
        self.shard_count: int = 0  # Number of shards per player (only if progression_mode > 0)
        self.shard_item_ids: Set[int] = set()  # All shard item IDs being tracked
        self.shards_received_by_id: Dict[int, int] = {}  # {item_id: count of shards received}
    
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
            
            # Convert string keys to int keys and build progression_item_names mapping
            self.claim_dict = {}
            self.progression_item_names = {}
            claim_dict_raw = slot_data.get("claim_dict", {})
            logger.info(f"NoLogic: claim_dict_raw: {claim_dict_raw}")
            
            for key, value in claim_dict_raw.items():
                try:
                    item_id = int(key)
                    self.claim_dict[item_id] = value
                    
                    # Build the progression item name from the player mapping
                    if item_id in self.item_id_to_player:
                        player_id = self.item_id_to_player[item_id]
                        if player_id in self.progression_items:
                            self.progression_item_names[item_id] = self.progression_items[player_id]
                except (ValueError, TypeError):
                    self.claim_dict[key] = value
            
            # Load shard configuration if available
            self.progression_mode = slot_data.get("progression_mode", 0)
            self.progression_item_type = slot_data.get("progression_item_type", 0)
            self.shard_count = slot_data.get("shard_count", 0)
            
            if self.progression_mode > 0 and self.shard_count > 0:
                logger.info(f"NoLogic: Shard mode enabled - Mode: {self.progression_mode}, Item Type: {'Global' if self.progression_item_type == 1 else 'Per-world'}, Shard count per: {self.shard_count}")
                # In shard mode, all items in claim_dict are shard items
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
            if self.shard_count > 0 and self.claim_dict:
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
                
                return f"({items_unlocked}/{total_items} items, {percentage:.0f}%)"
            return "(0/0 items, 0%)"
        return ""
    
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
        
        if cmd == "Connected":
            logger.info(f"NoLogic: Connected message received")
            logger.info(f"NoLogic: Available args keys: {args.keys()}")
            
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
            
            if self.nologic_tab:
                self.nologic_tab.update_status()
            
            # Start periodic progression item checking
            import asyncio
            if hasattr(self, '_check_task') and self._check_task is not None:
                # Cancel old task if it exists
                if not self._check_task.done():
                    self._check_task.cancel()
            self._check_task = asyncio.create_task(self._periodic_progression_check())
        
        elif cmd == "ReceivedItems":
            self._handle_received_items(args)
    
    
    def _handle_received_items(self, args: dict) -> None:
        """Check for progression item receipts and auto-check locations."""
        self._check_progression_items()
    
    def _check_progression_items(self) -> None:
        """Process all items received to detect progression item changes."""
        # Update shard count if in shard mode
        if self.progression_mode > 0:
            self.update_shard_count()
        
        for network_item in self.items_received[self.last_item_sync_index:]:
            # Check if this is a progression item we're tracking
            if network_item.item in self.claim_dict.keys():
                # In normal mode, only process the first time we receive each progression item
                # In shard mode, process every shard received (so we can progressively unlock locations)
                is_first_receipt = network_item.item not in self.collected_progression_items
                
                if self.progression_mode == 0 and not is_first_receipt:
                    # Normal mode: skip if we've already processed this item
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
                all_locations = self.claim_dict[network_item.item]
                
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
                
                # Schedule async auto-check task
                import asyncio
                asyncio.create_task(self._auto_check_locations(locations_to_check))
                # Update tab if exists
                if self.nologic_tab:
                    self.nologic_tab.update_status()
        
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
                if self.progression_item_type == 1:  # Global
                    total_possible = self.shard_count
                else:  # Per-world
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
            logger.warning("NoLogic: _auto_check_locations called with empty location_ids")
            return
        
        logger.info(f"NoLogic: _auto_check_locations called with {len(location_ids)} location IDs: {location_ids}")
        logger.info(f"NoLogic: Already auto-checked locations: {self.auto_checked_locations}")
        
        unchecked_locations = [loc_id for loc_id in location_ids if loc_id not in self.auto_checked_locations]
        
        logger.info(f"NoLogic: Unchecked locations after filtering: {unchecked_locations}")
        
        if unchecked_locations:
            logger.info(f"NoLogic: Auto-checking {len(unchecked_locations)} progression item copy locations")
            msg = {
                "cmd": "LocationChecks",
                "locations": unchecked_locations
            }
            logger.info(f"NoLogic: Sending message: {msg}")
            await self.send_msgs([msg])
            self.auto_checked_locations.update(unchecked_locations)
            logger.info(f"NoLogic: Auto-checked locations now: {self.auto_checked_locations}")
        else:
            logger.warning("NoLogic: All location IDs already auto-checked")
    
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
        """Disconnect from server and reset slot tracking."""
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
        self.progression_item_names.clear()
        self.item_id_to_player.clear()
        self.shard_item_ids.clear()
        self.shards_received_by_id.clear()
        self.last_item_sync_index = 0
        
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
                # In global mode: total = shard_count. In per-world: total = num_item_types * shard_count
                if self.ctx.progression_item_type == 1:  # Global
                    total_possible = self.ctx.shard_count
                else:  # Per-world
                    total_possible = len(self.ctx.shard_item_ids) * self.ctx.shard_count
                self.status_label.text = f"No Logic - Progression Items: {total_shards}/{total_possible}"
            
            # Update item list
            self.items_grid.clear_widgets()
            for item_id in self.ctx.claim_dict.keys():
                # In shard mode, only mark as complete when ALL shards are collected
                if self.ctx.progression_mode == 0:
                    status = "[X]" if item_id in self.ctx.collected_progression_items else "[ ]"
                else:  # Shard mode - check if all shards collected
                    total_shards = sum(self.ctx.shards_received_by_id.values())
                    if self.ctx.progression_item_type == 1:  # Global
                        total_possible = self.ctx.shard_count
                    else:  # Per-world
                        total_possible = len(self.ctx.shard_item_ids) * self.ctx.shard_count
                    status = "[X]" if (total_shards == total_possible) and total_possible > 0 else "[ ]"
                
                item_name = self.ctx.progression_item_names.get(item_id, f"Item {item_id}")
                
                # Show item count in shard mode
                if self.ctx.progression_mode > 0:
                    item_count = len(self.ctx.claim_dict[item_id])
                    shards_for_this = self.ctx.shards_received_by_id.get(item_id, 0)
                    label_text = f"{status} {item_name} ({shards_for_this}/{self.ctx.shard_count} shards, {item_count} items)"
                else:  # Normal mode
                    item_count = len(self.ctx.claim_dict[item_id])
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
