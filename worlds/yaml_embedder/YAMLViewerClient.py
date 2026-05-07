"""
YAML Viewer Client - Downloads and displays slot YAML data from Archipelago servers.

Features:
- Connect to server and retrieve slot data
- Display recreated YAML with all options and randomization info
- Download YAML file
- Quick swap between different slots
- Automatic reconnection with password caching
"""

import asyncio
import json
import logging
import os
import threading
import gzip
import base64
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

import websockets
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.textfield import MDTextField
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.card import MDCard
from kivymd.uix.divider import MDDivider
from kivymd.uix.dialog import MDDialog

logger = logging.getLogger("YAML Viewer")
logger.setLevel(logging.DEBUG)

# Ensure we have a handler for INFO+ messages
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class YAMLViewerClient:
    """Client for retrieving and displaying slot YAML data."""
    
    def __init__(self):
        self.server_address: Optional[str] = None
        self.port: int = 38281
        self.slot_name: Optional[str] = None
        self.password: Optional[str] = None
        self.server_password: Optional[str] = None
        
        self.websocket = None
        self.connection_state = "disconnected"
        self.slot_data: Optional[Dict[str, Any]] = None
        self.ap_slot_yaml: Optional[str] = None
        self.ap_slot_yaml_formats: Optional[Dict[str, Any]] = None
        self.ap_slot_options: Optional[Dict[str, Any]] = None
        
        # UI callback
        self.ui_callback = None
        self.room_info = None
        
        # Event loop management - single loop for all async operations
        self.event_loop: Optional[asyncio.AbstractEventLoop] = None
        self.loop_thread: Optional[threading.Thread] = None
        self._keep_alive_task = None
        self._setup_event_loop()
    
    def _setup_event_loop(self) -> None:
        """Set up a background event loop that runs in a separate thread."""
        try:
            # Create a new event loop for this thread
            self.event_loop = asyncio.new_event_loop()
            
            def run_loop():
                """Run the event loop in background thread."""
                asyncio.set_event_loop(self.event_loop)
                self.event_loop.run_forever()
            
            # Start background thread with the event loop
            self.loop_thread = threading.Thread(target=run_loop, daemon=True)
            self.loop_thread.start()
            logger.info("[YAML Viewer] Background event loop started")
        except Exception as e:
            logger.error(f"[YAML Viewer] Failed to setup event loop: {e}")
    
    def _run_async(self, coro) -> asyncio.Future:
        """Run a coroutine in the background event loop."""
        if not self.event_loop:
            logger.error("[YAML Viewer] Event loop not available")
            return None
        return asyncio.run_coroutine_threadsafe(coro, self.event_loop)
    
    async def connect(self, server_address: str, slot_name: str, password: str = "") -> bool:
        """Connect to server and retrieve slot data.
        
        Args:
            server_address: Address like "localhost:38281" or just "localhost"
            slot_name: Name of the slot to connect to
            password: Server password (optional)
        
        Returns:
            True if connection and data retrieval successful
        """
        try:
            self.server_address = server_address
            self.slot_name = slot_name
            self.password = password
            
            # Parse address
            if ":" in server_address:
                host, port_str = server_address.rsplit(":", 1)
                self.port = int(port_str)
            else:
                host = server_address
            
            # Connect
            uri = f"ws://{host}:{self.port}"
            logger.info(f"[YAML Viewer] Connecting to {uri} for slot '{slot_name}'")
            
            self.websocket = await websockets.connect(uri)
            self.connection_state = "connected"
            logger.info("[YAML Viewer] WebSocket connection established")
            
            # Get room info
            room_ok = await self._receive_room_info()
            if not room_ok:
                logger.warning("[YAML Viewer] Failed to receive room info")
                await self._disconnect()
                return False
            
            logger.info("[YAML Viewer] Room info received successfully")
            
            # Get slot data
            success = await self._retrieve_slot_data(slot_name, password)
            
            if success:
                self.connection_state = "authenticated"
                logger.info(f"[YAML Viewer] Successfully authenticated and retrieved data for slot '{slot_name}'")
                logger.info(f"[YAML Viewer] Slot data keys: {list(self.slot_data.keys()) if self.slot_data else 'None'}")
                logger.info(f"[YAML Viewer] YAML data available: {bool(self.ap_slot_yaml)}")
                if self.ui_callback:
                    self.ui_callback("connected", {"slot": slot_name})
                
                # Start background listener to keep connection alive
                logger.info("[YAML Viewer] Starting connection keep-alive listener")
                self._keep_alive_task = asyncio.create_task(self._keep_alive_listener())
            else:
                self.connection_state = "disconnected"
                logger.error("[YAML Viewer] Failed to retrieve slot data")
                await self._disconnect()
            
            return success
            
        except Exception as e:
            logger.error(f"[YAML Viewer] Connection failed: {e}", exc_info=True)
            self.connection_state = "disconnected"
            if self.websocket:
                try:
                    await self.websocket.close()
                except Exception:
                    pass
                self.websocket = None
            return False
    
    async def _keep_alive_listener(self) -> None:
        """Listen for server messages to keep connection alive."""
        try:
            logger.info("[YAML Viewer] Keep-alive listener started")
            while self.websocket and self.connection_state == "authenticated":
                try:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=30.0)
                    logger.debug(f"[YAML Viewer] Received server message: {len(message)} bytes")
                    # Just log incoming messages, we already have the data we need
                except asyncio.TimeoutError:
                    # Keep-alive ping/pong typically sent by websockets library
                    continue
                except asyncio.CancelledError:
                    logger.info("[YAML Viewer] Keep-alive listener cancelled")
                    break
                except Exception as e:
                    logger.warning(f"[YAML Viewer] Listen error: {e}")
                    break
            logger.info("[YAML Viewer] Keep-alive listener stopped")
        except asyncio.CancelledError:
            logger.info("[YAML Viewer] Keep-alive listener task cancelled")
        except Exception as e:
            logger.error(f"[YAML Viewer] Keep-alive listener error: {e}")
    
    async def _receive_room_info(self) -> bool:
        """Receive room info from server."""
        try:
            message = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
            data = json.loads(message)
            logger.info(f"[YAML Viewer] Received message with {len(data)} commands")
            
            # Archipelago sends messages as arrays of command dicts
            if isinstance(data, list):
                for cmd_dict in data:
                    if cmd_dict.get("cmd") == "RoomInfo":
                        self.room_info = cmd_dict
                        version = cmd_dict.get('version', {})
                        logger.info(f"[YAML Viewer] Received RoomInfo: version {version.get('major')}.{version.get('minor')}.{version.get('build')}")
                        return True
            
            logger.warning("[YAML Viewer] No RoomInfo command in first message")
            return False
        except asyncio.TimeoutError:
            logger.error("[YAML Viewer] Timeout waiting for room info")
            return False
        except Exception as e:
            logger.error(f"[YAML Viewer] Error receiving room info: {e}")
            return False
    
    async def _retrieve_slot_data(self, slot_name: str, password: str = "") -> bool:
        """Request and retrieve slot data from server.
        
        Args:
            slot_name: Name of the slot
            password: Server password
        
        Returns:
            True if successful
        """
        try:
            # Send Connect handshake packet (following TextOnly pattern from CommonClient)
            connect_request = {
                "cmd": "Connect",
                "password": password,  # Always include password field
                "name": slot_name,
                "game": "",  # TextOnly clients use empty game
                "uuid": "",
                "tags": ["YAML-Viewer", "TextOnly"],
                "version": {"class": "Version", "major": 0, "minor": 6, "build": 7},  # class required for dict versions
                "items_handling": 0b111,  # Receive all items for reference
                "slot_data": True  # Request slot_data in Connected response
            }
            
            logger.info(f"[YAML Viewer] Sending Connect handshake for slot '{slot_name}'")
            logger.debug(f"[YAML Viewer] Connect packet details: {connect_request}")
            await self.websocket.send(json.dumps([connect_request]))
            
            # Wait for response - Archipelago sends arrays of command dicts
            message = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
            response = json.loads(message)
            
            logger.info(f"[YAML Viewer] Received response with {len(response) if isinstance(response, list) else 1} command(s)")
            
            # Handle server response - look for Connected command
            if isinstance(response, list):
                for cmd_dict in response:
                    cmd = cmd_dict.get("cmd")
                    logger.info(f"[YAML Viewer] Processing command: {cmd}")
                    
                    if cmd == "Connected":
                        self.slot_data = cmd_dict.get("slot_data", {})
                        logger.info(f"[YAML Viewer] Connected! Received slot_data with keys: {list(self.slot_data.keys())}")
                        self._extract_yaml_data()
                        logger.info(f"[YAML Viewer] Extracted YAML data - ap_slot_yaml available: {bool(self.ap_slot_yaml)}")
                        return True
                    elif cmd == "ConnectionRefused":
                        errors = cmd_dict.get("errors", ["Unknown error"])
                        logger.error(f"[YAML Viewer] Connection refused: {errors}")
                        return False
            
            logger.error(f"[YAML Viewer] Unexpected response format: {response}")
            return False
            
        except asyncio.TimeoutError:
            logger.error("[YAML Viewer] Timeout retrieving slot data (5 second timeout)")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"[YAML Viewer] JSON decode error: {e}")
            return False
        except Exception as e:
            logger.error(f"[YAML Viewer] Error retrieving slot data: {e}", exc_info=True)
            return False
    
    def _extract_yaml_data(self) -> None:
        """Extract YAML-related data from slot_data (decompressed from compressed format)."""
        if not self.slot_data:
            logger.warning("[YAML Viewer] No slot_data to extract from")
            return
        
        logger.info(f"[YAML Viewer] Extracting data from slot_data...")
        
        # Try to decompress the new compressed format
        compressed_data = self.slot_data.get("ap_slot_meta_yaml_info")
        if compressed_data:
            try:
                # Decompress the metadata
                decompressed = self._decompress_yaml_metadata(compressed_data)
                self.ap_slot_yaml = decompressed.get("yaml")
                self.ap_slot_options = decompressed.get("options", {})
                self.ap_slot_yaml_formats = decompressed.get("formats")
                
                yaml_size = len(self.ap_slot_yaml) if self.ap_slot_yaml else 0
                logger.info(f"[YAML Viewer] Successfully decompressed ap_slot_meta_yaml_info: {yaml_size} chars")
                logger.info(f"[YAML Viewer] ap_slot_options available: {bool(self.ap_slot_options)}")
                logger.info(f"[YAML Viewer] ap_slot_yaml_formats available: {bool(self.ap_slot_yaml_formats)}")
            except Exception as e:
                logger.error(f"[YAML Viewer] Failed to decompress ap_slot_meta_yaml_info: {e}")
                self.ap_slot_yaml = None
                self.ap_slot_options = None
                self.ap_slot_yaml_formats = None
        else:
            # No compressed data found
            logger.warning("[YAML Viewer] ap_slot_meta_yaml_info not found in slot_data")
    
    def _decompress_yaml_metadata(self, compressed_string: str) -> Dict[str, Any]:
        """Decompress YAML metadata from base64-encoded gzip string.
        
        Args:
            compressed_string: Base64-encoded gzipped JSON
        
        Returns:
            Dict with 'yaml', 'options', and 'formats' keys
        """
        try:
            # Decode from base64
            compressed = base64.b64decode(compressed_string.encode('ascii'))
            
            # Decompress with gzip
            json_str = gzip.decompress(compressed).decode('utf-8')
            
            # Parse JSON
            metadata = json.loads(json_str)
            
            logger.info(f"[YAML Viewer] Decompressed metadata: {len(compressed)} bytes → {len(json_str)} chars")
            return metadata
        except Exception as e:
            logger.error(f"[YAML Viewer] Failed to decompress YAML metadata: {e}", exc_info=True)
            raise
    
    async def quick_swap(self, new_slot_name: str, password: Optional[str] = None) -> bool:
        """Quickly switch to a different slot by disconnecting and reconnecting.
        
        Archipelago only allows one slot per WebSocket connection, so to swap slots
        we must: close current connection → establish new connection → authenticate new slot.
        
        Args:
            new_slot_name: Name of the new slot
            password: Optional new password (uses cached if not provided)
        
        Returns:
            True if successful
        """
        if not self.websocket or self.connection_state != "authenticated":
            logger.error("[YAML Viewer] Not connected to server")
            return False
        
        try:
            # Use provided password or cached password
            use_password = password if password is not None else self.password
            
            logger.info(f"[YAML Viewer] Initiating quick swap to slot '{new_slot_name}'")
            
            # Step 1: Cancel keep-alive listener and close current connection
            logger.info("[YAML Viewer] Closing current connection for slot swap...")
            if self._keep_alive_task:
                self._keep_alive_task.cancel()
                try:
                    await self._keep_alive_task
                except asyncio.CancelledError:
                    pass
                self._keep_alive_task = None
            
            # Close current websocket
            if self.websocket:
                try:
                    await asyncio.wait_for(self.websocket.close(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("[YAML Viewer] Timeout closing websocket during swap")
                except Exception as e:
                    logger.warning(f"[YAML Viewer] Error closing websocket: {e}")
                self.websocket = None
            
            # Step 2: Create fresh WebSocket connection to same server
            uri = f"ws://{self.server_address.rsplit(':', 1)[0] if ':' in self.server_address else self.server_address}:{self.port}"
            logger.info(f"[YAML Viewer] Establishing new connection to {uri}...")
            try:
                self.websocket = await asyncio.wait_for(
                    websockets.connect(uri),
                    timeout=5.0
                )
                logger.info("[YAML Viewer] New WebSocket connection established")
            except asyncio.TimeoutError:
                logger.error("[YAML Viewer] Timeout connecting to server during swap")
                return False
            except Exception as e:
                logger.error(f"[YAML Viewer] Failed to connect to server during swap: {e}")
                return False
            
            # Step 3: Get room info on fresh connection
            logger.info("[YAML Viewer] Getting room info on new connection...")
            if not await self._receive_room_info():
                logger.error("[YAML Viewer] Failed to receive room info during swap")
                self.websocket = None
                return False
            
            # Step 4: Authenticate to new slot
            logger.info(f"[YAML Viewer] Authenticating to new slot '{new_slot_name}'...")
            if not await self._retrieve_slot_data(new_slot_name, use_password):
                logger.error(f"[YAML Viewer] Failed to authenticate to slot '{new_slot_name}'")
                self.websocket = None
                return False
            
            # Step 5: Update state and restart keep-alive listener
            self.slot_name = new_slot_name
            self.password = use_password
            self.connection_state = "authenticated"
            
            logger.info(f"[YAML Viewer] Successfully swapped to '{new_slot_name}'")
            if self.ui_callback:
                self.ui_callback("swapped", {"slot": new_slot_name})
            
            # Restart keep-alive listener with new connection
            logger.info("[YAML Viewer] Starting keep-alive listener on new connection")
            self._keep_alive_task = asyncio.create_task(self._keep_alive_listener())
            return True
            
        except Exception as e:
            logger.error(f"[YAML Viewer] Quick swap failed: {e}", exc_info=True)
            self.connection_state = "disconnected"
            self.websocket = None
            
            if self.ui_callback:
                self.ui_callback("swap_failed", {"slot": new_slot_name, "error": str(e)})
            
            return False
    
    async def _disconnect(self) -> None:
        """Disconnect from server (runs in event loop)."""
        try:
            # Cancel keep-alive listener if running
            if self._keep_alive_task:
                self._keep_alive_task.cancel()
                try:
                    await self._keep_alive_task
                except asyncio.CancelledError:
                    pass
                self._keep_alive_task = None
            
            # Close websocket
            if self.websocket:
                try:
                    await asyncio.wait_for(self.websocket.close(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("[YAML Viewer] Timeout closing websocket, forcing close")
                except Exception:
                    pass  # Ignore errors during close
                self.websocket = None
            
            self.connection_state = "disconnected"
            self.slot_data = None
            self.ap_slot_yaml = None
            logger.info("[YAML Viewer] Disconnected from server")
        except Exception as e:
            logger.error(f"[YAML Viewer] Error during disconnect: {e}", exc_info=True)
    
    def disconnect(self) -> None:
        """Public method to disconnect (thread-safe)."""
        try:
            if self.event_loop:
                future = asyncio.run_coroutine_threadsafe(self._disconnect(), self.event_loop)
                future.result(timeout=5.0)  # Wait for disconnect to complete
            logger.info("[YAML Viewer] Disconnect scheduled")
        except Exception as e:
            logger.error(f"[YAML Viewer] Failed to schedule disconnect: {e}")
            # Force cleanup if scheduling failed
            self.connection_state = "disconnected"
            self.websocket = None
    
    def _generate_yaml_with_annotations(self) -> str:
        """Generate YAML with comments showing which options were changed by randomization.
        
        Compares ap_slot_yaml (original) with ap_slot_options (actual values) to detect changes.
        Adds comments above changed options indicating what the original/randomized values were.
        
        Returns:
            YAML string with annotation comments for changed options
        """
        if not self.ap_slot_yaml:
            return "No YAML data available"
        
        if not self.ap_slot_options:
            logger.info("[YAML Viewer] No ap_slot_options available, displaying original YAML")
            return self.ap_slot_yaml
        
        try:
            import yaml
            
            # Parse original YAML to get the structure
            original_data = yaml.safe_load(self.ap_slot_yaml)
            if not isinstance(original_data, dict):
                logger.warning("[YAML Viewer] Original YAML is not a dict, displaying as-is")
                return self.ap_slot_yaml
            
            # Track which options were changed
            changed_options = {}
            
            # Compare each option in ap_slot_options with original values
            for option_name, new_value in self.ap_slot_options.items():
                if option_name in original_data:
                    original_value = original_data[option_name]
                    if original_value != new_value:
                        changed_options[option_name] = {
                            "original": original_value,
                            "new": new_value
                        }
                        logger.info(f"[YAML Viewer] Option '{option_name}' changed: {original_value} → {new_value}")
            
            if not changed_options:
                logger.info("[YAML Viewer] No options were changed by randomization")
                return self.ap_slot_yaml
            
            # Rebuild YAML with annotations for changed options
            lines = self.ap_slot_yaml.split('\n')
            annotated_lines = []
            
            for line in lines:
                # Check if this line defines an option that was changed
                option_found = False
                for option_name in changed_options.keys():
                    # Look for lines like "option_name: value"
                    if line.strip().startswith(f"{option_name}:"):
                        change_info = changed_options[option_name]
                        comment = f"# Changed by randomization: {change_info['original']} → {change_info['new']}"
                        annotated_lines.append(comment)
                        option_found = True
                        break
                
                annotated_lines.append(line)
            
            result = '\n'.join(annotated_lines)
            logger.info(f"[YAML Viewer] Generated annotated YAML with {len(changed_options)} changes noted")
            return result
            
        except ImportError:
            logger.warning("[YAML Viewer] PyYAML not available, displaying original YAML")
            return self.ap_slot_yaml
        except Exception as e:
            logger.error(f"[YAML Viewer] Error generating annotated YAML: {e}", exc_info=True)
            return self.ap_slot_yaml
    
    def download_yaml(self, filepath: Optional[str] = None) -> bool:
        """Download/save the current YAML to a file.
        
        Args:
            filepath: Full file path to save to (uses Downloads if not provided)
        
        Returns:
            True if successful
        """
        if not self.ap_slot_yaml:
            logger.warning("[YAML Viewer] No YAML data available to download")
            return False
        
        try:
            if not filepath:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{self.slot_name}_{timestamp}.yaml"
                # Determine save location
                filepath = os.path.join(os.path.expanduser("~"), "Downloads", filename)
            
            logger.info(f"[YAML Viewer] Saving YAML to {filepath}")
            
            with open(filepath, "w") as f:
                f.write(self.ap_slot_yaml)
            
            file_size = len(self.ap_slot_yaml)
            logger.info(f"[YAML Viewer] YAML downloaded successfully ({file_size} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"[YAML Viewer] Failed to download YAML: {e}", exc_info=True)
            return False


class YAMLViewerApp(MDApp):
    """KivyMD application for YAML Viewer using Archipelago styling."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = YAMLViewerClient()
        self.client.ui_callback = self.on_client_event
        self.title = "Archipelago YAML Viewer"
    
    def build(self):
        """Build the UI using KivyMD theme - programmatic approach."""
        # Set KivyMD theme - matches Archipelago client styling
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Lightsteelblue"
        
        Window.size = (1000, 800)
        
        # Build UI programmatically (no KV file)
        main_layout = MDBoxLayout(orientation="vertical", padding="12dp", spacing="10dp")
        main_layout.md_bg_color = self.theme_cls.backgroundColor
        
        # Store widget references - use a simple namespace object
        class WidgetRefs:
            pass
        
        refs = WidgetRefs()
        
        # Title
        title = MDLabel(
            text="[b]Archipelago YAML Viewer[/b]",
            markup=True,
            font_size="28sp",
            size_hint_y=None,
            height="50dp",
            theme_text_color="Custom",
            text_color=self.theme_cls.primaryColor
        )
        main_layout.add_widget(title)
        
        # Connection section - vertical layout with labels
        conn_card = MDCard(
            orientation="vertical",
            padding="15dp",
            spacing="12dp",
            size_hint_y=None,
            height="130dp",
            md_bg_color=self.theme_cls.surfaceContainerColor
        )
        
        # Input row 1: Server
        row1 = MDBoxLayout(size_hint_y=0.5, spacing="10dp")
        row1.add_widget(MDLabel(text="Server:", size_hint_x=0.15, font_size="13sp", theme_text_color="Custom", text_color=self.theme_cls.primaryColor))
        refs.server_input = MDTextField(
            hint_text="localhost:38281",
            size_hint_x=0.85,
            mode="filled",
            font_size="13sp",
            multiline=False
        )
        row1.add_widget(refs.server_input)
        conn_card.add_widget(row1)
        
        # Input row 2: Slot and Password
        row2 = MDBoxLayout(size_hint_y=0.5, spacing="10dp")
        row2.add_widget(MDLabel(text="Slot:", size_hint_x=0.1, font_size="13sp", theme_text_color="Custom", text_color=self.theme_cls.primaryColor))
        refs.slot_input = MDTextField(
            hint_text="Slot name",
            size_hint_x=0.4,
            mode="filled",
            font_size="13sp",
            multiline=False
        )
        row2.add_widget(refs.slot_input)
        
        row2.add_widget(MDLabel(text="Pass:", size_hint_x=0.1, font_size="13sp", theme_text_color="Custom", text_color=self.theme_cls.primaryColor))
        refs.password_input = MDTextField(
            hint_text="(optional)",
            password=True,
            size_hint_x=0.4,
            mode="filled",
            font_size="13sp",
            multiline=False
        )
        row2.add_widget(refs.password_input)
        
        refs.connect_btn = MDButton(style="elevated", theme_width="Custom", size_hint_x=None, width="120dp")
        refs.connect_btn.add_widget(MDButtonText(text="Connect", font_size="16sp"))
        row2.add_widget(refs.connect_btn)
        
        conn_card.add_widget(row2)
        
        main_layout.add_widget(conn_card)
        
        # Quick swap section
        swap_card = MDCard(
            orientation="horizontal",
            padding="15dp",
            spacing="15dp",
            size_hint_y=None,
            height="75dp",
            md_bg_color=self.theme_cls.surfaceContainerColor
        )
        
        swap_label = MDLabel(
            text="Quick Swap:",
            size_hint_x=0.12,
            font_size="14sp",
            theme_text_color="Custom",
            text_color=self.theme_cls.primaryColor
        )
        swap_card.add_widget(swap_label)
        
        refs.quick_swap_input = MDTextField(
            hint_text="New slot",
            size_hint_x=0.3,
            mode="filled",
            font_size="13sp",
            multiline=False
        )
        swap_card.add_widget(refs.quick_swap_input)
        
        pass_label = MDLabel(
            text="Pass:",
            size_hint_x=0.08,
            font_size="14sp",
            theme_text_color="Custom",
            text_color=self.theme_cls.primaryColor
        )
        swap_card.add_widget(pass_label)
        
        refs.swap_password_input = MDTextField(
            hint_text="(optional)",
            password=True,
            size_hint_x=0.3,
            mode="filled",
            font_size="13sp",
            multiline=False
        )
        swap_card.add_widget(refs.swap_password_input)
        
        refs.swap_btn = MDButton(style="elevated", theme_width="Custom", size_hint_x=None, width="100dp")
        refs.swap_btn.add_widget(MDButtonText(text="Swap", font_size="16sp"))
        swap_card.add_widget(refs.swap_btn)
        
        main_layout.add_widget(swap_card)
        
        # Status line
        refs.status_label = MDLabel(
            text="[color=ff7700]Disconnected[/color]",
            markup=True,
            size_hint_y=None,
            height="32dp",
            font_size="14sp",
            theme_text_color="Custom",
            text_color=self.theme_cls.onBackgroundColor
        )
        main_layout.add_widget(refs.status_label)
        
        main_layout.add_widget(MDDivider(size_hint_y=None, height="2dp"))
        
        # YAML display - use size_hint_y to fill available space
        scroll_view = MDScrollView(size_hint_y=1)
        refs.yaml_display = MDTextField(
            text="Connect to a server to view YAML",
            multiline=True,
            readonly=True,
            mode="filled",
            font_size="12sp"
        )
        scroll_view.add_widget(refs.yaml_display)
        main_layout.add_widget(scroll_view)
        
        # Action buttons - card container with properly sized buttons using theme_width="Custom"
        button_card = MDCard(
            orientation="vertical",
            padding="20dp",
            spacing="20dp",
            size_hint_y=None,
            height="200dp",
            md_bg_color=self.theme_cls.surfaceContainerColor
        )
        
        # First row: Download and Metadata buttons (split 50/50)
        button_row1 = MDBoxLayout(orientation="horizontal", size_hint_y=None, height="75dp", spacing="20dp")
        
        refs.download_btn = MDButton(
            style="elevated",
            theme_width="Custom",
            size_hint_x=0.5,
            size_hint_y=None,
            height="75dp"
        )
        refs.download_btn.add_widget(MDButtonText(text="Download", font_size="22sp"))
        button_row1.add_widget(refs.download_btn)
        
        refs.metadata_btn = MDButton(
            style="elevated",
            theme_width="Custom",
            size_hint_x=0.5,
            size_hint_y=None,
            height="75dp"
        )
        refs.metadata_btn.add_widget(MDButtonText(text="Metadata", font_size="22sp"))
        button_row1.add_widget(refs.metadata_btn)
        
        button_card.add_widget(button_row1)
        
        # Second row: Disconnect button (full width)
        button_row2 = MDBoxLayout(orientation="horizontal", size_hint_y=None, height="75dp", spacing="20dp")
        
        refs.disconnect_btn = MDButton(
            style="elevated",
            theme_width="Custom",
            size_hint_x=1,
            size_hint_y=None,
            height="75dp"
        )
        refs.disconnect_btn.add_widget(MDButtonText(text="Disconnect", font_size="22sp"))
        button_row2.add_widget(refs.disconnect_btn)
        
        button_card.add_widget(button_row2)
        
        main_layout.add_widget(button_card)
        
        # Store refs on root for later access (as an attribute, not Kivy's ids dict)
        main_layout.widget_refs = refs
        
        # Bind buttons immediately since we have direct references
        self._bind_ui_elements_direct(refs)
        
        return main_layout
    
    def _bind_ui_elements_direct(self, refs):
        """Bind UI elements directly from refs object."""
        try:
            button_bindings = {
                'connect_btn': self.on_connect,
                'swap_btn': self.on_quick_swap,
                'download_btn': self.on_download,
                'metadata_btn': self.on_show_metadata,
                'disconnect_btn': self.on_disconnect
            }
            
            for btn_id, handler in button_bindings.items():
                try:
                    btn = getattr(refs, btn_id, None)
                    if btn:
                        btn.bind(on_release=handler)
                        logger.info(f"[YAML Viewer] Bound {btn_id} successfully")
                    else:
                        logger.warning(f"[YAML Viewer] Button {btn_id} not found")
                except Exception as e:
                    logger.warning(f"[YAML Viewer] Failed to bind {btn_id}: {e}")
            
            # Store refs on app for later access
            self.widget_refs = refs
            logger.info("[YAML Viewer] UI element binding complete")
        except Exception as e:
            logger.warning(f"[YAML Viewer] Could not bind UI elements: {e}", exc_info=True)
    
    def on_connect(self, instance):
        """Handle connect button press."""
        server = self.widget_refs.server_input.text.strip() or "localhost:38281"
        slot = self.widget_refs.slot_input.text.strip()
        password = self.widget_refs.password_input.text.strip()
        
        if not slot:
            self.widget_refs.status_label.text = "[color=EE0000]Please enter a slot name[/color]"
            return
        
        # Run connection in background thread using event loop
        def connect_thread():
            try:
                if self.client.event_loop:
                    future = asyncio.run_coroutine_threadsafe(self.client.connect(server, slot, password), self.client.event_loop)
                    result = future.result(timeout=10.0)
                else:
                    self.widget_refs.status_label.text = "[color=EE0000]Event loop not available[/color]"
                    return
            except Exception as e:
                logger.error(f"[YAML Viewer] Connection error: {e}", exc_info=True)
                Clock.schedule_once(lambda dt: self._on_connect_error(str(e)), 0)
        
        thread = threading.Thread(target=connect_thread, daemon=True)
        thread.start()
    
    def _on_connect_error(self, error: str) -> None:
        """Called when connection fails (main thread)."""
        self.widget_refs.status_label.text = f"[color=EE0000]Connection error: {error[:40]}...[/color]"
    
    def on_quick_swap(self, instance):
        """Handle quick swap button press."""
        if self.client.connection_state != "authenticated":
            self.widget_refs.status_label.text = "[color=EE0000]Not connected to a server[/color]"
            return
        
        new_slot = self.widget_refs.quick_swap_input.text.strip()
        if not new_slot:
            self.widget_refs.status_label.text = "[color=EE0000]Please enter a slot name[/color]"
            return
        
        new_password = self.widget_refs.swap_password_input.text.strip() if self.widget_refs.swap_password_input else None
        
        # Run swap in background thread using event loop
        def swap_thread():
            try:
                if self.client.event_loop:
                    future = asyncio.run_coroutine_threadsafe(self.client.quick_swap(new_slot, new_password), self.client.event_loop)
                    result = future.result(timeout=10.0)
                else:
                    logger.error("[YAML Viewer] Event loop not available")
                    Clock.schedule_once(lambda dt: self._on_swap_failed({"slot": new_slot, "error": "Event loop not available"}), 0)
            except Exception as e:
                logger.error(f"[YAML Viewer] Swap error: {e}", exc_info=True)
                Clock.schedule_once(lambda dt: self._on_swap_error(str(e)), 0)
        
        thread = threading.Thread(target=swap_thread, daemon=True)
        thread.start()
    
    def _on_swap_error(self, error: str) -> None:
        """Called when swap encounters error (main thread)."""
        self.widget_refs.status_label.text = f"[color=EE0000]Swap error: {error[:40]}...[/color]"
    
    def on_download(self, instance):
        """Handle download button press - open file chooser."""
        if not self.client.ap_slot_yaml:
            self.widget_refs.status_label.text = "[color=EE0000]No YAML data available to download[/color]"
            return
        
        # Create file chooser dialog
        content = MDBoxLayout(orientation="vertical", spacing=10, padding=10)
        
        # Current path display
        path_label = MDLabel(
            text=f"Saving to: {os.path.expanduser('~')}",
            size_hint_y=0.08,
            font_size="12sp",
            theme_text_color="Custom",
            text_color=self.theme_cls.primaryColor
        )
        content.add_widget(path_label)
        
        # File chooser
        file_chooser = FileChooserListView(
            filters=['*.yaml', '*.yml'],
            path=os.path.expanduser("~"),
        )
        
        # Bind path changes to update the label
        def update_path(instance, value):
            path_label.text = f"Saving to: {file_chooser.path}"
        
        file_chooser.bind(path=update_path)
        content.add_widget(file_chooser)
        
        # Filename input
        filename_box = MDBoxLayout(size_hint_y=0.12, spacing=10)
        filename_box.add_widget(MDLabel(text="Filename:", size_hint_x=0.2))
        
        default_name = f"{self.client.slot_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
        filename_input = MDTextField(
            text=default_name,
            size_hint_x=0.8,
            mode="filled"
        )
        filename_box.add_widget(filename_input)
        content.add_widget(filename_box)
        
        # Buttons
        button_box = MDBoxLayout(size_hint_y=0.12, spacing=10)
        
        def on_save(btn):
            # Combine path and filename
            filepath = os.path.join(file_chooser.path, filename_input.text)
            if self.client.download_yaml(filepath):
                self.widget_refs.status_label.text = f"[color=00FF7F]Downloaded: {os.path.basename(filepath)}[/color]"
                popup.dismiss()
            else:
                self.widget_refs.status_label.text = "[color=EE0000]Failed to save YAML[/color]"
        
        def on_cancel(btn):
            popup.dismiss()
        
        save_btn = MDButton(style="elevated")
        save_btn.add_widget(MDButtonText(text="Save"))
        save_btn.bind(on_release=on_save)
        
        cancel_btn = MDButton(style="elevated")
        cancel_btn.add_widget(MDButtonText(text="Cancel"))
        cancel_btn.bind(on_release=on_cancel)
        
        button_box.add_widget(save_btn)
        button_box.add_widget(cancel_btn)
        content.add_widget(button_box)
        
        # Create popup
        popup = Popup(title="Save YAML", content=content, size_hint=(0.9, 0.9))
        popup.open()
    
    def on_show_metadata(self, instance):
        """Show format metadata in a popup."""
        if not self.client.ap_slot_yaml_formats:
            self.widget_refs.status_label.text = "[color=FF7700]No metadata available[/color]"
            return
        
        metadata = self.client.ap_slot_yaml_formats
        
        # Format metadata for display
        text = "[b]=== YAML Format Metadata ===[/b]\n\n"
        text += f"Format Type: {metadata.get('format_type', 'unknown')}\n"
        text += f"Multi-Document: {metadata.get('is_multi_document', False)}\n"
        text += f"Document Count: {metadata.get('document_count', 1)}\n\n"
        
        if metadata.get('randomization_types'):
            text += "[b]Randomization Types:[/b]\n"
            for rand_type in metadata['randomization_types']:
                text += f"  • {rand_type}\n"
            text += "\n"
        
        if metadata.get('randomization_metadata'):
            text += "[b]Randomization Details:[/b]\n"
            for field, info in metadata['randomization_metadata'].items():
                text += f"  [b]{field}:[/b]\n"
                text += f"    Type: {info.get('randomization_type', 'unknown')}\n"
                text += f"    Options: {info.get('option_count', 'unknown')}\n"
                if info.get('total_weight'):
                    text += f"    Total Weight: {info['total_weight']}\n"
                text += "\n"
        
        popup = Popup(title="YAML Metadata", size_hint=(0.85, 0.85))
        content = MDBoxLayout(orientation="vertical", padding=10, spacing=10)
        
        text_display = MDTextField(text=text, multiline=True, readonly=True, mode="filled", font_size="12sp")
        content.add_widget(text_display)
        
        close_btn = MDButton(style="elevated")
        close_btn.add_widget(MDButtonText(text="Close"))
        close_btn.bind(on_release=popup.dismiss)
        content.add_widget(close_btn)
        
        popup.content = content
        popup.open()
    
    def on_disconnect(self, instance):
        """Handle disconnect button press."""
        def disconnect_thread():
            try:
                self.client.disconnect()  # Use public method which handles event loop
                # Schedule UI update on main thread
                Clock.schedule_once(lambda dt: self._on_disconnected(), 0)
            except Exception as e:
                logger.error(f"[YAML Viewer] Disconnect error: {e}")
                Clock.schedule_once(lambda dt: self._on_disconnect_error(str(e)), 0)
        
        threading.Thread(target=disconnect_thread, daemon=True).start()
    
    def _on_disconnected(self) -> None:
        """Called when disconnect completes (main thread)."""
        self.widget_refs.status_label.text = "[color=FF7700]Disconnected[/color]"
        self.update_ui()
    
    def _on_disconnect_error(self, error: str) -> None:
        """Called when disconnect fails (main thread)."""
        self.widget_refs.status_label.text = f"[color=EE0000]Disconnect error: {error[:40]}...[/color]"
        logger.error(f"[YAML Viewer] Disconnect error: {error}")
    
    def on_client_event(self, event: str, data: Dict[str, Any]) -> None:
        """Handle client events (called from network thread, schedule on main thread)."""
        if event == "connected":
            Clock.schedule_once(lambda dt: self._on_connected(data), 0)
        elif event == "swapped":
            Clock.schedule_once(lambda dt: self._on_swapped(data), 0)
        elif event == "swap_failed":
            Clock.schedule_once(lambda dt: self._on_swap_failed(data), 0)
    
    def _on_connected(self, data: Dict[str, Any]) -> None:
        """Update UI when connected (main thread)."""
        self.widget_refs.status_label.text = f"[color=00FF7F]Connected to {self.client.slot_name}[/color]"
        self.update_ui()
    
    def _on_swapped(self, data: Dict[str, Any]) -> None:
        """Update UI when slot swapped (main thread)."""
        self.widget_refs.status_label.text = f"[color=00FF7F]Swapped to {self.client.slot_name}[/color]"
        self.update_ui()
        self.widget_refs.quick_swap_input.text = ""
    
    def _on_swap_failed(self, data: Dict[str, Any]) -> None:
        """Update UI when swap fails (main thread)."""
        self.widget_refs.status_label.text = f"[color=EE0000]Failed to swap to {data.get('slot', 'unknown')}[/color]"
    
    def update_ui(self) -> None:
        """Update UI with current client data (must be called on main thread)."""
        if self.client.ap_slot_yaml:
            # Generate YAML with annotations for changed options
            annotated_yaml = self.client._generate_yaml_with_annotations()
            self.widget_refs.yaml_display.text = annotated_yaml
        else:
            self.widget_refs.yaml_display.text = "No YAML data available"
    
    def on_stop(self):
        """Clean up when app closes."""
        try:
            if self.client and self.client.connection_state == "authenticated":
                self.client.disconnect()  # Use public method which handles event loop
                logger.info("[YAML Viewer] Disconnected on app close")
        except Exception as e:
            logger.error(f"[YAML Viewer] Error closing connection: {e}")


def run_yaml_viewer():
    """Run the YAML Viewer application."""
    app = YAMLViewerApp()
    app.run()


def launch(*args):
    """Launch function for Archipelago Launcher integration."""
    run_yaml_viewer()


if __name__ == "__main__":
    run_yaml_viewer()
