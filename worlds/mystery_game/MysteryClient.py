"""Mystery Client: MysteryContext + RelayContexts + proxy for locked slots."""

import asyncio
import functools
import logging
import socket
import time
from typing import Any, Dict, List, Optional, Set

from CommonClient import (
    ClientCommandProcessor,
    CommonContext,
    async_start,
    get_base_parser,
    gui_enabled,
    handle_url_arg,
    server_loop,
)
from NetUtils import decode, encode

from .cache import (
    MYSTERY_GLOBAL_HOST,
    MYSTERY_GLOBAL_PORT,
    MYSTERY_PROXY_HOST,
    MYSTERY_PROXY_PORT,
    NUZLOCKE_PREFIX,
    cache_key,
    check_guess,
    merge_held_items,
    merge_pending_checks,
    merge_puzzle_state,
    new_cache_entry,
    normalize_cache_entry,
    normalize_puzzle_state,
    nuzlocke_extra_key,
    nuzlocke_key,
    parse_puzzle_hint,
    parse_puzzle_piece,
    proxy_instructions,
    puzzle_ready,
    puzzle_state_key,
    set_operation,
    unlocks_key,
)
from .puzzles import EXTRA_LIFE_ITEM, puzzle_location_name

logger = logging.getLogger("Mystery")
client_logger = logging.getLogger("Client")

LOCK_OFF: int = 0
LOCK_FROZEN: int = 1
LOCK_GUESS: int = 2
LOCK_BOTH: int = 3

CHEESE_GAME: str = "Mystery Cheese"

def find_free_port(host: str, start_port: int, max_tries: int = 50) -> int:
    """Find a free TCP port."""
    for offset in range(max_tries):
        port = start_port + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host if host != "0.0.0.0" else "127.0.0.1", port))
            return port
        except OSError:
            continue
    return start_port

class MysteryCommandProcessor(ClientCommandProcessor):
    """Chat commands."""

    def __call__(self, raw: str) -> bool | None:
        if raw.startswith("!mystery_"):
            return super().__call__("/" + raw[1:])
        return super().__call__(raw)

    def default(self, raw: str) -> None:
        """Send chat via active relay."""
        ctx: Any = self.ctx
        if isinstance(ctx, MysteryContext):
            relay = ctx.relay_for_chat()
            if relay is not None:
                text: Any = ctx.on_user_say(raw)
                if text:
                    async_start(relay.send_msgs([{"cmd": "Say", "text": text}]),
                                name="send Say via relay")
                return
        super().default(raw)

    def _cmd_mystery_status(self) -> bool:
        """Show status."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        self.output(f"Lock mode: {ctx.lock_mode_name()}")
        if ctx.game == CHEESE_GAME:
            self.output("MYSTERY CHEESE MODE ACTIVE")
        locked: List[str] = ctx.locked_slots()
        self.output(f"Locked slots: {len(locked)} | Unlocked: {len(ctx.unlocked_slots)}")
        for slot in sorted(ctx.real_slots):
            state: str = f"unlocked ({ctx.unlocked_slots[slot]})" if slot in ctx.unlocked_slots else "LOCKED"
            if ctx.nuzlocke_enabled:
                lives = ctx.get_nuzlocke_lives(slot)
                hits = ctx.get_nuzlocke_hits(slot)
                if slot in ctx.nuzlocke_dead:
                    state += f" – DEAD ({hits}/{lives})"
                elif hits > 0:
                    state += f" – {hits}/{lives} hits ({lives - hits} left)"
                elif lives != 1:
                    state += f" – {lives} lives"
            self.output(f"  {slot} [{ctx.shown_game(slot)}] - {state}")
        if ctx.nuzlocke_enabled:
            self.output(f"Nuzlocke: {ctx.nuzlocke_lives} lives default (per-slot overrides: {len(ctx.nuzlocke_lives_per_slot)})")
        return True

    def _cmd_mystery_solve(self, puzzle: str) -> bool:
        """Disabled."""
        self.output("Puzzles are currently disabled.")
        return False

    def _cmd_mystery_puzzle(self, puzzle: str) -> bool:
        """Disabled."""
        self.output("Puzzles are currently disabled.")
        return False

    def _cmd_mystery_hint(self, puzzle: str) -> bool:
        """Disabled."""
        self.output("Puzzles are currently disabled.")
        return False

    def _cmd_mystery_unlock(self, slot: str) -> bool:
        """Unlock a slot."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        revealed: Optional[str] = ctx.reveal_unlock(slot)
        if revealed is None:
            self.output(f"No unlock matching {slot!r}.")
            return False
        self.output(f"Unlocked: {revealed}")
        return True

    def _cmd_mystery_slots(self) -> bool:
        """List slots."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        for slot in sorted(ctx.real_slots):
            if slot in ctx.unlocked_slots:
                self.output(f"  {slot} = {ctx.real_slots[slot]} (unlocked)")
            elif ctx.guessable():
                self.output(f"  {slot} = ? (guess with !mystery_guess {slot} <game>)")
            else:
                self.output(f"  {slot} = {ctx.shown_game(slot)} (locked)")
        for slot in sorted(ctx.untouched_slots):
            self.output(f"  {slot} = {ctx.untouched_slots[slot]} (untouched, connect directly)")
        return True

    def _cmd_mystery_guess(self, slot: str, game: str) -> bool:
        """Guess a game."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        result: Optional[str] = ctx.submit_guess(slot, game)
        self.output(result if result else f"No slot matching {slot!r}.")
        return True

    def _cmd_mystery_relay(self, slot: str = "") -> bool:
        """Connect relay."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        if not slot:
            if not ctx.relays:
                self.output("No relays running.")
            for name, relay in ctx.relays.items():
                marker: str = " (talking)" if ctx.active_relay == name else ""
                state: str = "online" if ctx._relay_online(relay) else "connecting"
                self.output(f"  {name}: {state}{marker}")
            return True
        result: Optional[str] = ctx.start_relay(slot, via_command=True)
        self.output(result if result else f"No slot matching {slot!r}.")
        return True

    def _cmd_mystery_unrelay(self, slot: str = "") -> bool:
        """Disconnect relay."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        if not slot or slot.strip().lower() == "all":
            running: list = sorted(ctx.relays)
            if not running:
                self.output("No relays running.")
                return True
            for name in running:
                result = ctx.stop_relay(name)
                self.output(result if result else f"No slot matching {name!r}.")
            return True
        result = ctx.stop_relay(slot)
        self.output(result if result else f"No slot matching {slot!r}.")
        return True

    def _cmd_mystery_proxy(self, action: str = "") -> bool:
        """Proxy control."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        if action == "start":
            async_start(ctx.start_proxy())
            self.output("Starting proxy listener...")
            return True
        if action == "stop":
            async_start(ctx.stop_proxy())
            self.output("Stopping proxy listener...")
            return True
        self.output(ctx.proxy_help())
        return True

    def _cmd_mystery_aliases(self) -> bool:
        """Print aliases."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        shown: bool = False
        for slot in sorted(ctx.real_slots):
            real_name: str = ctx.identities.get(slot, {}).get("name", slot)
            if slot in ctx.unlocked_slots and real_name != slot:
                self.output(f"!alias {slot} {real_name}")
                shown = True
        if not shown:
            self.output("No unlocked scrambled slots to reveal.")
        return True

    def _cmd_mystery_global(self, action: str = "", value: str = "") -> bool:
        """Global bridge control."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        if not action or action.lower() in ("status", "show"):
            state = "ON" if ctx.global_bridge_enabled else "OFF"
            gport = ctx.global_bridge_port
            grunning = ctx.global_bridge.running if ctx.global_bridge else False
            self.output(f"Global bridge: {state} port {gport} ({'running' if grunning else 'stopped'})")
            if ctx.global_bridge:
                for slot, port in sorted(ctx.global_bridge.slot_ports.items()):
                    self.output(f"  {slot} -> :{port} (global)")
            if ctx.proxy:
                for slot, port in sorted(ctx.proxy.slot_ports.items()):
                    self.output(f"  {slot} -> :{port} (proxy)")
            return True
        if action.lower() in ("on", "enable", "start"):
            ctx.global_bridge_enabled = True
            async_start(ctx.start_global_bridge())
            self.output(f"Global bridge ON port {ctx.global_bridge_port} (tunnel this for broadcast)")
            return True
        if action.lower() in ("off", "disable", "stop"):
            ctx.global_bridge_enabled = False
            async_start(ctx.stop_global_bridge())
            self.output("Global bridge OFF")
            return True
        if action.lower() in ("port", "set_port"):
            try:
                p = int(value)
                if not (1024 <= p <= 65535):
                    raise ValueError
                ctx.global_bridge_port = p
                self.output(f"Global bridge port set to {p} (restart bridge to apply)")
                if ctx.global_bridge and ctx.global_bridge.running:
                    async_start(ctx.stop_global_bridge())
                    async_start(ctx.start_global_bridge())
                return True
            except Exception:
                self.output("Usage: !mystery_global port <1024-65535>")
                return False
        self.output("Usage: !mystery_global [on|off|status|port <num>]")
        return False

    def _cmd_mystery_ports(self) -> bool:
        """Show ports."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        shown = False
        if ctx.proxy:
            self.output(f"Proxy {ctx.proxy.host}:{ctx.proxy.port} ({'running' if ctx.proxy.running else 'stopped'})")
            for slot, port in sorted(ctx.proxy.slot_ports.items()):
                shown = True
                state = "FROZEN" if ctx.is_locked(slot) else "open"
                if slot in ctx.nuzlocke_dead:
                    state = "DEAD"
                self.output(f"  {slot} -> :{port} [{state}]")
        if ctx.global_bridge:
            self.output(f"Global {ctx.global_bridge.host}:{ctx.global_bridge.port} ({'running' if ctx.global_bridge.running else 'stopped'})")
            for slot, port in sorted(ctx.global_bridge.slot_ports.items()):
                shown = True
                state = "FROZEN" if ctx.is_locked(slot) else "open"
                if slot in ctx.nuzlocke_dead:
                    state = "DEAD"
                self.output(f"  {slot} -> :{port} [{state}] (global)")
        if not shown:
            self.output("No dedicated relay ports allocated yet (relays create on demand).")
        else:
            self.output("Use ws://<host>:<port> with alias as slot name.")
        return True

    def _cmd_mystery_proxy_port(self, port: str = "") -> bool:
        """Set proxy port."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        if not port:
            actual = ctx.proxy.port if ctx.proxy and getattr(ctx.proxy, "running", False) else getattr(ctx, "proxy_port", MYSTERY_PROXY_PORT)
            self.output(f"Proxy port: {actual} (main {MYSTERY_PROXY_HOST}:{actual})")
            if ctx.proxy:
                for slot, p in sorted(ctx.proxy.slot_ports.items()):
                    self.output(f"  {slot} -> :{p}")
            if ctx.global_bridge:
                self.output(f"Global bridge: {ctx.global_bridge.host}:{ctx.global_bridge.port} ({'running' if ctx.global_bridge.running else 'stopped'})")
                for slot, p in sorted(ctx.global_bridge.slot_ports.items()):
                    self.output(f"  {slot} -> :{p} (global)")
            return True
        try:
            p = int(port)
            if not (1024 <= p <= 65535):
                raise ValueError
            ctx.proxy_port = p
            if ctx.proxy and ctx.proxy.running:
                async_start(ctx.stop_proxy())
            async_start(ctx.start_proxy())
            self.output(f"Proxy port set to {p} (restarting, fallback if busy)")
            return True
        except Exception:
            self.output("Usage: !mystery_proxy_port <1024-65535>")
            return False

    def _cmd_mystery_sync(self) -> bool:
        """Send Sync."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        try:
            async_start(ctx.send_msgs([{"cmd": "Sync"}]))
            self.output("Mystery: Sync sent")
        except Exception as e:
            self.output(f"Mystery: Sync failed: {e}")
        count = 0
        for slot, relay in list(ctx.relays.items()):
            try:
                async_start(relay.send_msgs([{"cmd": "Sync"}]))
                count += 1
            except Exception as e:
                self.output(f"Relay {slot}: Sync failed: {e}")
        self.output(f"Relays: Sync sent to {count} relay(s)")
        return True

    def _cmd_mystery_forcesync(self) -> bool:
        """Alias for sync."""
        return self._cmd_mystery_sync()

    def _cmd_mystery_rewards(self) -> bool:
        """Show paired reward locations."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        if not getattr(ctx, "custom_goal_enabled", False):
            self.output("Custom goal not enabled.")
            return False
        pairs = getattr(ctx, "custom_goal_pairs", []) or []
        if not pairs:
            # fallback to internal_map
            im = getattr(ctx, "custom_goal_internal_map", {}) or {}
            if im:
                self.output(f"Reward pairs ({len(im)}) - token count gated, paired to source:")
                for src, rew in sorted(im.items()):
                    self.output(f"  {rew} -> {src} [paired={getattr(ctx,'custom_goal_reward_paired',False)}]")
                return True
            self.output("No reward pairs (no custom goal locations).")
            return True
        self.output(f"Reward pairs ({len(pairs)}) - each reward is logically paired to its source location:")
        for p in sorted(pairs, key=lambda x: x.get("index", 0)):
            src = p.get("source", "?")
            rew = p.get("reward", "?")
            pid = p.get("source_player")
            region = p.get("source_region", "?")
            game = p.get("source_game", "?")
            self.output(f"  {rew} -> {src} [p{pid} {game} @ {region}] requires can_reach(source) + tokens")
        if getattr(ctx, "custom_goal_reward_paired", False):
            self.output("Paired logic: rewards require reaching source area (e.g., dungeon) + token count - use for OoT key consistency")
        return True

    def _cmd_mystery_goal(self) -> bool:
        """Show custom goal status."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        if not getattr(ctx, "custom_goal_enabled", False):
            self.output("Custom goal not enabled.")
            return False
        locs = getattr(ctx, "custom_goal_locations", set())
        items = getattr(ctx, "custom_goal_items", {})
        self.output(f"Custom goal: {len(locs)} locations, {len(items)} item requirements, token={getattr(ctx,'custom_goal_token','?')}")
        for loc in sorted(locs)[:20]:
            rew = ctx.get_reward_for_source(loc) or "?"
            self.output(f"  GOAL: {loc} -> {rew}")
        if len(locs) > 20:
            self.output(f"  ... and {len(locs)-20} more")
        for name, cnt in items.items():
            self.output(f"  ITEM: {name} x{cnt}")
        self.output(f"Goal done: {getattr(ctx,'custom_goal_done',False)} paired={getattr(ctx,'custom_goal_reward_paired',False)}")
        return True

class MysteryContext(CommonContext):
    """Mystery slot context."""

    game: str = "Mystery Game"
    tags = CommonContext.tags | {"Mystery"}
    command_processor = MysteryCommandProcessor
    items_handling: int = 0b111
    max_size: int = 64*1024*1024

    def __init__(self, server_address: Optional[str], password: Optional[str]) -> None:
        super().__init__(server_address, password)
        self.puzzle_names: List[str] = []
        self.unlock_map: Dict[str, str] = {}
        self.solved_puzzles: set = set()
        self.revealed_unlocks: Dict[str, str] = {}
        self.lock_mode: int = LOCK_OFF
        self.real_slots: Dict[str, str] = {}
        self.untouched_slots: Dict[str, str] = {}
        self.identities: Dict[str, Dict[str, str]] = {}
        self.unlocked_slots: Dict[str, str] = {}
        self.scrambled: bool = False
        self.expose_proxied_items: bool = True
        self.puzzle_pieces: Dict[str, int] = {}
        self.puzzle_hints: Dict[str, List[str]] = {}
        self.puzzle_state: Dict[str, Dict[str, Any]] = {}
        self.caches: Dict[str, Dict[str, Any]] = {}
        self.relays: Dict[str, "RelayContext"] = {}
        self.active_relay: Optional[str] = None
        self.relay_disabled: set = set()
        self.nuzlocke_enabled: bool = False
        self.nuzlocke_deathlink: int = 0
        self.nuzlocke_per_game_modes: Dict[str, int] = {}
        self.nuzlocke_lives: int = 1
        self.nuzlocke_lives_per_slot: Dict[str, int] = {}
        self.nuzlocke_hits: Dict[str, int] = {}
        self.nuzlocke_extra_lives: int = 0
        self.nuzlocke_extra_distribution: int = 0
        self.nuzlocke_extra_assignments: List[str] = []
        self.nuzlocke_extra_earned: Dict[str, int] = {}
        self.nuzlocke_dead: set = set()
        self.proxy: Optional["MysteryProxy"] = None
        self.global_bridge: Optional["MysteryProxy"] = None
        self.global_bridge_enabled: bool = False
        self.global_bridge_port: int = 11400
        self.proxy_port: int = MYSTERY_PROXY_PORT
        self.mystery_tab: Any = None
        self.proxy_tab: Any = None
        self.relay_tracker_tab: Any = None
        self.custom_goal_enabled: bool = False
        self.custom_goal_locations: set = set()
        self.custom_goal_items: Dict[str, int] = {}
        self.custom_goal_any_items: bool = False
        self.custom_goal_tag: str = "mystery_custom_goal"
        self.custom_goal_token: str = "Mystery Goal Token"
        self.custom_goal_internal_map: Dict[str, str] = {}
        self.custom_goal_pairs: List[dict] = []
        self.custom_goal_reward_map: Dict[str, str] = {}
        self.custom_goal_reward_paired: bool = False
        self.custom_goal_done: bool = False
        self._cheese_tried: bool = False
        self._local_item_ids: Dict[str, int] = {}
        self._local_location_ids: Dict[str, int] = {}
        self._local_item_names: Dict[int, str] = {}
        self._last_roominfo: Dict[str, Any] = {}

    async def server_auth(self, password_requested: bool = False) -> None:
        """Authenticate."""
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect(name=self.auth, password=self.password)

    def event_invalid_game(self) -> None:
        """Retry as Mystery Cheese."""
        if self.game == "Mystery Game" and not self._cheese_tried:
            self._cheese_tried = True
            self.game = CHEESE_GAME
            client_logger.info("Mystery: standard identity refused; retrying as Mystery Cheese...")
            self.disconnected_intentionally = False
            async_start(self._cheese_reconnect())
            return
        super().event_invalid_game()

    async def _cheese_reconnect(self) -> None:
        await asyncio.sleep(1.0)
        try:
            await self.disconnect()
        except Exception:
            pass
        try:
            await self.connect()
        except Exception as exc:
            logger.warning("Mystery: cheese reconnect failed: %s", exc)

    def _ensure_local_datapackage(self) -> None:
        """Build local datapackage."""
        try:
            from .puzzles import build_item_name_to_id, build_location_name_to_id
            self._local_item_ids = dict(build_item_name_to_id())
            self._local_location_ids = dict(build_location_name_to_id())
            self._local_item_names = {code: name for name, code in self._local_item_ids.items()}
        except Exception:
            pass
        try:
            known: Any = set(getattr(self, "checksums", {}) or {})
        except Exception:
            known = set()
        wanted: set[str] = {"Mystery Game"} | set(self.real_slots.values())
        missing: list[str] = sorted(game for game in wanted if game not in known)
        if missing:
            async_start(self.send_msgs([{"cmd": "GetDataPackage", "games": missing}]))

    def item_name_for(self, raw_id: Any) -> str:
        """Resolve item name."""
        try:
            code: int = int(raw_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return f"item {raw_id}"
        try:
            name: Any = self.item_names.lookup_in_game(code)
            if isinstance(name, str):
                return name
        except Exception:
            pass
        local: Dict[int, str] = getattr(self, "_local_item_names", {})
        return local.get(code, f"item {code}")

    def on_package(self, cmd: str, args: dict) -> None:
        if cmd == "RoomInfo":
            try:
                self._last_roominfo = dict(args)
            except Exception:
                pass
        if cmd == "Connected":
            super().on_package(cmd, args)
            self._on_connected(args)
            return
        if cmd in ("Retrieved", "SetReply"):
            super().on_package(cmd, args)
            self._sync_server_state()
            return
        if cmd == "ReceivedItems":
            super().on_package(cmd, args)
            self._check_unlock_items(args)
            self._check_extra_life_items(args)
            self._check_custom_goal(args)
            self._refresh_ui()
            return
        if cmd == "PrintJSON" and args.get("type") == "ItemSend" and args.get("receiving") != self.slot:
            # Ignore observer
            return
        super().on_package(cmd, args)

    def _on_connected(self, args: dict) -> None:
        slot_data: Dict[str, Any] = args.get("slot_data", {})
        self.puzzle_names = list(slot_data.get("mystery_puzzles", []))
        self.unlock_map = dict(slot_data.get("mystery_unlock_map", {}))
        try:
            self.lock_mode = int(slot_data.get("mystery_lock_mode", LOCK_OFF))
        except (TypeError, ValueError):
            self.lock_mode = LOCK_OFF
        self.real_slots = dict(slot_data.get("mystery_real_slots", {}))
        self.untouched_slots = dict(slot_data.get("mystery_untouched_slots", {}))
        self.nuzlocke_enabled = bool(slot_data.get("mystery_nuzlocke", False))
        try:
            self.nuzlocke_deathlink = int(slot_data.get("mystery_nuzlocke_deathlink", 0))
        except Exception:
            self.nuzlocke_deathlink = 0
        raw_modes = slot_data.get("mystery_nuzlocke_deathlink_modes", {})
        if isinstance(raw_modes, dict):
            self.nuzlocke_per_game_modes = {str(k): int(v) for k, v in raw_modes.items() if isinstance(v, int) and v in (0, 1, 2)}
        else:
            self.nuzlocke_per_game_modes = {}
        try:
            self.nuzlocke_lives = int(slot_data.get("mystery_nuzlocke_lives", 1))
            if self.nuzlocke_lives < 1:
                self.nuzlocke_lives = 1
        except Exception:
            self.nuzlocke_lives = 1
        raw_lives = slot_data.get("mystery_nuzlocke_lives_per_slot", {})
        if isinstance(raw_lives, dict):
            self.nuzlocke_lives_per_slot = {str(k): int(v) for k, v in raw_lives.items() if isinstance(v, int) and int(v) >= 1}
        else:
            self.nuzlocke_lives_per_slot = {}
        self.nuzlocke_hits = {}
        try:
            self.nuzlocke_extra_lives = int(slot_data.get("mystery_nuzlocke_extra_lives", 0))
            if self.nuzlocke_extra_lives < 0:
                self.nuzlocke_extra_lives = 0
        except Exception:
            self.nuzlocke_extra_lives = 0
        try:
            self.nuzlocke_extra_distribution = int(slot_data.get("mystery_nuzlocke_extra_distribution", 0))
            if self.nuzlocke_extra_distribution not in (0, 1, 2):
                self.nuzlocke_extra_distribution = 0
        except Exception:
            self.nuzlocke_extra_distribution = 0
        raw_assign = slot_data.get("mystery_nuzlocke_extra_assignments", [])
        if isinstance(raw_assign, list):
            self.nuzlocke_extra_assignments = [str(s) for s in raw_assign if isinstance(s, str) and s in self.real_slots]
        else:
            self.nuzlocke_extra_assignments = []
        self.nuzlocke_extra_earned = {}
        try:
            self.nuzlocke_shared_lives = bool(slot_data.get("mystery_nuzlocke_shared_lives", False))
        except Exception:
            self.nuzlocke_shared_lives = False
        try:
            self.nuzlocke_shared_extra_lives = bool(slot_data.get("mystery_nuzlocke_shared_extra_lives", False))
        except Exception:
            self.nuzlocke_shared_extra_lives = False
        raw_code_sets = slot_data.get("mystery_game_code_sets", [])
        if isinstance(raw_code_sets, list):
            self.game_code_sets = [str(s) for s in raw_code_sets if isinstance(s, str)]
        else:
            self.game_code_sets = []
        raw_code_slots = slot_data.get("mystery_code_set_slots", {})
        if isinstance(raw_code_slots, dict):
            self.code_set_slots = {str(k): [str(s) for s in v if isinstance(s, str) and s in self.real_slots] for k, v in raw_code_slots.items() if isinstance(v, list)}
        else:
            self.code_set_slots = {}
        raw_slot_to_set = slot_data.get("mystery_slot_to_code_set", {})
        if isinstance(raw_slot_to_set, dict):
            self.slot_to_code_set = {str(k): str(v) for k, v in raw_slot_to_set.items() if isinstance(k, str) and isinstance(v, str) and k in self.real_slots}
        else:
            self.slot_to_code_set = {}
        self.nuzlocke_set_hits: dict[str, int] = {}
        self.nuzlocke_set_extra_earned: dict[str, int] = {}
        try:
            self.global_bridge_enabled = bool(slot_data.get("mystery_enable_global_bridge", False))
        except Exception:
            self.global_bridge_enabled = False
        try:
            self.global_bridge_port = int(slot_data.get("mystery_global_bridge_port", 11400))
            if not (1024 <= self.global_bridge_port <= 65535):
                self.global_bridge_port = 11400
        except Exception:
            self.global_bridge_port = 11400
        self.scrambled = bool(slot_data.get("mystery_scrambled", False))
        try:
            self.expose_proxied_items = bool(slot_data.get("mystery_expose_proxied_items", True))
        except Exception:
            self.expose_proxied_items = True
        self.identities = {str(slot): dict(info) for slot, info in
                           dict(slot_data.get("mystery_identities", {})).items()}
        self._ensure_local_datapackage()
        self.puzzle_pieces = {str(puzzle): int(count) for puzzle, count in
                              dict(slot_data.get("mystery_puzzle_pieces", {})).items()}
        self.puzzle_hints = {str(puzzle): [str(text) for text in hints] for puzzle, hints in
                             dict(slot_data.get("mystery_puzzle_hints", {})).items()}
        try:
            self.custom_goal_enabled = bool(slot_data.get("mystery_custom_goal", False))
            self.custom_goal_locations = {str(x).strip() for x in slot_data.get("mystery_custom_goal_locations", []) if isinstance(x, str) and str(x).strip()}
            raw_items = slot_data.get("mystery_custom_goal_items", {})
            if isinstance(raw_items, dict):
                self.custom_goal_items = {str(k).strip(): int(v) for k, v in raw_items.items() if isinstance(k, str) and isinstance(v, int) and int(v) >= 1}
            else:
                self.custom_goal_items = {}
            self.custom_goal_any_items = bool(slot_data.get("mystery_custom_goal_any_items", False))
            self.custom_goal_tag = str(slot_data.get("mystery_custom_goal_tag", "mystery_custom_goal"))
            self.custom_goal_token = str(slot_data.get("mystery_custom_goal_token", "Mystery Goal Token"))
            self.custom_goal_internal_map = dict(slot_data.get("mystery_custom_goal_internal_map", {}))
            # Paired reward info - exposed for client and external tools
            raw_pairs = slot_data.get("mystery_custom_goal_pairs", [])
            if isinstance(raw_pairs, list):
                self.custom_goal_pairs = [dict(p) for p in raw_pairs if isinstance(p, dict) and "source" in p and "reward" in p]
            else:
                self.custom_goal_pairs = []
            raw_rmap = slot_data.get("mystery_custom_goal_reward_map", {})
            if isinstance(raw_rmap, dict):
                self.custom_goal_reward_map = {str(k): str(v) for k, v in raw_rmap.items()}
            elif self.custom_goal_internal_map:
                # fallback: invert internal map
                self.custom_goal_reward_map = {v: k for k, v in self.custom_goal_internal_map.items()}
            else:
                self.custom_goal_reward_map = {}
            self.custom_goal_reward_paired = bool(slot_data.get("mystery_custom_goal_reward_paired", False))
            self.custom_goal_done = False
            if self.custom_goal_enabled:
                client_logger.info("Mystery custom goal: locations=%s items=%s any=%s pairs=%d paired=%s", self.custom_goal_locations, self.custom_goal_items, self.custom_goal_any_items, len(self.custom_goal_pairs), self.custom_goal_reward_paired)
                if self.custom_goal_pairs:
                    for p in self.custom_goal_pairs[:5]:
                        client_logger.info("  pair %s -> %s (player %s region %s)", p.get("source"), p.get("reward"), p.get("source_player"), p.get("source_region"))
                    if len(self.custom_goal_pairs) > 5:
                        client_logger.info("  ... and %d more pairs", len(self.custom_goal_pairs)-5)
        except Exception as e:
            client_logger.debug(f"Mystery custom goal parse failed: {e}")
            self.custom_goal_enabled = False
            self.custom_goal_locations = set()
            self.custom_goal_items = {}
            self.custom_goal_any_items = False
            self.custom_goal_tag = "mystery_custom_goal"
            self.custom_goal_token = "Mystery Goal Token"
            self.custom_goal_internal_map = {}
            self.custom_goal_pairs = []
            self.custom_goal_reward_map = {}
            self.custom_goal_reward_paired = False
            self.custom_goal_done = False
        client_logger.info(
            "Mystery connected: %d puzzle(s), %d unlock(s), lock=%s, %d tracked slot(s)",
            len(self.puzzle_names), len(self.unlock_map),
            self.lock_mode_name(), len(self.real_slots),
        )
        for slot in slot_data.get("mystery_preunlocked", []):
            if isinstance(slot, str) and slot in self.real_slots and slot not in self.unlocked_slots:
                self.unlocked_slots[slot] = "seed"
                relay = self.relays.get(slot)
                if relay is not None:
                    relay.frozen = False
                async_start(self._unlock_slot(slot, "seed"))
        if self.slot is not None:
            keys: List[str] = [unlocks_key(self.team), puzzle_state_key(self.team, self.slot)]
            if self.nuzlocke_enabled:
                keys.append(nuzlocke_key(self.team))
                keys.append(nuzlocke_extra_key(self.team))
            async_start(self.send_msgs([
                {"cmd": "Get", "keys": keys},
                {"cmd": "SetNotify", "keys": keys},
            ]))
        if self.proxy is None or not self.proxy.running:
            async_start(self.start_proxy())
        if self.global_bridge_enabled:
            if self.global_bridge is None or not getattr(self.global_bridge, "running", False):
                async_start(self.start_global_bridge())
        else:
            if self.global_bridge is not None and getattr(self.global_bridge, "running", False):
                async_start(self.stop_global_bridge())
        self._refresh_ui()
        self._check_custom_goal()

    def _sync_server_state(self) -> None:
        if self.slot is None:
            return
        stored: Any = self.stored_data.get(unlocks_key(self.team), {})
        if isinstance(stored, dict):
            for slot, how in stored.items():
                if slot in self.real_slots and slot not in self.unlocked_slots:
                    self.unlocked_slots[slot] = how if isinstance(how, str) else "item"
                    async_start(self.flush_slot(slot))
        if self.nuzlocke_enabled:
            nuz_raw: Any = self.stored_data.get(nuzlocke_key(self.team), {})
            if isinstance(nuz_raw, dict):
                for slot, raw_val in nuz_raw.items():
                    if not isinstance(slot, str) or slot not in self.real_slots:
                        continue
                    lives = self.get_nuzlocke_lives(slot)
                    hits: int | None = None
                    cause: str = ""
                    if isinstance(raw_val, bool):
                        hits = lives if raw_val else 0
                        if isinstance(raw_val, dict):
                            pass
                    elif isinstance(raw_val, int):
                        hits = int(raw_val)
                    elif isinstance(raw_val, dict):
                        if "hits" in raw_val and isinstance(raw_val["hits"], int):
                            hits = int(raw_val["hits"])
                            cause = str(raw_val.get("cause", ""))
                        elif raw_val.get("dead"):
                            hits = lives
                            cause = str(raw_val.get("cause", ""))
                        elif raw_val:
                            hits = lives
                    else:
                        hits = lives if raw_val else 0
                    if hits is None:
                        continue
                    prev_hits = self.nuzlocke_hits.get(slot, 0)
                    if hits > prev_hits:
                        self.nuzlocke_hits[slot] = hits
                    else:
                        hits = self.nuzlocke_hits.get(slot, hits)
                    if hits >= lives and slot not in self.nuzlocke_dead:
                        self.nuzlocke_dead.add(slot)
                        if slot in self.relays:
                            relay = self.relays.pop(slot, None)
                            if relay is not None:
                                if self.active_relay == slot:
                                    self.active_relay = None
                                self.relay_disabled.add(slot)
                                async_start(self._drop_relay(relay))
                                client_logger.warning("Mystery: Nuzlocke killed %s (synced from server)%s", slot, f" ({cause})" if cause else "")
                        if self.proxy is not None:
                            self.proxy.notify_relay_failed(slot, "Nuzlocke dead")
                    elif hits > 0 and hits < lives and hits != prev_hits:
                        client_logger.info("Mystery: Nuzlocke hit %s %d/%d%s (synced)", slot, hits, lives, f" ({cause})" if cause else "")
            elif isinstance(nuz_raw, list):
                for slot in nuz_raw:
                    if isinstance(slot, str) and slot in self.real_slots and slot not in self.nuzlocke_dead:
                        lives = self.get_nuzlocke_base_lives(slot)
                        self.nuzlocke_hits[slot] = lives
                        self.nuzlocke_dead.add(slot)
        if self.nuzlocke_enabled:
            extra_raw: Any = self.stored_data.get(nuzlocke_extra_key(self.team), {})
            if isinstance(extra_raw, dict):
                for slot, cnt in extra_raw.items():
                    if isinstance(slot, str) and slot in self.real_slots and isinstance(cnt, int) and cnt >= 0:
                        if cnt > self.nuzlocke_extra_earned.get(slot, 0):
                            self.nuzlocke_extra_earned[slot] = cnt
                for slot in list(self.nuzlocke_dead):
                    if slot not in self.real_slots:
                        continue
                    lives = self.get_nuzlocke_lives(slot)
                    hits = self.get_nuzlocke_hits(slot)
                    if hits < lives:
                        self.nuzlocke_dead.discard(slot)
                        self.relay_disabled.discard(slot)
                        client_logger.info("Mystery: Nuzlocke revived %s via extra life (%d/%d)", slot, hits, lives)
                        if self.proxy is not None:
                            self.proxy.notify_relay_failed(slot, "revived")
        server_puzzles: Any = self.stored_data.get(puzzle_state_key(self.team, self.slot))
        if server_puzzles is not None:
            merge_puzzle_state(self.puzzle_state, normalize_puzzle_state(server_puzzles))
            for puzzle, entry in self.puzzle_state.items():
                if entry.get("solved"):
                    self.solved_puzzles.add(puzzle)
        for slot, entry in list(self.caches.items()):
            server_entry: Any = self.stored_data.get(self._cache_key_for(slot))
            if server_entry is not None:
                merged: Dict[str, Any] = normalize_cache_entry(server_entry, entry.get("game", "Unknown"))
                merge_pending_checks(merged, entry.get("pending_checks", []))
                merge_held_items(merged, entry.get("held_items", []))
                self.caches[slot] = merged
        self._refresh_ui()

    def find_puzzle(self, query: str) -> Optional[str]:
        lowered: str = query.strip().lower()
        for name in self.puzzle_names:
            if name.lower() == lowered:
                return name
        for name in self.puzzle_names:
            if lowered in name.lower():
                return name
        return None

    def can_solve(self, puzzle: str) -> tuple[bool, str]:
        """Check if puzzle can be solved."""
        need: int = int(self.puzzle_pieces.get(puzzle, 0))
        if puzzle_ready(self.puzzle_state, puzzle, need):
            return True, ""
        have: int = len(self.puzzle_state.get(puzzle, {}).get("pieces", []))
        return False, f"{puzzle} needs {need} pieces ({have}/{need}). Find them first!"

    def puzzle_detail(self, puzzle: str) -> str:
        """Puzzle status."""
        need: int = int(self.puzzle_pieces.get(puzzle, 0))
        have: int = len(self.puzzle_state.get(puzzle, {}).get("pieces", []))
        hints: int = len(self.puzzle_state.get(puzzle, {}).get("hints", []))
        total_hints: int = len(self.puzzle_hints.get(puzzle, []))
        solved: str = "SOLVED" if puzzle in self.solved_puzzles else "open"
        return (f"{puzzle}: pieces {have}/{need}, hints {hints}/{total_hints}, {solved}")

    def earned_hints(self, puzzle: str) -> List[str]:
        """Puzzle hints."""
        texts: List[str] = self.puzzle_hints.get(puzzle, [])
        seen: List[int] = self.puzzle_state.get(puzzle, {}).get("hints", [])
        lines: List[str] = [f"{puzzle} hints ({len(seen)}/{len(texts)}):"]
        for index, text in enumerate(texts, start=1):
            if index in seen:
                lines.append(f"  {index}. {text}")
            else:
                lines.append(f"  {index}. ??? (find Puzzle Hint #{index})")
        if not texts:
            lines.append("  (this puzzle has no hints)")
        return lines

    async def check_puzzle(self, puzzle: str) -> None:
        ready, reason = self.can_solve(puzzle)
        if not ready:
            client_logger.warning("Mystery: cannot solve yet: %s", reason)
            return
        location_id: Optional[int] = self.missing_locations_by_name(puzzle_location_name(puzzle))
        if location_id is None:
            client_logger.warning("Mystery: no location id for puzzle %r", puzzle)
            return
        await self.send_msgs([{"cmd": "LocationChecks", "locations": [location_id]}])
        self.solved_puzzles.add(puzzle)
        entry: Dict[str, Any] = self.puzzle_state.setdefault(
            puzzle, {"pieces": [], "hints": [], "solved": False})
        entry["solved"] = True
        await self._persist_puzzle_state()
        client_logger.info("Mystery: puzzle solved: %s", puzzle)
        self._refresh_ui()

    def missing_locations_by_name(self, location_name: str) -> Optional[int]:
        for location_id in self.missing_locations:
            info: Any = self.locations_info.get(location_id, {})
            name: Any = info.get("name") if isinstance(info, dict) else getattr(info, "name", None)
            if name == location_name:
                return location_id
        local_map: Dict[str, int] = getattr(self, "_local_location_ids", {})
        return local_map.get(location_name)

    def lock_mode_name(self) -> str:
        return {LOCK_OFF: "off", LOCK_FROZEN: "frozen",
                LOCK_GUESS: "guess_the_game", LOCK_BOTH: "both"}.get(self.lock_mode, "off")

    def guessable(self) -> bool:
        """Check if guessing is allowed."""
        return self.lock_mode in (LOCK_GUESS, LOCK_BOTH)

    def item_unlockable(self) -> bool:
        """Check if item unlocks allowed."""
        return self.lock_mode in (LOCK_FROZEN, LOCK_BOTH)

    def locked_slots(self) -> List[str]:
        if self.lock_mode == LOCK_OFF:
            return []
        return [slot for slot in self.real_slots if slot not in self.unlocked_slots]

    def shown_game(self, slot: str) -> str:
        """Display game name."""
        if slot in self.untouched_slots:
            return self.untouched_slots[slot]
        if slot in self.unlocked_slots:
            return self.real_slots.get(slot, "?")
        if self.lock_mode == LOCK_OFF and not self.scrambled:
            return self.real_slots.get(slot, "?")
        return "?"

    def is_locked(self, slot: str) -> bool:
        return slot in self.real_slots and slot not in self.unlocked_slots and self.lock_mode != LOCK_OFF

    def find_slot(self, query: str) -> Optional[str]:
        lowered: str = query.strip().lower()
        for slot in self.real_slots:
            if slot.lower() == lowered:
                return slot
        for slot in self.real_slots:
            if lowered in slot.lower():
                return slot
        return None

    def match_untouched(self, query: str) -> Optional[str]:
        """Find untouched slot."""
        lowered: str = query.strip().lower()
        for slot in self.untouched_slots:
            if slot.lower() == lowered:
                return slot
        for slot in self.untouched_slots:
            if lowered in slot.lower():
                return slot
        return None

    def _unlock_order_names(self) -> List[str]:
        """Unlock order."""
        try:
            ids: List[int] = sorted(
                pid for pid, info in self.slot_info.items()
                if isinstance(pid, int) and pid != 0
                and getattr(info, "name", None) in self.real_slots)
        except Exception:
            return []
        ordered: List[str] = [self.slot_info[pid].name for pid in ids]
        return ordered[:len(self.unlock_map)] if self.unlock_map else ordered

    def resolve_unlock_target(self, item_name: str) -> Optional[str]:
        """Map unlock item to slot."""
        try:
            number: int = int(item_name.rsplit(" ", 1)[1])
        except (IndexError, ValueError):
            return None
        ordered: List[str] = self._unlock_order_names()
        if 1 <= number <= len(ordered):
            return ordered[number - 1]
        return None

    def reveal_unlock(self, query: str) -> Optional[str]:
        if not self.item_unlockable():
            return "Item unlocks are disabled in guess-only mode (use !mystery_guess)."
        untouched: Optional[str] = self.match_untouched(query)
        if untouched is not None:
            return f"{untouched} is not managed by Mystery (connect directly)."
        lowered: str = query.strip().lower()
        for location, slot in self.unlock_map.items():
            if lowered in location.lower() or lowered in slot.lower():
                real: Optional[str] = self.resolve_unlock_target(slot) or self.find_slot(slot)
                self.revealed_unlocks[location] = real or slot
                if real and real in self.real_slots:
                    async_start(self._unlock_slot(real, "item"))
                    return f"{location} reveals {real} (unlocking...)"
                return f"{location} reveals {self.revealed_unlocks[location]}"
        slot_hit: Optional[str] = self.find_slot(query)
        if slot_hit and slot_hit in self.real_slots:
            async_start(self._unlock_slot(slot_hit, "item"))
            return f"{slot_hit} unlocking..."
        return None

    def _check_unlock_items(self, args: dict) -> None:
        if not self.item_unlockable():
            return
        for item in args.get("items", []):
            name: str = self.item_name_for(getattr(item, "item", None))
            if name.startswith("Unlock Slot"):
                target: Optional[str] = self.resolve_unlock_target(name)
                if target:
                    async_start(self._unlock_slot(target, "item"))

    async def _persist_puzzle_state(self) -> None:
        if self.slot is None:
            return
        await self.send_msgs([set_operation(
            puzzle_state_key(self.team, self.slot), self.puzzle_state, default={})])

    def _check_puzzle_items(self, args: dict) -> None:
        """Record puzzle items."""
        touched: bool = False
        for item in args.get("items", []):
            name: str = self.item_name_for(getattr(item, "item", None))
            piece: Optional[tuple[str, int]] = parse_puzzle_piece(name)
            if piece is not None:
                puzzle, index = piece
                entry: Dict[str, Any] = self.puzzle_state.setdefault(
                    puzzle, {"pieces": [], "hints": [], "solved": False})
                if index not in entry["pieces"]:
                    entry["pieces"].append(index)
                    entry["pieces"] = sorted(entry["pieces"])
                    client_logger.info("Mystery: piece %d for '%s'", index, puzzle)
                    touched = True
                continue
            hint: Optional[tuple[str, int]] = parse_puzzle_hint(name)
            if hint is not None:
                puzzle, index = hint
                entry = self.puzzle_state.setdefault(
                    puzzle, {"pieces": [], "hints": [], "solved": False})
                texts: List[str] = self.puzzle_hints.get(puzzle, [])
                if index not in entry["hints"]:
                    entry["hints"].append(index)
                    entry["hints"] = sorted(entry["hints"])
                    touched = True
                if 1 <= index <= len(texts):
                    client_logger.info("Mystery hint for '%s' (#%d): %s", puzzle, index, texts[index - 1])
                else:
                    client_logger.info("Mystery: hint #%d for '%s' (no text recorded)", index, puzzle)
        if touched:
            async_start(self._persist_puzzle_state())
            self._refresh_ui()

    def _pick_random_nuzlocke_slot(self) -> Optional[str]:
        """Pick random Nuzlocke slot."""
        try:
            candidates = [s for s in self.real_slots if s not in self.nuzlocke_dead]
            if not candidates:
                candidates = list(self.real_slots.keys())
            if candidates:
                import random
                return random.choice(candidates)
        except Exception:
            pass
        return None

    def _pick_most_needy_nuzlocke_slot(self) -> Optional[str]:
        """Pick neediest Nuzlocke slot."""
        try:
            best: Optional[str] = None
            best_remaining: int | None = None
            for slot in self.real_slots:
                if slot in self.nuzlocke_dead:
                    continue
                rem = self.get_nuzlocke_remaining(slot)
                if best_remaining is None or rem < best_remaining:
                    best_remaining = rem
                    best = slot
            if best is not None:
                return best
            return self._pick_random_nuzlocke_slot()
        except Exception:
            return self._pick_random_nuzlocke_slot()

    async def _persist_extra_lives(self) -> None:
        if self.slot is None:
            return
        try:
            if getattr(self, "nuzlocke_shared_extra_lives", False) and getattr(self, "nuzlocke_set_extra_earned", None):
                merged = dict(self.nuzlocke_extra_earned)
                merged.update(self.nuzlocke_set_extra_earned)
                await self.send_msgs([set_operation(nuzlocke_extra_key(self.team), merged, default={})])
            else:
                await self.send_msgs([set_operation(nuzlocke_extra_key(self.team), dict(self.nuzlocke_extra_earned), default={})])
        except Exception as exc:
            logger.warning("Mystery: failed to persist extra lives: %s", exc)

    def _check_extra_life_items(self, args: dict) -> None:
        if not self.nuzlocke_enabled:
            return
        has_extra = False
        for item in args.get("items", []):
            try:
                name = self.item_name_for(getattr(item, "item", None))
            except Exception:
                continue
            if name == EXTRA_LIFE_ITEM or name.startswith("Extra Life"):
                has_extra = True
                break
        if not has_extra:
            return
        for item in args.get("items", []):
            try:
                name = self.item_name_for(getattr(item, "item", None))
            except Exception:
                continue
            if name != EXTRA_LIFE_ITEM and not name.startswith("Extra Life"):
                continue
            mode = self.nuzlocke_extra_distribution
            targets: List[str] = []
            if mode == 1:  # for_all
                targets = list(self.real_slots.keys())
            elif mode == 2:  # for_specific (pre-assigned round-robin)
                total = sum(self.nuzlocke_extra_earned.values())
                if self.nuzlocke_extra_assignments:
                    target = self.nuzlocke_extra_assignments[total % len(self.nuzlocke_extra_assignments)]
                    if target in self.real_slots:
                        targets = [target]
                    else:
                        picked = self._pick_random_nuzlocke_slot()
                        if picked:
                            targets = [picked]
                else:
                    picked = self._pick_random_nuzlocke_slot()
                    if picked:
                        targets = [picked]
            else:  # for_picker
                finder = getattr(item, "player", None)
                picker: Optional[str] = None
                try:
                    for pid, info in self.slot_info.items():
                        if int(pid) == int(finder):  # type: ignore[arg-type]
                            cand = getattr(info, "name", None)
                            if isinstance(cand, str) and cand in self.real_slots:
                                picker = cand
                                break
                except Exception:
                    picker = None
                if picker and picker in self.real_slots:
                    targets = [picker]
                else:
                    picked = self._pick_most_needy_nuzlocke_slot()
                    if picked:
                        targets = [picked]
            for target in targets:
                if not target or target not in self.real_slots:
                    continue
                is_shared_extra = getattr(self, "nuzlocke_shared_extra_lives", False) and target in getattr(self, "slot_to_code_set", {})
                if is_shared_extra:
                    set_name = self.slot_to_code_set.get(target)
                    for s in self.code_set_slots.get(set_name, [target]):
                        cur = self.nuzlocke_extra_earned.get(s, 0)
                        cur_set = self.nuzlocke_set_extra_earned.get(set_name, 0)
                        self.nuzlocke_set_extra_earned[set_name] = cur_set + 1
                        self.nuzlocke_extra_earned[s] = self.nuzlocke_set_extra_earned[set_name]
                        effective = self.get_nuzlocke_lives(s)
                        hits = self.get_nuzlocke_hits(s)
                        was_dead = s in self.nuzlocke_dead or set_name in self.nuzlocke_dead
                        if was_dead and hits < effective:
                            self.nuzlocke_dead.discard(s)
                            self.nuzlocke_dead.discard(set_name)
                            self.relay_disabled.discard(s)
                            client_logger.info("Mystery: Extra Life revived set %s -> %s (%d/%d extra %d)", set_name, s, hits, effective, self.nuzlocke_set_extra_earned[set_name])
                        else:
                            client_logger.info("Mystery: Extra Life for set %s -> %s (%d/%d, extra %d)", set_name, s, hits, effective, self.nuzlocke_set_extra_earned[set_name])
                else:
                    cur = self.nuzlocke_extra_earned.get(target, 0)
                    self.nuzlocke_extra_earned[target] = cur + 1
                    effective = self.get_nuzlocke_lives(target)
                    hits = self.get_nuzlocke_hits(target)
                    was_dead = target in self.nuzlocke_dead
                    if was_dead and hits < effective:
                        self.nuzlocke_dead.discard(target)
                        self.relay_disabled.discard(target)
                        client_logger.info("Mystery: Extra Life revived %s (%d/%d extra %d)", target, hits, effective, self.nuzlocke_extra_earned[target])
                    else:
                        client_logger.info("Mystery: Extra Life for %s (%d/%d, extra %d)", target, hits, effective, self.nuzlocke_extra_earned[target])
        import asyncio as _asyncio
        try:
            from CommonClient import async_start as _as
            _as(self._persist_extra_lives())
        except Exception:
            pass
        self._refresh_ui()
        self._check_custom_goal(args)

    def _is_custom_goal_met(self) -> bool:
        """Check if custom goal is met based on received items."""
        if not getattr(self, "custom_goal_enabled", False):
            return False
        if getattr(self, "custom_goal_done", False):
            return True
        # Check locations: need standard Goal Tokens count
        locs = getattr(self, "custom_goal_locations", set())
        if locs:
            token_name = getattr(self, "custom_goal_token", "Mystery Goal Token")
            need_tokens = len(locs)
            have_tokens = 0
            for it in getattr(self, "items_received", []):
                try:
                    name = self.item_name_for(getattr(it, "item", None))
                except Exception:
                    continue
                if name == token_name:
                    have_tokens += 1
                # Backwards compat: also accept old per-location tokens
                elif name.startswith("Mystery Goal Token: "):
                    have_tokens += 1
            if have_tokens < need_tokens:
                return False
        # Check items: need counts, handling any vs specific via flags
        needed: Dict[str, int] = getattr(self, "custom_goal_items", {})
        if needed:
            any_mode = bool(getattr(self, "custom_goal_any_items", False))
            # For any_mode, count any item with matching name
            # For specific, count only GOAL_MARKED items (flags & 8)
            counts: Dict[str, int] = {}
            for it in getattr(self, "items_received", []):
                try:
                    name = self.item_name_for(getattr(it, "item", None))
                except Exception:
                    continue
                if name not in needed:
                    continue
                if not any_mode:
                    # Specific: only count if GOAL_MARKED
                    flags = int(getattr(it, "flags", 0) or 0)
                    is_marked = bool(flags & 8)  # GOAL_MARKED_FLAG
                    # Also accept attribute if present (fallback)
                    if not is_marked:
                        # Check if NetworkItem has extra? items_received entries are NetworkItem with flags
                        # If not flagged, skip (don't count unmarked filler)
                        continue
                counts[name] = counts.get(name, 0) + 1
                # For any_mode we already counted; for specific we only counted marked
            # For any_mode, the above counted only filtered names, but for specific we filtered by flag.
            # For any_mode, we counted all; for specific, only marked.
            # However, if specific items are not flagged due to old generation, fallback to counting all (compat)
            # Detect if no marked items were found but we expected specific: fallback
            if not any_mode:
                # If zero counted but there are needed items, check if any of those items exist without flag (old saves)
                # We can fallback to counting by name if no flagged items at all
                if all(counts.get(n, 0) == 0 for n in needed):
                    # Fallback: count by name without flag filter
                    fallback_counts: Dict[str, int] = {}
                    for it in getattr(self, "items_received", []):
                        try:
                            name = self.item_name_for(getattr(it, "item", None))
                        except Exception:
                            continue
                        if name in needed:
                            fallback_counts[name] = fallback_counts.get(name, 0) + 1
                    # Use fallback if it has counts
                    if any(fallback_counts.values()):
                        counts = fallback_counts
            for name, need in needed.items():
                if counts.get(name, 0) < int(need):
                    return False
        return True

    def _check_custom_goal(self, args: dict | None = None) -> None:
        """Track custom goal and send goaled if met."""
        if not getattr(self, "custom_goal_enabled", False):
            return
        if getattr(self, "custom_goal_done", False):
            return
        if self._is_custom_goal_met():
            self.custom_goal_done = True
            client_logger.info("Mystery: custom goal completed - %s locations, %s items", self.custom_goal_locations, self.custom_goal_items)
            try:
                from NetUtils import ClientStatus
                async_start(self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]))
            except Exception:
                try:
                    async_start(self.send_msgs([{"cmd": "StatusUpdate", "status": 30}]))
                except Exception:
                    pass
            try:
                self.finished_game = True
            except Exception:
                pass
            self._refresh_ui()

    # --- Custom goal paired reward helpers (exposed for client/UI and external tools) ---
    def get_reward_for_source(self, source_name: str) -> Optional[str]:
        """Given a source location name, return its paired reward location name, if any."""
        try:
            if self.custom_goal_internal_map and source_name in self.custom_goal_internal_map:
                return self.custom_goal_internal_map[source_name]
            for p in getattr(self, "custom_goal_pairs", []):
                if p.get("source") == source_name:
                    return p.get("reward")
        except Exception:
            pass
        return None

    def get_source_for_reward(self, reward_name: str) -> Optional[str]:
        """Given a reward location name, return its source location name, if any."""
        try:
            if self.custom_goal_reward_map and reward_name in self.custom_goal_reward_map:
                return self.custom_goal_reward_map[reward_name]
            for p in getattr(self, "custom_goal_pairs", []):
                if p.get("reward") == reward_name:
                    return p.get("source")
        except Exception:
            pass
        # fallback inverse
        try:
            for src, rew in self.custom_goal_internal_map.items():
                if rew == reward_name:
                    return src
        except Exception:
            pass
        return None

    def get_pair_for_reward(self, reward_name: str) -> Optional[dict]:
        try:
            for p in getattr(self, "custom_goal_pairs", []):
                if p.get("reward") == reward_name:
                    return p
        except Exception:
            pass
        return None

    def submit_guess(self, slot_query: str, game_guess: str) -> Optional[str]:
        slot: Optional[str] = self.find_slot(slot_query)
        if slot is None:
            untouched: Optional[str] = self.match_untouched(slot_query)
            if untouched is not None:
                return f"{untouched} is not managed by Mystery (connect directly)."
            return None
        if slot in self.unlocked_slots:
            return f"{slot} is already unlocked ({self.unlocked_slots[slot]})."
        if not self.guessable():
            return f"Guess mode is off (lock mode: {self.lock_mode_name()})."
        if check_guess(game_guess, self.real_slots[slot]):
            async_start(self._unlock_slot(slot, "guess"))
            return f"Correct! {slot} is {self.real_slots[slot]}. Unlocking..."
        return f"Wrong: {slot} is not {game_guess.strip()}."

    async def _unlock_slot(self, slot: str, how: str) -> None:
        if slot in self.unlocked_slots:
            return
        self.unlocked_slots[slot] = how
        client_logger.info("Mystery: unlocked %s (%s)", slot, how)
        if self.slot is not None:
            key: str = unlocks_key(self.team)
            current: Any = self.stored_data.get(key, {})
            updated: Dict[str, Any] = dict(current) if isinstance(current, dict) else {}
            updated[slot] = how
            await self.send_msgs([set_operation(key, updated, default={})])
        await self.flush_slot(slot)
        self._refresh_ui()

    def _slot_id(self, slot: str) -> Optional[int]:
        for player, info in self.slot_info.items():
            if info.name == slot:
                return int(player)
        return None

    def _cache_key_for(self, slot: str) -> Optional[str]:
        if self.slot is None:
            return None
        player: Optional[int] = self._slot_id(slot)
        if player is None:
            return None
        return cache_key(self.team, player)

    def cache_entry(self, slot: str) -> Dict[str, Any]:
        entry: Optional[Dict[str, Any]] = self.caches.get(slot)
        if entry is None:
            entry = new_cache_entry(self.real_slots.get(slot, "Unknown"))
            self.caches[slot] = entry
        return entry

    async def stash_checks(self, slot: str, checks: List[int]) -> None:
        if not checks:
            return
        entry: Dict[str, Any] = self.cache_entry(slot)
        merge_pending_checks(entry, checks)
        key: Optional[str] = self._cache_key_for(slot)
        if key is not None:
            await self.send_msgs([set_operation(key, entry, default={})])
        client_logger.info("Mystery: cached %d check(s) for locked slot %s", len(checks), slot)
        self._refresh_ui()

    async def stash_items(self, slot: str, items: List[dict]) -> None:
        if not items:
            return
        entry: Dict[str, Any] = self.cache_entry(slot)
        merge_held_items(entry, items)
        key: Optional[str] = self._cache_key_for(slot)
        if key is not None:
            await self.send_msgs([set_operation(key, entry, default={})])
        client_logger.info("Mystery: held %d item(s) for locked slot %s", len(items), slot)
        self._refresh_ui()

    async def flush_slot(self, slot: str) -> None:
        """Flush slot."""
        if self.is_locked(slot):
            self._refresh_ui()
            return
        entry: Dict[str, Any] = self.cache_entry(slot)
        relay: Optional["RelayContext"] = self.relays.get(slot)
        pending: List[int] = list(entry.get("pending_checks", []))
        if pending and relay is not None and relay.server and relay.slot:
            await relay.send_msgs([{"cmd": "LocationChecks", "locations": pending}])
            entry["pending_checks"] = []
            client_logger.info("Mystery: flushed %d cached check(s) for %s", len(pending), slot)
        if relay is not None:
            relay.frozen = False
            async_start(relay._maybe_alias())
        if self.proxy is not None:
            await self.proxy.deliver_held(slot)
        key: Optional[str] = self._cache_key_for(slot)
        if key is not None and (pending or entry.get("held_items")):
            await self.send_msgs([set_operation(key, entry, default={})])
        self._refresh_ui()

    def server_identity(self, slot: str) -> Dict[str, str]:
        """Handshake identity."""
        info: Dict[str, str] = self.identities.get(slot, {})
        return {
            "game": info.get("server_game", self.real_slots.get(slot, "Unknown")),
            "slot": slot,
        }

    def _main_online(self) -> bool:
        """Check if connected."""
        try:
            return bool(self.server and self.server.socket and self.server.socket.open
                        and not self.server.socket.closed and self.slot is not None)
        except Exception:
            return False

    def is_nuzlocke_dead(self, slot: str) -> bool:
        """Check if Nuzlocke dead."""
        if not self.nuzlocke_enabled:
            return False
        if getattr(self, "nuzlocke_shared_lives", False):
            try:
                set_name = self.slot_to_code_set.get(slot)
                if set_name and set_name in self.nuzlocke_dead:
                    return True
                if set_name:
                    for s in self.code_set_slots.get(set_name, []):
                        if s in self.nuzlocke_dead:
                            return True
            except Exception:
                pass
        return slot in self.nuzlocke_dead

    def get_nuzlocke_lives(self, slot: str) -> int:
        """Effective lives."""
        if getattr(self, "nuzlocke_shared_lives", False):
            try:
                set_name = self.slot_to_code_set.get(slot)
                if set_name:
                    per = self.nuzlocke_lives_per_slot.get(slot)
                    if isinstance(per, int) and per >= 1:
                        base = int(per)
                    else:
                        base = int(self.nuzlocke_lives)
                    if getattr(self, "nuzlocke_shared_extra_lives", False):
                        extra = int(self.nuzlocke_set_extra_earned.get(set_name, 0))
                    else:
                        extra = int(self.nuzlocke_extra_earned.get(slot, 0))
                    if extra < 0:
                        extra = 0
                    return base + extra
            except Exception:
                pass
        try:
            per = self.nuzlocke_lives_per_slot.get(slot)
            if isinstance(per, int) and per >= 1:
                base = int(per)
            else:
                base = int(self.nuzlocke_lives)
        except Exception:
            try:
                base = int(self.nuzlocke_lives)
            except Exception:
                base = 1
        try:
            extra = int(self.nuzlocke_extra_earned.get(slot, 0))
            if extra < 0:
                extra = 0
        except Exception:
            extra = 0
        return base + extra

    def get_nuzlocke_base_lives(self, slot: str) -> int:
        """Base lives."""
        try:
            per = self.nuzlocke_lives_per_slot.get(slot)
            if isinstance(per, int) and per >= 1:
                return int(per)
        except Exception:
            pass
        try:
            return int(self.nuzlocke_lives)
        except Exception:
            return 1

    def get_nuzlocke_hits(self, slot: str) -> int:
        """Hits taken."""
        if getattr(self, "nuzlocke_shared_lives", False):
            try:
                set_name = self.slot_to_code_set.get(slot)
                if set_name:
                    return int(self.nuzlocke_set_hits.get(set_name, 0))
            except Exception:
                pass
        try:
            return int(self.nuzlocke_hits.get(slot, 0))
        except Exception:
            return 0

    def get_nuzlocke_remaining(self, slot: str) -> int:
        """Lives remaining."""
        return max(0, self.get_nuzlocke_lives(slot) - self.get_nuzlocke_hits(slot))

    def get_nuzlocke_mode(self, slot: str) -> int:
        """Nuzlocke mode."""
        if not self.nuzlocke_enabled:
            return 0
        per = self.nuzlocke_per_game_modes.get(slot)
        if isinstance(per, int) and per in (1, 2):
            return per
        if self.nuzlocke_deathlink in (1, 2):
            return int(self.nuzlocke_deathlink)
        return 0

    def non_controlled_ids(self) -> list[int]:
        """Uncontrolled player ids."""
        try:
            all_ids = [pid for pid in self.slot_info.keys() if isinstance(pid, int) and pid != 0 and pid != self.slot]
            controlled_names = set(self.real_slots.keys()) | set(self.nuzlocke_per_game_modes.keys())
            controlled_ids: set[int] = set()
            for pid, info in self.slot_info.items():
                name = getattr(info, "name", None)
                if isinstance(name, str) and name in self.real_slots:
                    controlled_ids.add(int(pid))
            return [pid for pid in all_ids if pid not in controlled_ids]
        except Exception:
            return []

    async def trigger_nuzlocke(self, slot: str, cause: str = "") -> None:
        """Trigger Nuzlocke hit."""
        if not self.nuzlocke_enabled or slot not in self.real_slots:
            return
        is_shared = getattr(self, "nuzlocke_shared_lives", False) and slot in getattr(self, "slot_to_code_set", {})
        if is_shared:
            set_name = self.slot_to_code_set.get(slot)
            if not set_name:
                return
            if set_name in self.nuzlocke_dead:
                return
            lives = self.get_nuzlocke_lives(slot)
            hits = self.nuzlocke_set_hits.get(set_name, 0)
            try:
                stored = self.stored_data.get(nuzlocke_key(self.team), {})
                if isinstance(stored, dict) and set_name in stored:
                    raw = stored[set_name]
                    if isinstance(raw, int):
                        hits = max(hits, int(raw))
                    elif isinstance(raw, dict) and "hits" in raw and isinstance(raw["hits"], int):
                        hits = max(hits, int(raw["hits"]))
                    elif raw is True or (isinstance(raw, dict) and raw.get("dead")):
                        hits = max(hits, lives)
                elif isinstance(stored, dict) and slot in stored:
                    raw = stored[slot]
                    if isinstance(raw, int):
                        hits = max(hits, int(raw))
                    elif isinstance(raw, dict) and "hits" in raw and isinstance(raw["hits"], int):
                        hits = max(hits, int(raw["hits"]))
            except Exception:
                pass
            new_hits = hits + 1
            self.nuzlocke_set_hits[set_name] = new_hits
            for s in self.code_set_slots.get(set_name, []):
                self.nuzlocke_hits[s] = new_hits
        else:
            if slot in self.nuzlocke_dead:
                return
            lives = self.get_nuzlocke_lives(slot)
            hits = self.nuzlocke_hits.get(slot, 0)
            try:
                stored = self.stored_data.get(nuzlocke_key(self.team), {})
                if isinstance(stored, dict) and slot in stored:
                    raw = stored[slot]
                    if isinstance(raw, int):
                        hits = max(hits, int(raw))
                    elif isinstance(raw, dict) and "hits" in raw and isinstance(raw["hits"], int):
                        hits = max(hits, int(raw["hits"]))
                    elif raw is True or (isinstance(raw, dict) and raw.get("dead")):
                        hits = max(hits, lives)
            except Exception:
                pass
            new_hits = hits + 1
            self.nuzlocke_hits[slot] = new_hits
        remaining = max(0, lives - new_hits)
        if self.slot is not None:
            try:
                key = nuzlocke_key(self.team)
                current = self.stored_data.get(key, {})
                new_dict = dict(current) if isinstance(current, dict) else {}
                is_shared = getattr(self, "nuzlocke_shared_lives", False) and slot in getattr(self, "slot_to_code_set", {})
                target_key = self.slot_to_code_set.get(slot, slot) if is_shared else slot
                if new_hits >= lives:
                    new_dict[target_key] = {"dead": True, "hits": new_hits, "lives": lives, "cause": cause, "time": time.time()} if cause else True
                    if is_shared:
                        for s in self.code_set_slots.get(target_key, []):
                            new_dict[s] = new_dict[target_key]
                else:
                    new_dict[target_key] = new_hits
                    if is_shared:
                        for s in self.code_set_slots.get(target_key, []):
                            new_dict[s] = new_hits
                await self.send_msgs([set_operation(key, new_dict, default={})])
                try:
                    self.stored_data[key] = new_dict
                except Exception:
                    pass
            except Exception as exc:
                logger.warning("Mystery: failed to persist nuzlocke for %s: %s", slot, exc)
        if new_hits < lives:
            is_shared = getattr(self, "nuzlocke_shared_lives", False) and slot in getattr(self, "slot_to_code_set", {})
            log_slot = self.slot_to_code_set.get(slot, slot) if is_shared else slot
            client_logger.warning("Mystery: Nuzlocke hit %s %d/%d%s (remaining %d) – relay stays up", log_slot, new_hits, lives, f" ({cause})" if cause else "", remaining)
            if self.proxy is not None:
                try:
                    # Broadcast hit to all clients for this slot (multi-client)
                    for ws in list(self.proxy._get_sockets_for_slot(slot)):
                        try:
                            await ws.send(encode([{"cmd": "PrintJSON", "data": [{"text": f"Nuzlocke: {slot} hit {new_hits}/{lives} – {remaining} lives remaining{': ' + cause if cause else '.'}"}]}]))
                        except Exception:
                            pass
                except Exception:
                    pass
            self._refresh_ui()
            self._refresh_hints_ui()
            return
        is_shared = getattr(self, "nuzlocke_shared_lives", False) and slot in getattr(self, "slot_to_code_set", {})
        if is_shared:
            set_name = self.slot_to_code_set.get(slot)
            self.nuzlocke_dead.add(set_name)
            for s in self.code_set_slots.get(set_name, []):
                self.nuzlocke_dead.add(s)
                self.relay_disabled.add(s)
                if self.active_relay == s:
                    self.active_relay = None
                relay = self.relays.pop(s, None)
                if relay is not None:
                    try:
                        relay.disconnected_intentionally = True
                    except Exception:
                        pass
                    async_start(self._drop_relay(relay))
            if self.proxy is not None:
                try:
                    self.proxy.notify_relay_failed(set_name, "Nuzlocke dead (set)")
                    for s in self.code_set_slots.get(set_name, []):
                        self.proxy.notify_relay_failed(s, "Nuzlocke dead (set)")
                        for ws in list(self.proxy._get_sockets_for_slot(s)):
                            try:
                                await ws.send(encode([{"cmd": "PrintJSON", "data": [{"text": f"Nuzlocke: {set_name} has died. Relay permanently closed ({new_hits}/{lives}){': ' + cause if cause else '.'} - {s}"}]}]))
                                await ws.close()
                            except Exception:
                                pass
                            try:
                                self.proxy._unregister_socket(ws)
                            except Exception:
                                pass
                except Exception:
                    pass
            client_logger.warning("Mystery: Nuzlocke killed set %s%s (%d/%d) - %s", set_name, f" ({cause})" if cause else "", new_hits, lives, ", ".join(self.code_set_slots.get(set_name, [])))
        else:
            self.nuzlocke_dead.add(slot)
            self.relay_disabled.add(slot)
            if self.active_relay == slot:
                self.active_relay = None
            relay = self.relays.pop(slot, None)
            if relay is not None:
                try:
                    relay.disconnected_intentionally = True
                except Exception:
                    pass
                async_start(self._drop_relay(relay))
            if self.proxy is not None:
                try:
                    self.proxy.notify_relay_failed(slot, "Nuzlocke dead")
                    for ws in list(self.proxy._get_sockets_for_slot(slot)):
                        try:
                            await ws.send(encode([{"cmd": "PrintJSON", "data": [{"text": f"Nuzlocke: {slot} has died. Relay permanently closed ({new_hits}/{lives}){': ' + cause if cause else '.'}"}]}]))
                            await ws.close()
                        except Exception:
                            pass
                        try:
                            self.proxy._unregister_socket(ws)
                        except Exception:
                            pass
                except Exception:
                    pass
            client_logger.warning("Mystery: Nuzlocke killed %s%s (%d/%d)", slot, f" ({cause})" if cause else "", new_hits, lives)
        self._refresh_ui()
        self._refresh_hints_ui()

    def start_relay(self, slot_query: str, make_active: bool = True,
                    via_command: bool = False) -> Optional[str]:
        """Start relay."""
        slot: Optional[str] = self.find_slot(slot_query)
        if slot is None:
            untouched: Optional[str] = self.match_untouched(slot_query)
            if untouched is not None:
                return f"{untouched} is not managed by Mystery (connect directly)."
            return None
        if self.is_nuzlocke_dead(slot):
            return f"{slot} is dead (Nuzlocke) – relay permanently closed."
        if not self._main_online():
            return "Mystery slot is not connected to the server; connect it first."
        if slot in self.relay_disabled and not via_command:
            return f"Relay for {slot} was stopped (!mystery_relay {slot} to restart)."
        if via_command:
            self.relay_disabled.discard(slot)
        if slot in self.relays:
            if make_active:
                self.active_relay = slot
                self._refresh_ui()
                return f"Relay for {slot} already running (chat control -> {slot})."
            return f"Relay for {slot} already running."
        game: str = self.real_slots.get(slot, "Unknown")
        identity: Dict[str, str] = self.server_identity(slot)
        relay = RelayContext(self.server_address, self.password, game, slot, self,
                             server_game=identity["game"])
        relay.auth = identity["slot"]
        relay.username = identity["slot"]
        relay.frozen = self.is_locked(slot)
        try:
            ih = None
            if hasattr(self, "_pending_items_handling") and isinstance(getattr(self, "_pending_items_handling"), dict):
                ih = getattr(self, "_pending_items_handling").get(slot)
            if ih is None and getattr(self, "proxy", None) is not None:
                try:
                    ih = self.proxy.game_items_handling.get(slot)
                except Exception:
                    ih = None
            if isinstance(ih, int) and 0 <= ih <= 7:
                relay.items_handling = ih
        except Exception:
            pass
        self.relays[slot] = relay
        if make_active:
            self.active_relay = slot
        relay.server_task = asyncio.create_task(server_loop(relay), name=f"relay {slot}")
        try:
            if self.proxy is not None:
                async_start(self.proxy.ensure_slot_port(slot))
            if self.global_bridge is not None and self.global_bridge_enabled:
                async_start(self.global_bridge.ensure_slot_port(slot))
        except Exception:
            pass
        key: Optional[str] = self._cache_key_for(slot)
        if key is not None:
            async_start(relay.send_msgs([
                {"cmd": "Get", "keys": [key]},
                {"cmd": "SetNotify", "keys": [key]},
            ]))
        self._refresh_ui()
        shown: str = self.shown_game(slot)
        port_info = ""
        try:
            ports: List[str] = []
            if self.proxy is not None and slot in getattr(self.proxy, "slot_ports", {}):
                ports.append(f"proxy:{self.proxy.slot_ports[slot]}")
            if self.global_bridge is not None and slot in getattr(self.global_bridge, "slot_ports", {}):
                ports.append(f"global:{self.global_bridge.slot_ports[slot]}")
            if ports:
                port_info = " [" + ", ".join(ports) + "]"
        except Exception:
            pass
        return (f"Relay connecting as {slot} ({shown})"
                + (" [FROZEN]" if relay.frozen else "")
                + (" [chat control]" if make_active else "")
                + port_info)

    def stop_relay(self, slot_query: str) -> Optional[str]:
        """Stop relay."""
        slot: Optional[str] = self.find_slot(slot_query)
        if slot is None:
            return None
        relay: Optional["RelayContext"] = self.relays.pop(slot, None)
        if relay is None:
            return f"No relay running for {slot}."
        self.relay_disabled.add(slot)
        if self.active_relay == slot:
            self.active_relay = None
        async_start(self._drop_relay(relay))
        self._refresh_ui()
        return f"Relay for {slot} disconnecting (stopped; !mystery_relay {slot} to restart)..."

    async def _drop_relay(self, relay: "RelayContext") -> None:
        try:
            await relay.disconnect()
        except Exception:
            pass

    @staticmethod
    def _relay_online(relay: "RelayContext") -> bool:
        try:
            return bool(relay.server) and relay.slot is not None
        except Exception:
            return False

    def relay_for_chat(self) -> Optional["RelayContext"]:
        """Active relay for chat."""
        active: Optional[str] = self.active_relay
        if active is not None:
            relay: Optional["RelayContext"] = self.relays.get(active)
            if relay is not None and self._relay_online(relay):
                return relay
        return None

    async def start_proxy(self) -> None:
        if self.proxy is not None and self.proxy.running:
            client_logger.info("Mystery: proxy already running")
            return
        target = getattr(self, "proxy_port", MYSTERY_PROXY_PORT)
        try:
            port = find_free_port(MYSTERY_PROXY_HOST, int(target))
        except Exception:
            port = int(target)
        self.proxy = MysteryProxy(self, MYSTERY_PROXY_HOST, port)
        try:
            self.proxy_port = port
        except Exception:
            pass
        await self.proxy.start()
        try:
            if getattr(self.proxy, "port", None) != port:
                self.proxy_port = int(self.proxy.port)
        except Exception:
            pass
        client_logger.info("Mystery: %s", self.proxy_help())
        self._refresh_ui()

    async def stop_proxy(self) -> None:
        if self.proxy is None:
            return
        await self.proxy.stop()
        self.proxy = None
        self._refresh_ui()

    async def start_global_bridge(self) -> None:
        if self.global_bridge is not None and self.global_bridge.running:
            return
        if not self.global_bridge_enabled:
            return
        target = int(self.global_bridge_port)
        try:
            port = find_free_port(MYSTERY_GLOBAL_HOST, target)
        except Exception:
            port = target
        self.global_bridge = MysteryProxy(self, MYSTERY_GLOBAL_HOST, port, is_global=True)
        await self.global_bridge.start()
        try:
            if getattr(self.global_bridge, "port", None) != port:
                self.global_bridge_port = int(self.global_bridge.port)
            else:
                self.global_bridge_port = int(port)
                if port != target:
                    client_logger.info("Mystery: global bridge port %d busy, using %d", target, port)
        except Exception:
            pass
        if self.global_bridge.running:
            client_logger.info("Mystery: global bridge listening on ws://%s:%d (broadcast, APWorld not required, shared)", self.global_bridge.host, self.global_bridge.port)
        self._refresh_ui()

    async def stop_global_bridge(self) -> None:
        if self.global_bridge is None:
            return
        try:
            await self.global_bridge.stop()
        except Exception:
            pass
        self.global_bridge = None
        self._refresh_ui()

    def proxy_help(self) -> str:
        routes: Dict[str, str] = {}
        for slot in self.real_slots:
            routes[slot] = slot
            if self.proxy is not None:
                routes.update(self.proxy.routes)
        frozen: List[str] = [slot for slot in routes if self.is_locked(slot)]
        host: str = MYSTERY_PROXY_HOST
        port: int = self.proxy.port if self.proxy is not None else MYSTERY_PROXY_PORT
        text: str = proxy_instructions(host, port, routes, frozen)
        text += f"\nChat speaks as: {self.active_relay or 'Mystery slot'} (!mystery_relay <slot> to switch)"
        return text

    def _refresh_ui(self) -> None:
        try:
            if self.mystery_tab is not None:
                self.mystery_tab.update_status()
            if self.proxy_tab is not None:
                self.proxy_tab.update_status()
            if self.relay_tracker_tab is not None:
                try:
                    # RelayTrackerTab has refresh_all
                    self.relay_tracker_tab.refresh_all()
                except Exception:
                    pass
        except Exception:
            pass

    def _refresh_hints_ui(self) -> None:
        """Refresh hints UI."""
        try:
            if self.ui is not None:
                self.ui.update_hints()
        except Exception:
            pass

    async def drop_all_relays(self, reason: str = "main connection lost") -> None:
        """Drop all relays."""
        for slot in list(self.relays):
            relay: Optional["RelayContext"] = self.relays.pop(slot, None)
            if relay is None:
                continue
            try:
                relay.disconnected_intentionally = True
            except Exception:
                pass
            try:
                await relay.disconnect()
            except Exception:
                pass
        self.active_relay = None
        if self.proxy is not None:
            for slot in list(self.real_slots):
                try:
                    self.proxy.notify_relay_failed(slot, reason)
                except Exception:
                    pass
        if self.global_bridge is not None:
            for slot in list(self.real_slots):
                try:
                    self.global_bridge.notify_relay_failed(slot, reason)
                except Exception:
                    pass
        self._refresh_ui()
        if reason != "client disconnecting":
            client_logger.info("Mystery: all relays dropped (%s)", reason)

    async def connection_closed(self) -> None:
        await super().connection_closed()
        await self.drop_all_relays("main connection closed")
        # Ensure no stale slot_data remains for next connect
        self._clear_session_state()

    def _clear_session_state(self) -> None:
        """Clear all per-connection state to avoid desync on reconnect."""
        # Puzzles / unlocks
        self.puzzle_names = []
        self.unlock_map = {}
        self.solved_puzzles = set()
        self.revealed_unlocks = {}
        self.lock_mode = LOCK_OFF
        self.real_slots = {}
        self.untouched_slots = {}
        self.identities = {}
        self.unlocked_slots = {}
        self.scrambled = False
        self.expose_proxied_items = True
        self.puzzle_pieces = {}
        self.puzzle_hints = {}
        self.puzzle_state = {}
        self.caches = {}
        # Nuzlocke
        self.nuzlocke_enabled = False
        self.nuzlocke_deathlink = 0
        self.nuzlocke_per_game_modes = {}
        self.nuzlocke_lives = 1
        self.nuzlocke_lives_per_slot = {}
        self.nuzlocke_hits = {}
        self.nuzlocke_extra_lives = 0
        self.nuzlocke_extra_distribution = 0
        self.nuzlocke_extra_assignments = []
        self.nuzlocke_extra_earned = {}
        self.nuzlocke_dead = set()
        self.nuzlocke_set_hits = {}
        self.nuzlocke_set_extra_earned = {}
        # Custom goal
        self.custom_goal_enabled = False
        self.custom_goal_locations = set()
        self.custom_goal_items = {}
        self.custom_goal_any_items = False
        self.custom_goal_tag = "mystery_custom_goal"
        self.custom_goal_token = "Mystery Goal Token"
        self.custom_goal_internal_map = {}
        self.custom_goal_pairs = []
        self.custom_goal_reward_map = {}
        self.custom_goal_reward_paired = False
        self.custom_goal_done = False
        # Relays
        self.relays = {}
        self.active_relay = None
        self.relay_disabled = set()
        # Ensure proxy/bridge state is not stale (ports kept, but routes cleared)
        if self.proxy is not None:
            try:
                self.proxy.routes.clear()
                self.proxy.game_sockets.clear()
                self.proxy._sockets.clear()
                self.proxy._socket_alias.clear()
                self.proxy._socket_slot.clear()
                self.proxy._socket_tags.clear()
                self.proxy._socket_handling.clear()
                self.proxy._socket_sent_connected.clear()
                self.proxy.slot_to_sockets.clear()
                self.proxy.slot_to_aliases.clear()
                self.proxy.preamble.clear()
                self.proxy.pending_packets.clear()
            except Exception:
                pass
        if self.global_bridge is not None:
            try:
                self.global_bridge.routes.clear()
                self.global_bridge.game_sockets.clear()
                self.global_bridge._sockets.clear()
                self.global_bridge._socket_alias.clear()
                self.global_bridge._socket_slot.clear()
                self.global_bridge._socket_tags.clear()
                self.global_bridge._socket_handling.clear()
                self.global_bridge._socket_sent_connected.clear()
                self.global_bridge.slot_to_sockets.clear()
                self.global_bridge.slot_to_aliases.clear()
                self.global_bridge.preamble.clear()
                self.global_bridge.pending_packets.clear()
            except Exception:
                pass
        self._refresh_ui()

    async def disconnect(self, allow_autoreconnect: bool = False) -> None:
        """Disconnect - ensure full cleanup so reconnect is fresh."""
        await self.drop_all_relays("client disconnecting")
        if self.proxy is not None:
            try:
                await self.stop_proxy()
            except Exception:
                pass
        if self.global_bridge is not None:
            try:
                await self.stop_global_bridge()
            except Exception:
                pass
        self._clear_session_state()
        await super().disconnect(allow_autoreconnect)

    def make_gui(self) -> Any:
        """GUI manager."""
        return MysteryManager

def _game_known_locally(game: str) -> bool:
    """Check local datapackage."""
    try:
        from worlds import network_data_package
        return "checksum" in network_data_package.get("games", {}).get(game, {})
    except Exception:
        return False

class RelayContext(CommonContext):
    """Relay context."""
    game: str = "Mystery Relay"
    tags = CommonContext.tags | {"MysteryRelay"}
    items_handling: int = 0b111

    def __init__(self, server_address: Optional[str], password: Optional[str],
                 game: str, slot_name: str, owner: MysteryContext,
                 server_game: Optional[str] = None) -> None:
        self.real_game: str = game
        self.relay_slot: str = slot_name
        self.owner: MysteryContext = owner
        self.frozen: bool = True
        self.aliased: bool = False
        self.connect_error: Optional[str] = None
        self.game = game if _game_known_locally(game) else "Archipelago"
        super().__init__(server_address, password)
        if server_game:
            self.game = server_game

    async def server_auth(self, password_requested: bool = False) -> None:
        """Authenticate relay."""
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        if self.owner.proxy is not None:
            stored: set = self.owner.proxy.game_tags.get(self.relay_slot, set())
            if stored:
                self.tags = set(stored) | {"MysteryRelay"}
        await self.send_connect(name=self.auth, password=self.password)

    def event_invalid_game(self) -> None:
        self.connect_error = "InvalidGame"
        if self.owner.proxy is not None:
            self.owner.proxy.notify_relay_failed(self.relay_slot, "InvalidGame")
        client_logger.warning("Mystery: relay for %s refused (InvalidGame)", self.relay_slot)

    def event_invalid_slot(self) -> None:
        self.connect_error = "InvalidSlot"
        if self.owner.proxy is not None:
            self.owner.proxy.notify_relay_failed(self.relay_slot, "InvalidSlot")
        client_logger.warning("Mystery: relay for %s refused (InvalidSlot)", self.relay_slot)

    def consume_network_item_groups(self) -> None:
        """No-op."""

    def consume_network_location_groups(self) -> None:
        """No-op."""

    async def connection_closed(self) -> None:
        await super().connection_closed()
        try:
            if not self.owner._main_online():
                self.disconnected_intentionally = True
                if self.owner.relays.get(self.relay_slot) is self:
                    self.owner.relays.pop(self.relay_slot, None)
                if self.owner.active_relay == self.relay_slot:
                    self.owner.active_relay = None
                if self.owner.proxy is not None:
                    self.owner.proxy.notify_relay_failed(
                        self.relay_slot, "main connection closed")
                self.owner._refresh_ui()
        except Exception:
            pass

    async def _maybe_alias(self) -> None:
        """Maybe alias."""
        if self.aliased:
            return
        try:
            if not self.server or self.slot is None:
                return
        except Exception:
            return
        real: str = self.owner.identities.get(self.relay_slot, {}).get("name", self.relay_slot)
        if real == self.relay_slot:
            return
        if self.relay_slot not in self.owner.unlocked_slots:
            return
        self.aliased = True
        await self.send_msgs([{"cmd": "Say", "text": f"!alias {real[:16]}"}])

    def on_package(self, cmd: str, args: dict) -> None:
        if cmd in ("Connected", "RoomInfo"):
            super().on_package(cmd, args)
            if cmd == "Connected":
                # Store slot_data for optional Relay Tracker tab
                try:
                    self.slot_data = dict(args.get("slot_data", {}))  # type: ignore[attr-defined]
                except Exception:
                    self.slot_data = {}  # type: ignore[attr-defined]
                # Notify relay tracker tab if present
                try:
                    if getattr(self.owner, "relay_tracker_tab", None) is not None:
                        self.owner._refresh_ui()
                except Exception:
                    pass
            if self.owner.proxy is not None:
                async_start(self.owner.proxy.note_preamble(self.relay_slot, cmd, dict(args)))
            if cmd == "Connected":
                async_start(self.owner.flush_slot(self.relay_slot))
                async_start(self._maybe_alias())
            return
        if cmd == "ReceivedItems":
            # Forward or stash
            if self.owner.is_locked(self.relay_slot):
                items: List[dict] = [
                    {"item": item.item, "location": item.location,
                     "player": item.player, "flags": int(item.flags),
                     "index": idx}
                    for idx, item in enumerate(args.get("items", []), start=args.get("index", 0))
                ]
                async_start(self.owner.stash_items(self.relay_slot, items))
                return
            if self.owner.proxy is not None:
                async_start(self.owner.proxy.send_to_slot_game(
                    self.relay_slot, {"cmd": cmd, **args}))
            return
        if self.owner.proxy is not None and cmd in (
                "Print", "PrintJSON", "LocationInfo", "RoomUpdate", "DataPackage", "Bounced", "InvalidPacket"):
            if cmd == "DataPackage" and not getattr(self.owner, "expose_proxied_items", True):
                data = args.get("data", {})
                if isinstance(data, dict) and isinstance(data.get("games"), dict):
                    filtered_games = {k: v for k, v in data["games"].items() if k in ("Archipelago", "Mystery Game")}
                    args = dict(args, data=dict(data, games=filtered_games))
            elif cmd == "DataPackage" and getattr(self.owner, "expose_proxied_items", True):
                try:
                    data = args.get("data", {})
                    games_dict = data.get("games", {})
                    if isinstance(games_dict, dict):
                        new_games = dict(games_dict)
                        for info in self.owner.identities.values():
                            real = info.get("game")
                            server = info.get("server_game")
                            if isinstance(real, str) and isinstance(server, str) and server in games_dict and real not in new_games:
                                new_games[real] = games_dict[server]
                        if len(new_games) != len(games_dict):
                            args = dict(args, data=dict(data, games=new_games))
                except Exception:
                    pass
            async_start(self.owner.proxy.send_to_slot_game(
                self.relay_slot, {"cmd": cmd, **args}))
            return
        super().on_package(cmd, args)
        if self.owner.proxy is not None and cmd in (
                "Print", "PrintJSON", "Retrieved", "SetReply", "LocationInfo",
                "RoomUpdate", "DataPackage", "Bounced", "InvalidPacket"):
            if cmd == "DataPackage" and not getattr(self.owner, "expose_proxied_items", True):
                data = args.get("data", {})
                if isinstance(data, dict) and isinstance(data.get("games"), dict):
                    allowed = {"Archipelago", "Mystery Game"}
                    try:
                        real = self.owner.real_slots.get(self.relay_slot, "")
                        if isinstance(real, str) and real:
                            allowed.add(real)
                        info = self.owner.identities.get(self.relay_slot, {})
                        rg = info.get("game")
                        if isinstance(rg, str) and rg:
                            allowed.add(rg)
                    except Exception:
                        pass
                    filtered_games = {k: v for k, v in data["games"].items() if k in allowed}
                    args = dict(args, data=dict(data, games=filtered_games))
            async_start(self.owner.proxy.send_to_slot_game(
                self.relay_slot, {"cmd": cmd, **args}))
        if cmd == "Retrieved":
            try:
                if any("_read_hints_" in str(key) for key in args.get("keys", {})):
                    self.owner._refresh_hints_ui()
            except Exception:
                pass
        elif cmd == "SetReply":
            try:
                if "_read_hints_" in str(args.get("key", "")):
                    self.owner._refresh_hints_ui()
            except Exception:
                pass

class MysteryProxy:
    """Local proxy for games."""

    def __init__(self, owner: MysteryContext, host: str, port: int, is_global: bool = False) -> None:
        self.owner: MysteryContext = owner
        self.host: str = host
        self.port: int = port
        self.is_global: bool = bool(is_global)
        self.routes: Dict[str, str] = {}
        # Multi-client tracking: alias -> list of sockets, slot -> list of sockets, plus per-socket metadata
        self.game_sockets: Dict[str, List[Any]] = {}  # alias -> list[websocket] (multi-client)
        self._sockets: Dict[int, Any] = {}  # id(ws) -> websocket
        self._socket_alias: Dict[int, str] = {}  # id -> alias
        self._socket_slot: Dict[int, str] = {}  # id -> slot
        self._socket_tags: Dict[int, set] = {}  # id -> tags set
        self._socket_handling: Dict[int, int] = {}  # id -> items_handling
        self._socket_sent_connected: set = set()  # set of id(ws) that have received Connected preamble
        self.slot_to_sockets: Dict[str, List[Any]] = {}  # slot -> list[websocket]
        self.slot_to_aliases: Dict[str, set] = {}  # slot -> set(alias)
        self.preamble: Dict[str, List[dict]] = {}
        self._relay_events: Dict[str, asyncio.Event] = {}
        self._relay_failed: Dict[str, str] = {}
        self._known_checksums: Dict[str, str] = {}
        self.game_tags: Dict[str, set] = {}  # aggregated union per slot
        self.game_items_handling: Dict[str, int] = {}  # aggregated OR per slot
        self._sent_connected: set = set()  # legacy alias set (compat)
        self.slot_servers: Dict[str, Any] = {}
        self.slot_ports: Dict[str, int] = {}
        self.pending_packets: Dict[str, List[dict]] = {}
        self.server: Any = None
        self.running: bool = False

    # ---------- Multi-client helpers ----------
    def _sid(self, ws: Any) -> int:
        """_sid."""
        return id(ws)

    def _register_socket(self, ws: Any, alias: str, slot: str, tags: Optional[set] = None, handling: Optional[int] = None) -> None:
        """_register_socket."""
        sid = self._sid(ws)
        self._sockets[sid] = ws
        self._socket_alias[sid] = alias
        self._socket_slot[sid] = slot
        if tags is not None:
            self._socket_tags[sid] = set(tags)
        if handling is not None:
            self._socket_handling[sid] = int(handling)
        # alias -> list
        self.game_sockets.setdefault(alias, [])
        if ws not in self.game_sockets[alias]:
            self.game_sockets[alias].append(ws)
        # slot -> list
        self.slot_to_sockets.setdefault(slot, [])
        if ws not in self.slot_to_sockets[slot]:
            self.slot_to_sockets[slot].append(ws)
        self.slot_to_aliases.setdefault(slot, set()).add(alias)
        self.routes[alias] = slot
        self._recompute_slot_aggregates(slot)

    def _unregister_socket(self, ws: Any) -> Optional[tuple[str, str]]:
        """_unregister_socket."""
        sid = self._sid(ws)
        alias = self._socket_alias.pop(sid, None)
        slot = self._socket_slot.pop(sid, None)
        self._sockets.pop(sid, None)
        self._socket_tags.pop(sid, None)
        self._socket_handling.pop(sid, None)
        self._socket_sent_connected.discard(sid)
        if alias is not None and alias in self.game_sockets:
            lst = self.game_sockets[alias]
            if ws in lst:
                lst.remove(ws)
            if not lst:
                self.game_sockets.pop(alias, None)
                self.routes.pop(alias, None)
                self._sent_connected.discard(alias)
        if slot is not None and slot in self.slot_to_sockets:
            lst2 = self.slot_to_sockets[slot]
            if ws in lst2:
                lst2.remove(ws)
            if not lst2:
                self.slot_to_sockets.pop(slot, None)
                self.slot_to_aliases.pop(slot, None)
                # keep aggregates? recompute will clear
            else:
                self._recompute_slot_aggregates(slot)
        else:
            if slot is not None:
                self._recompute_slot_aggregates(slot)
        if alias is not None:
            self._sent_connected.discard(alias)
        return (alias, slot) if alias and slot else None

    def _recompute_slot_aggregates(self, slot: str) -> None:
        """_recompute_slot_aggregates."""
        tags_union: set = set()
        handling_or: Optional[int] = None
        has_any = False
        for sid, s_slot in list(self._socket_slot.items()):
            if s_slot == slot:
                has_any = True
                tags_union.update(self._socket_tags.get(sid, set()))
                h = self._socket_handling.get(sid)
                if isinstance(h, int):
                    if handling_or is None:
                        handling_or = h
                    else:
                        handling_or |= h
        if has_any:
            if tags_union:
                self.game_tags[slot] = tags_union
            else:
                self.game_tags.pop(slot, None)
            if handling_or is not None:
                self.game_items_handling[slot] = handling_or
            else:
                self.game_items_handling.pop(slot, None)
        else:
            self.game_tags.pop(slot, None)
            self.game_items_handling.pop(slot, None)

    def _get_sockets_for_slot(self, slot: str) -> List[Any]:
        """_get_sockets_for_slot."""
        return list(self.slot_to_sockets.get(slot, []))

    def _get_sockets_for_alias(self, alias: str) -> List[Any]:
        """_get_sockets_for_alias."""
        return list(self.game_sockets.get(alias, []))

    def _get_handling_for_socket(self, ws: Any) -> Optional[int]:
        """_get_handling_for_socket."""
        sid = self._sid(ws)
        if sid in self._socket_handling:
            return self._socket_handling[sid]
        slot = self._socket_slot.get(sid)
        if slot and slot in self.game_items_handling:
            return self.game_items_handling[slot]
        return None

    async def start(self) -> None:
        try:
            import websockets
        except ImportError:
            client_logger.warning("Mystery: websockets not installed; proxy unavailable")
            return
        owner: MysteryContext = self.owner

        async def handler(websocket: Any, path: str = "/", owner: MysteryContext = owner) -> None:
            try:
                peer: Any = getattr(websocket, "remote_address", "?")
            except Exception:
                peer = "?"
            logger.info("MysteryProxy: incoming game connection from %s", peer)
            try:
                await websocket.send(encode([self._hello_room_info()]))
            except Exception as exc:
                logger.debug("MysteryProxy: hello failed for %s: %s", peer, exc)
                try:
                    await websocket.close()
                except Exception:
                    pass
                return
            await self._socket_loop(websocket, None)

        try:
            self.server = await websockets.serve(
                functools.partial(handler, owner=owner),
                host=self.host, port=self.port, ping_interval=20, ping_timeout=999999)
        except OSError as exc:
            client_logger.warning("Mystery: proxy cannot listen on ws://%s:%d (%s). "
                                  "Is another proxy running?", self.host, self.port, exc)
            self.server = None
            return
        self.running = True
        if getattr(self, "is_global", False):
            logger.info("MysteryGlobalBridge listening on ws://%s:%d (broadcast, APWorld not required, shared)", self.host, self.port)
        else:
            logger.info("MysteryProxy listening on ws://%s:%d", self.host, self.port)
        if getattr(self, "is_global", False):
            return
        for index, slot in enumerate(sorted(self.owner.real_slots)):
            desired = self.port + 1 + index
            slot_port: int = find_free_port(self.host, desired)
            used_ports = set(self.slot_ports.values())
            tries = 0
            while slot_port in used_ports and tries < 20:
                slot_port = find_free_port(self.host, slot_port + 1)
                tries += 1

            def _slot_handler(websocket: Any, path: str = "/",
                              _slot: str = slot) -> Any:
                return self._serve_slot_socket(websocket, _slot)

            try:
                slot_server = await websockets.serve(
                    _slot_handler, host=self.host, port=slot_port,
                    ping_interval=20, ping_timeout=999999)
            except OSError as exc:
                fallback = find_free_port(self.host, slot_port + 1)
                if fallback != slot_port:
                    try:
                        slot_server = await websockets.serve(
                            _slot_handler, host=self.host, port=fallback,
                            ping_interval=20, ping_timeout=999999)
                        slot_port = fallback
                    except OSError as exc2:
                        client_logger.warning("Mystery: no slot listener for %s on :%d (%s).",
                                              slot, slot_port, exc2)
                        continue
                else:
                    client_logger.warning("Mystery: no slot listener for %s on :%d (%s).",
                                          slot, slot_port, exc)
                    continue
            self.slot_servers[slot] = slot_server
            self.slot_ports[slot] = slot_port
            logger.info("MysteryProxy: slot listener for %s on ws://%s:%d", slot, self.host, slot_port)

    async def _serve_slot_socket(self, websocket: Any, slot: str) -> None:
        """Serve slot socket."""
        try:
            peer: Any = getattr(websocket, "remote_address", "?")
        except Exception:
            peer = "?"
        logger.info("MysteryProxy: %s connected on its slot port (%s)", slot, peer)
        relay: Optional[RelayContext] = self.owner.relays.get(slot)
        if relay is not None and slot in self._relay_failed:
            self.owner.relays.pop(slot, None)
            relay = None
        if relay is None:
            self.owner.start_relay(slot, make_active=False)
            relay = self.owner.relays.get(slot)
            if relay is None:
                await self._send_connect_error(websocket, self._relay_refusal(slot))
                try:
                    await websocket.close()
                except Exception:
                    pass
                return
        if not await self._wait_relay(slot, lambda: self._has_roominfo(slot), timeout=30):
            await self._send_connect_error(
                websocket, f"MysteryProxy: could not reach {slot} "
                           f"({self._relay_failed.get(slot, 'relay unreachable')}).")
            try:
                await websocket.close()
            except Exception:
                pass
            return
        await websocket.send(encode([self._hello_room_info()]))
        await self._socket_loop(websocket, slot)

    async def ensure_slot_port(self, slot: str) -> Optional[int]:
        """Ensure slot port."""
        if slot in self.slot_ports:
            return self.slot_ports[slot]
        base = self.port + 1 + len(self.slot_ports)
        other_ports: set[int] = set()
        try:
            other = getattr(self.owner, "proxy", None)
            if other is not None and other is not self:
                other_ports.update(other.slot_ports.values())
                if getattr(other, "port", None):
                    other_ports.add(int(other.port))
            other2 = getattr(self.owner, "global_bridge", None)
            if other2 is not None and other2 is not self:
                other_ports.update(other2.slot_ports.values())
                if getattr(other2, "port", None):
                    other_ports.add(int(other2.port))
        except Exception:
            pass
        port = find_free_port(self.host, base)
        tries = 0
        while port in other_ports or port in self.slot_ports.values():
            port = find_free_port(self.host, port + 1)
            tries += 1
            if tries > 30:
                break
        def _slot_handler(websocket: Any, path: str = "/", _slot: str = slot) -> Any:
            return self._serve_slot_socket(websocket, _slot)
        try:
            import websockets
            server = await websockets.serve(
                _slot_handler, host=self.host, port=port,
                ping_interval=20, ping_timeout=999999)
            self.slot_servers[slot] = server
            self.slot_ports[slot] = port
            logger.info("MysteryProxy: allocated dedicated port %d for %s on %s:%d", port, slot, self.host, port)
            return port
        except OSError as exc:
            logger.warning("MysteryProxy: could not allocate dedicated port for %s on :%d (%s)", slot, port, exc)
            try:
                alt = find_free_port(self.host, port + 1)
                server = await websockets.serve(
                    _slot_handler, host=self.host, port=alt,
                    ping_interval=20, ping_timeout=999999)
                self.slot_servers[slot] = server
                self.slot_ports[slot] = alt
                logger.info("MysteryProxy: allocated fallback port %d for %s", alt, slot)
                return alt
            except Exception as exc2:
                logger.warning("MysteryProxy: fallback also failed for %s (%s)", slot, exc2)
                return None

    def _relay_refusal(self, slot: str) -> str:
        """Relay failure reason."""
        try:
            if self.owner.is_nuzlocke_dead(slot):
                return f"MysteryProxy: {slot} is dead (Nuzlocke) – relay permanently closed."
            if slot in self.owner.relay_disabled:
                return (f"MysteryProxy: relay for {slot} was stopped "
                        f"(!mystery_relay {slot} to restart).")
            if not self.owner._main_online():
                return ("MysteryProxy: mystery slot is not connected to the server; "
                        "relay unavailable.")
        except Exception:
            pass
        return f"MysteryProxy: could not start relay for {slot}."

    def _roominfo_for(self, slot: str) -> dict:
        """RoomInfo for slot."""
        for packet in self.preamble.get(slot, []):
            if packet.get("cmd") == "RoomInfo":
                return packet
        return {"cmd": "RoomInfo"}

    async def _wait_relay(self, slot: str, ready: Any, timeout: float = 30.0) -> bool:
        """Wait for relay."""
        event: asyncio.Event = self._relay_events.setdefault(slot, asyncio.Event())
        event.clear()
        if ready():
            return True
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        return bool(ready())

    async def _socket_loop(self, websocket: Any, fixed_slot: Optional[str]) -> None:
        """Socket loop."""
        alias: Optional[str] = None
        try:
            peer: Any = getattr(websocket, "remote_address", "?")
        except Exception:
            peer = "?"
        got_message: bool = False
        try:
            async for data in websocket:
                try:
                    messages: Any = decode(data)
                except Exception as exc:
                    logger.warning("MysteryProxy: dropping undecodable chunk: %s", exc)
                    await self._send_invalid_packet(
                        websocket, None, f"Undecodable packet: {exc}")
                    continue
                for msg in messages:
                    try:
                        if not isinstance(msg, dict) or not isinstance(msg.get("cmd"), str):
                            await self._send_invalid_packet(
                                websocket, None,
                                f"Malformed packet (missing cmd): {str(msg)[:160]}")
                            continue
                        got_message = True
                        if msg.get("cmd") == "Connect":
                            alias = await self._handle_connect(websocket, msg, fixed_slot)
                            if alias is None:
                                return
                        else:
                            if alias is None:
                                continue
                            await self._handle_game_message(websocket, alias, msg)
                    except Exception as exc:
                        logger.warning("MysteryProxy: dropping bad message: %s", exc)
                        await self._send_invalid_packet(
                            websocket, msg.get("cmd") if isinstance(msg, dict) else None,
                            f"Proxy failed to handle packet: {exc}")
                        continue
        except Exception as exc:
            logger.debug("MysteryProxy socket closed: %s", exc)
        finally:
            if not got_message:
                logger.info("MysteryProxy: %s closed without sending anything "
                            "(probe, retry abort, or wrong address?)", peer)
            # Multi-client unregister - only remove this socket, not all for alias
            try:
                self._unregister_socket(websocket)
            except Exception:
                # Fallback legacy cleanup
                if alias is not None:
                    try:
                        lst = self.game_sockets.get(alias, [])
                        if websocket in lst:
                            lst.remove(websocket)
                            if not lst:
                                self.game_sockets.pop(alias, None)
                                self.routes.pop(alias, None)
                    except Exception:
                        self.game_sockets.pop(alias, None)
                    self._sent_connected.discard(alias)

    async def stop(self) -> None:
        self.running = False
        # Close all multi-client sockets
        all_sockets: List[Any] = []
        try:
            all_sockets.extend(list(self._sockets.values()))
        except Exception:
            pass
        # Fallback: legacy game_sockets lists
        for lst in list(self.game_sockets.values()):
            if isinstance(lst, list):
                all_sockets.extend(lst)
            else:
                all_sockets.append(lst)
        # Deduplicate
        seen_ids = set()
        uniq: List[Any] = []
        for s in all_sockets:
            sid = id(s)
            if sid not in seen_ids:
                seen_ids.add(sid)
                uniq.append(s)
        for socket in uniq:
            try:
                await socket.close()
            except Exception:
                pass
        self.game_sockets.clear()
        self._sockets.clear()
        self._socket_alias.clear()
        self._socket_slot.clear()
        self._socket_tags.clear()
        self._socket_handling.clear()
        self._socket_sent_connected.clear()
        self.slot_to_sockets.clear()
        self.slot_to_aliases.clear()
        self.game_tags.clear()
        self.game_items_handling.clear()
        for slot, slot_server in list(self.slot_servers.items()):
            try:
                slot_server.close()
                await slot_server.wait_closed()
            except Exception:
                pass
        self.slot_servers.clear()
        self.slot_ports.clear()
        if self.server is not None:
            try:
                self.server.close()
                await self.server.wait_closed()
            except Exception:
                pass
            self.server = None

    def slot_for_alias(self, alias: str) -> Optional[str]:
        """Resolve alias."""
        if alias in self.routes:
            return self.routes[alias]
        if alias in self.owner.real_slots:
            return alias
        return None

    def notify_relay_ready(self, slot: str) -> None:
        """Mark relay ready."""
        self._relay_failed.pop(slot, None)
        self._relay_events.setdefault(slot, asyncio.Event()).set()

    def notify_relay_failed(self, slot: str, error: str) -> None:
        """Mark relay failed."""
        self._relay_failed[slot] = error
        self._relay_events.setdefault(slot, asyncio.Event()).set()

    def _has_roominfo(self, slot: str) -> bool:
        return any(packet.get("cmd") == "RoomInfo" for packet in self.preamble.get(slot, []))

    def _relay_preamble_ready(self, slot: str) -> bool:
        relay: Optional[RelayContext] = self.owner.relays.get(slot)
        return (bool(self.preamble.get(slot)) and relay is not None
                and bool(relay.server) and relay.slot is not None)

    def _relay_online_ready(self, slot: str) -> bool:
        """Relay online."""
        relay: Optional[RelayContext] = self.owner.relays.get(slot)
        return relay is not None and bool(relay.server) and relay.slot is not None

    async def _handle_connect(self, websocket: Any, msg: dict,
                              fixed_slot: Optional[str] = None) -> Optional[str]:
        alias: Any = msg.get("name", "")
        slot: Optional[str] = self.slot_for_alias(alias) if isinstance(alias, str) else None
        if fixed_slot is not None:
            if slot is not None and slot != fixed_slot:
                await websocket.send(encode([{"cmd": "PrintJSON", "data": [
                    {"text": f"MysteryProxy: this address serves {fixed_slot}, not {slot}."}]}]))
                await websocket.close()
                return None
            slot = fixed_slot
            if not isinstance(alias, str) or not alias:
                alias = fixed_slot
        if slot is None and isinstance(alias, str):
            untouched: Optional[str] = self.owner.match_untouched(alias)
            if untouched is not None:
                await websocket.send(encode([{"cmd": "PrintJSON", "data": [
                    {"text": f"MysteryProxy: {untouched} is not managed by Mystery; "
                             "connect to the server directly."}]}]))
                await websocket.close()
                return None
        if slot is None:
            await websocket.send(encode([{"cmd": "PrintJSON", "data": [
                {"text": f"MysteryProxy: unknown alias {alias!r}. Ask for !mystery_proxy help."}]}]))
            await websocket.close()
            return None
        if self.owner.is_nuzlocke_dead(slot):
            await websocket.send(encode([{"cmd": "PrintJSON", "data": [
                {"text": f"Mystery: {slot} is dead (Nuzlocke) – relay permanently closed."}]}]))
            try:
                self.owner.relay_disabled.add(slot)
                if self.owner.proxy is not None:
                    self.owner.proxy.notify_relay_failed(slot, "Nuzlocke dead")
                if self.owner.global_bridge is not None:
                    self.owner.global_bridge.notify_relay_failed(slot, "Nuzlocke dead")
            except Exception:
                pass
            await websocket.close()
            return None
        if self.owner.lock_mode == LOCK_GUESS and self.owner.is_locked(slot):
            await websocket.send(encode([{"cmd": "PrintJSON", "data": [
                {"text": "This game isn't unlocked yet."}]}]))
            await websocket.close()
            return None
        # Multi-client: parse tags/handling per-socket
        incoming_tags: set = set()
        try:
            incoming: Any = msg.get("tags", [])
            if isinstance(incoming, list):
                incoming_tags = {str(tag) for tag in incoming}
        except Exception:
            incoming_tags = set()
        incoming_handling: Optional[int] = None
        try:
            ih_tmp = msg.get("items_handling")
            if isinstance(ih_tmp, int) and 0 <= ih_tmp <= 7:
                incoming_handling = int(ih_tmp)
        except Exception:
            incoming_handling = None
        # Register socket (multi-client)
        try:
            self._register_socket(websocket, alias, slot, incoming_tags, incoming_handling)
        except Exception:
            # Fallback legacy
            self.routes[alias] = slot
            if alias not in self.game_sockets:
                self.game_sockets[alias] = []
            if websocket not in self.game_sockets[alias]:
                self.game_sockets[alias].append(websocket)
            if incoming_tags:
                self.game_tags[slot] = incoming_tags
            if incoming_handling is not None:
                self.game_items_handling[slot] = incoming_handling
        logger.info("MysteryProxy: %s connected as %s (handling=%s tags=%s) [total %d client(s) for %s]",
                    alias, slot, incoming_handling, sorted(incoming_tags) if incoming_tags else "[]",
                    len(self._get_sockets_for_slot(slot)), slot)
        relay: Optional[RelayContext] = self.owner.relays.get(slot)
        if relay is not None and slot in self._relay_failed:
            self.owner.relays.pop(slot, None)
            relay = None
        if relay is None:
            try:
                ih = self.game_items_handling.get(slot)
                if isinstance(ih, int):
                    self.owner._pending_items_handling = getattr(self.owner, "_pending_items_handling", {})
                    self.owner._pending_items_handling[slot] = ih
            except Exception:
                pass
            self.owner.start_relay(slot, make_active=False)
            relay = self.owner.relays.get(slot)
            if relay is None:
                await self._send_connect_error(websocket, self._relay_refusal(slot))
                try:
                    self._unregister_socket(websocket)
                except Exception:
                    self.routes.pop(alias, None)
                    try:
                        lst = self.game_sockets.get(alias, [])
                        if websocket in lst:
                            lst.remove(websocket)
                            if not lst:
                                self.game_sockets.pop(alias, None)
                    except Exception:
                        self.game_sockets.pop(alias, None)
                try:
                    await websocket.close()
                except Exception:
                    pass
                return None
            try:
                ih = self.game_items_handling.get(slot)
                if isinstance(ih, int) and relay is not None:
                    relay.items_handling = ih
            except Exception:
                pass
        else:
            try:
                # Update relay tags/handling from aggregated union across all clients for this slot
                aggregated_tags = self.game_tags.get(slot, set())
                if aggregated_tags:
                    relay.tags = set(aggregated_tags) | {"MysteryRelay"}
                aggregated_handling = self.game_items_handling.get(slot)
                if isinstance(aggregated_handling, int) and getattr(relay, "items_handling", 0b111) != aggregated_handling:
                    relay.items_handling = aggregated_handling
                    await relay.send_connect(name=relay.auth, password=relay.password)
                elif aggregated_tags:
                    await relay.send_connect(name=relay.auth, password=relay.password)
                else:
                    pass
            except Exception as exc:
                logger.debug("MysteryProxy: relay re-auth skipped for %s: %s", slot, exc)
        if self._relay_preamble_ready(slot):
            await self._send_preamble(websocket, alias, slot)
        else:
            if not await self._wait_relay(
                    slot, lambda: self._relay_preamble_ready(slot), timeout=30):
                reason: str = self._relay_failed.get(slot, "relay unreachable")
                await self._send_connect_error(
                    websocket, f"MysteryProxy: could not reach {slot} ({reason}).")
                try:
                    self._unregister_socket(websocket)
                except Exception:
                    self.routes.pop(alias, None)
                    try:
                        lst = self.game_sockets.get(alias, [])
                        if websocket in lst:
                            lst.remove(websocket)
                            if not lst:
                                self.game_sockets.pop(alias, None)
                    except Exception:
                        self.game_sockets.pop(alias, None)
                try:
                    await websocket.close()
                except Exception:
                    pass
                return None
            await self._send_preamble(websocket, alias, slot)
        await self.deliver_held(slot)
        await self.deliver_pending(slot, alias)
        return alias

    async def _send_preamble(self, websocket: Any, alias: str, slot: str) -> None:
        """Send preamble."""
        # Use the explicit websocket, not alias lookup, to support multi-client
        target = websocket
        if target is None:
            # fallback to alias lookup
            lst = self.game_sockets.get(alias, [])
            if not lst:
                return
            target = lst[-1]
        sid = self._sid(target)
        # Avoid duplicate send per socket
        if sid in self._socket_sent_connected:
            return
        for packet in self.preamble.get(slot, []):
            if packet.get("cmd") == "RoomInfo":
                continue
            out: dict = self._connected_for(slot, packet)
            try:
                await target.send(encode([out]))
            except Exception:
                try:
                    self._unregister_socket(target)
                except Exception:
                    self.game_sockets.get(alias, []).remove(target)  # type: ignore
                return
        self._socket_sent_connected.add(sid)
        self._sent_connected.add(alias)

    async def _send_connect_error(self, websocket: Any, text: str) -> None:
        try:
            await websocket.send(encode([{"cmd": "PrintJSON", "data": [{"text": text}]}]))
        except Exception:
            pass

    async def _send_invalid_packet(
            self, websocket: Any, original_cmd: Any, text: str) -> None:
        """Send invalid packet."""
        try:
            await websocket.send(encode([{
                "cmd": "InvalidPacket",
                "type": "arguments",
                "original_cmd": original_cmd,
                "text": text,
            }]))
        except Exception:
            pass

    def _hello_room_info(self) -> dict:
        """Hello RoomInfo."""
        ctx = self.owner
        try:
            base: Dict[str, Any] = dict(getattr(ctx, "_last_roominfo", {}) or {})
        except Exception:
            base = {}
        if not isinstance(base.get("version"), (list, tuple)):
            base = {}
        if base:
            packet: dict = dict(base)
            packet["cmd"] = "RoomInfo"
            packet["password"] = False
            packet["time"] = time.time()
            try:
                guessy: bool = int(getattr(ctx, "lock_mode", 0)) == LOCK_GUESS
            except (TypeError, ValueError):
                guessy = False
            expose = bool(getattr(ctx, "expose_proxied_items", True))
            is_global = bool(getattr(self, "is_global", False))
            if not guessy:
                base_games: list[str] = []
                base_checksums: Dict[str, str] = {}
                try:
                    base_games = list(base.get("games", []))
                    base_checksums = dict(base.get("datapackage_checksums", {}))
                except Exception:
                    pass
                if is_global:
                    games: list[str] = ["Archipelago"]
                    if expose:
                        try:
                            all_games = set(base_games) | set(ctx.real_slots.values())
                            games = sorted(all_games | {"Archipelago"})
                        except Exception:
                            games = list(base_games) if base_games else ["Archipelago"]
                else:
                    games: list[str] = ["Archipelago", "Mystery Game"]
                    if expose:
                        try:
                            all_games = set(base_games) | set(ctx.real_slots.values())
                            games = sorted(all_games | {"Archipelago", "Mystery Game"})
                        except Exception:
                            pass
                packet["games"] = games
                try:
                    known: Dict[str, str] = dict(getattr(self, "_known_checksums", {}))
                except Exception:
                    known = {}
                try:
                    for game, checksum in dict(getattr(ctx, "checksums", {}) or {}).items():
                        if isinstance(game, str) and isinstance(checksum, str):
                            known.setdefault(game, checksum)
                    for game, checksum in base_checksums.items():
                        if isinstance(game, str) and isinstance(checksum, str):
                            known.setdefault(game, checksum)
                    # Also pull from _known_checksums (proxy's cache of all seen checksums)
                    try:
                        for game, checksum in dict(getattr(self, "_known_checksums", {}) or {}).items():
                            if isinstance(game, str) and isinstance(checksum, str):
                                known.setdefault(game, checksum)
                    except Exception:
                        pass
                except Exception:
                    pass
                if expose:
                    real_to_server: Dict[str, str] = {}
                    try:
                        for info in ctx.identities.values():
                            real = info.get("game")
                            server = info.get("server_game")
                            if isinstance(real, str) and isinstance(server, str):
                                if server in known and real not in known:
                                    # Always map real -> server checksum, even if server not in known yet (use base or ctx)
                                    # Try to find checksum for server in any source
                                    cs = known.get(server) or base_checksums.get(server) or getattr(ctx, "checksums", {}).get(server) or self._known_checksums.get(server)
                                    if cs:
                                        real_to_server.setdefault(real, cs)
                                    else:
                                        # Fallback: if we have no checksum for server, still map to allow GetDataPackage translation
                                        real_to_server.setdefault(real, known.get(server, ""))
                                elif server in known:
                                    real_to_server.setdefault(real, known[server])
                    except Exception:
                        pass
                    checksums: Dict[str, str] = {}
                    for game in games:
                        if game in known and known[game]:
                            checksums[game] = known[game]
                        elif game in real_to_server and real_to_server[game]:
                            checksums[game] = real_to_server[game]
                        elif game in base_checksums and base_checksums[game]:
                            checksums[game] = base_checksums[game]
                        else:
                            try:
                                if game in getattr(ctx, "checksums", {}):
                                    checksums[game] = ctx.checksums[game]
                                elif game in self._known_checksums:
                                    checksums[game] = self._known_checksums[game]
                            except Exception:
                                pass
                    # Ensure every game in `games` has a checksum entry, even if empty, to avoid TUNIC "incompatible"
                    # For TUNIC and other proxied games, ensure we have an entry even if we had to synthesize
                    for game in games:
                        if game not in checksums:
                            # Try to find via identities: if game is real, use server's checksum
                            try:
                                for info in ctx.identities.values():
                                    if info.get("game") == game and info.get("server_game") in known:
                                        checksums[game] = known[info.get("server_game")]
                                        break
                            except Exception:
                                pass
                    packet["datapackage_checksums"] = checksums
                else:
                    packet["datapackage_checksums"] = {
                        game: known[game] for game in games if game in known}
            else:
                packet["games"] = ["Archipelago"]
                packet["datapackage_checksums"] = {}
            return packet

        def _version(value: Any, fallback: list[int]) -> list[int]:
            try:
                parts: list[int] = [int(part) for part in list(value)]
                if len(parts) >= 3:
                    return parts[:3]
            except Exception:
                pass
            return fallback

        packet: dict = {
            "cmd": "RoomInfo",
            "password": False,
            "games": ["Archipelago"],
            "tags": ["AP"],
            "version": _version(getattr(ctx, "server_version", None), [0, 6, 7]),
            "permissions": {},
            "hint_cost": 10,
            "location_check_points": 1,
            "datapackage_checksums": {},
            "seed_name": str(getattr(ctx, "seed_name", "") or ""),
            "time": time.time(),
        }
        try:
            hint_cost: Any = getattr(ctx, "hint_cost", None)
            if isinstance(hint_cost, int):
                packet["hint_cost"] = hint_cost
        except Exception:
            pass
        try:
            generator: Any = getattr(ctx, "generator_version", None)
            if generator is not None:
                packet["generator_version"] = _version(generator, [0, 6, 7])
        except Exception:
            pass
        return packet

    async def _handle_game_message(self, websocket: Any, alias: str, msg: dict) -> None:
        """_handle_game_message."""
        sid = self._sid(websocket)
        # Resolve slot via per-socket mapping if available, else alias
        slot: Optional[str] = self._socket_slot.get(sid)
        if slot is None:
            slot = self.slot_for_alias(alias)
        if slot is None:
            return
        if msg.get("cmd") == "Connect":
            logger.debug("MysteryProxy: consumed game Connect for %s", alias)
            return
        relay: Optional[RelayContext] = self.owner.relays.get(slot)
        if relay is None:
            self.owner.start_relay(slot, make_active=False)
            relay = self.owner.relays.get(slot)
            if relay is None:
                # Send error to the specific websocket that sent the message
                try:
                    await websocket.send(encode([{"cmd": "PrintJSON", "data": [
                        {"text": self._relay_refusal(slot)}]}]))
                except Exception:
                    pass
                return
        if msg.get("cmd") == "LocationChecks":
            checks: List[int] = [loc for loc in msg.get("locations", []) if isinstance(loc, int)]
            if self.owner.is_locked(slot):
                await self.owner.stash_checks(slot, checks)
                return
            if relay is not None and relay.server:
                await relay.send_msgs([msg])
            else:
                await self.owner.stash_checks(slot, checks)
            return
        if relay is not None and not relay.server:
            if not await self._wait_relay(
                    slot, lambda: self._relay_online_ready(slot), timeout=10):
                logger.warning("MysteryProxy: relay for %s offline, dropping %s",
                               slot, msg.get("cmd"))
                try:
                    await websocket.send(encode([{"cmd": "PrintJSON", "data": [
                        {"text": f"MysteryProxy: relay for {slot} unreachable, "
                                 f"{msg.get('cmd')} dropped (retry)."}]}]))
                except Exception:
                    pass
                return
            relay = self.owner.relays.get(slot)
        if relay is not None and relay.server:
            if msg.get("cmd") == "Connect":
                logger.debug("MysteryProxy: consumed game Connect for %s", alias)
                return
            if msg.get("cmd") == "ConnectUpdate":
                try:
                    tags: Any = msg.get("tags", [])
                    if isinstance(tags, list):
                        cleaned: set = {str(tag) for tag in tags}
                        cleaned.discard("MysteryRelay")
                        # Update per-socket tags
                        self._socket_tags[sid] = cleaned
                        self._recompute_slot_aggregates(slot)
                        # Use aggregated for relay
                        aggregated = self.game_tags.get(slot, set())
                        msg = dict(msg, tags=sorted(aggregated | {"MysteryRelay"}))
                    ih = msg.get("items_handling")
                    if isinstance(ih, int) and 0 <= ih <= 7:
                        self._socket_handling[sid] = int(ih)
                        self._recompute_slot_aggregates(slot)
                        aggregated_h = self.game_items_handling.get(slot)
                        if aggregated_h is not None and getattr(relay, "items_handling", None) != aggregated_h:
                            relay.items_handling = aggregated_h
                except Exception:
                    pass
            if msg.get("cmd") == "Bounce":
                try:
                    tags = msg.get("tags", [])
                    if isinstance(tags, list) and "DeathLink" in tags and self.owner.nuzlocke_enabled:
                        mode = self.owner.get_nuzlocke_mode(slot)
                        cause = ""
                        try:
                            data = msg.get("data", {})
                            if isinstance(data, dict):
                                cause = str(data.get("cause") or data.get("source") or "")
                        except Exception:
                            cause = ""
                        # Determine which socket sent this Bounce for targeted feedback
                        sender_ws = websocket
                        if mode == 1:
                            async_start(self.owner.trigger_nuzlocke(slot, cause))
                            try:
                                await sender_ws.send(encode([{"cmd": "PrintJSON", "data": [{"text": f"Nuzlocke: {slot} died – relay permanently closed (DeathLink suppressed)."}]}]))
                                await sender_ws.close()
                            except Exception:
                                pass
                            try:
                                self._unregister_socket(sender_ws)
                            except Exception:
                                pass
                            return
                        elif mode == 2:
                            non_ids = self.owner.non_controlled_ids()
                            if non_ids:
                                iso_msg = dict(msg)
                                iso_msg["slots"] = non_ids
                                await relay.send_msgs([iso_msg])
                            async_start(self.owner.trigger_nuzlocke(slot, cause))
                            try:
                                await sender_ws.send(encode([{"cmd": "PrintJSON", "data": [{"text": f"Nuzlocke: {slot} died – relay permanently closed (DeathLink isolated)."}]}]))
                                await sender_ws.close()
                            except Exception:
                                pass
                            try:
                                self._unregister_socket(sender_ws)
                            except Exception:
                                pass
                            return
                        else:
                            await relay.send_msgs([msg])
                            async_start(self.owner.trigger_nuzlocke(slot, cause))
                            try:
                                await sender_ws.send(encode([{"cmd": "PrintJSON", "data": [{"text": f"Nuzlocke: {slot} died – relay permanently closed."}]}]))
                                await sender_ws.close()
                            except Exception:
                                pass
                            try:
                                self._unregister_socket(sender_ws)
                            except Exception:
                                pass
                            return
                except Exception:
                    pass
            if msg.get("cmd") == "GetDataPackage" and not getattr(self.owner, "expose_proxied_items", True):
                requested = msg.get("games", [])
                if isinstance(requested, list):
                    # Always allow the slot's real game even when not exposing, otherwise TUNIC etc. gets incompatible
                    allowed = {"Archipelago", "Mystery Game"}
                    try:
                        real = self.owner.real_slots.get(slot, "")
                        if isinstance(real, str) and real:
                            allowed.add(real)
                        # Also allow any game that is in identities for this slot
                        info = self.owner.identities.get(slot, {})
                        rg = info.get("game")
                        if isinstance(rg, str) and rg:
                            allowed.add(rg)
                    except Exception:
                        pass
                    filtered = [g for g in requested if g in allowed]
                    if not filtered:
                        try:
                            await websocket.send(encode([{"cmd": "DataPackage", "data": {"games": {}}}]))
                        except Exception:
                            pass
                        return
                    msg = dict(msg, games=filtered)
            elif msg.get("cmd") == "GetDataPackage" and getattr(self.owner, "expose_proxied_items", True):
                try:
                    requested = msg.get("games", [])
                    if isinstance(requested, list):
                        translated = []
                        for g in requested:
                            if isinstance(g, str):
                                hashed = None
                                for info in self.owner.identities.values():
                                    if info.get("game") == g:
                                        hashed = info.get("server_game")
                                        break
                                if hashed and hashed not in translated:
                                    translated.append(hashed)
                                if g not in translated:
                                    translated.append(g)
                            else:
                                translated.append(g)
                        if translated != requested:
                            msg = dict(msg, games=translated)
                except Exception:
                    pass
            await relay.send_msgs([msg])
        else:
            logger.warning("MysteryProxy: no relay for %s, dropping %s",
                           slot, msg.get("cmd"))
        # Also keep per-socket handling updated if message contained items_handling outside ConnectUpdate
        try:
            ih = msg.get("items_handling")
            if isinstance(ih, int) and 0 <= ih <= 7:
                if self._socket_handling.get(sid) != ih:
                    self._socket_handling[sid] = ih
                    self._recompute_slot_aggregates(slot)
        except Exception:
            pass

    async def note_preamble(self, slot: str, cmd: str, packet: dict) -> None:
        """Remember preamble."""
        stored: List[dict] = self.preamble.setdefault(slot, [])
        stored = [entry for entry in stored if entry.get("cmd") != cmd]
        stored.append({"cmd": cmd, **{k: v for k, v in packet.items() if k != "cmd"}})
        self.preamble[slot] = stored[-2:]
        if cmd == "RoomInfo":
            checksums: Any = packet.get("datapackage_checksums", {})
            if isinstance(checksums, dict):
                for game, checksum in checksums.items():
                    if isinstance(game, str) and isinstance(checksum, str):
                        self._known_checksums[game] = checksum
        self._relay_events.setdefault(slot, asyncio.Event()).set()

    async def send_to_slot_game(self, slot: str, packet: dict) -> None:
        """Forward to game."""
        if not self._forwardable(slot, packet):
            return
        raw_packet: dict = dict(packet)
        if isinstance(packet, dict) and packet.get("cmd") == "Connected":
            packet = self._connected_for(slot, packet)
        elif slot in self.owner.unlocked_slots:
            packet = self._revealed_for(slot, packet)
        delivered: bool = False
        # Broadcast to all sockets for this slot (Tracker + Game etc.)
        for ws in list(self._get_sockets_for_slot(slot)):
            try:
                await ws.send(encode([packet]))
                delivered = True
            except Exception:
                try:
                    self._unregister_socket(ws)
                except Exception:
                    pass
        # Legacy fallback: also try alias map if slot_to_sockets empty
        if not delivered:
            for alias, routed in list(self.routes.items()):
                if routed == slot and alias in self.game_sockets:
                    for ws in list(self.game_sockets.get(alias, [])):
                        try:
                            await ws.send(encode([packet]))
                            delivered = True
                        except Exception:
                            try:
                                self._unregister_socket(ws)
                            except Exception:
                                pass
        if not delivered:
            if packet.get("cmd") not in ("Connected", "RoomInfo"):
                buf = self.pending_packets.setdefault(slot, [])
                buf.append(raw_packet)
                if len(buf) > 1000:
                    self.pending_packets[slot] = buf[-1000:]

    async def deliver_pending(self, slot: str, alias: Optional[str] = None) -> None:
        """Deliver pending."""
        pending = self.pending_packets.get(slot)
        if not pending:
            return
        to_send: List[dict] = list(pending)
        self.pending_packets[slot] = []
        if not to_send:
            return
        # Determine targets: if alias specified, deliver only to sockets for that alias; else all for slot
        target_sockets: List[Any] = []
        if alias is not None:
            # Prefer per-alias sockets, fallback to slot
            lst = self._get_sockets_for_alias(alias)
            if lst and self.routes.get(alias) == slot:
                target_sockets = lst
            else:
                target_sockets = self._get_sockets_for_slot(slot)
                if not target_sockets:
                    # legacy
                    target_sockets = []
                    for a, r in list(self.routes.items()):
                        if r == slot and a in self.game_sockets:
                            target_sockets.extend(self.game_sockets.get(a, []))
        else:
            target_sockets = self._get_sockets_for_slot(slot)
            if not target_sockets:
                for a, r in list(self.routes.items()):
                    if r == slot and a in self.game_sockets:
                        target_sockets.extend(self.game_sockets.get(a, []))
            if not target_sockets:
                self.pending_packets.setdefault(slot, []).extend(to_send)
                return
        if not target_sockets:
            self.pending_packets.setdefault(slot, []).extend(to_send)
            return
        for raw in to_send:
            if not self._forwardable(slot, raw):
                continue
            out = raw
            if isinstance(raw, dict) and raw.get("cmd") == "Connected":
                out = self._connected_for(slot, raw)
            elif slot in self.owner.unlocked_slots:
                out = self._revealed_for(slot, raw)
            for ws in list(target_sockets):
                try:
                    await ws.send(encode([out]))
                except Exception:
                    try:
                        self._unregister_socket(ws)
                    except Exception:
                        pass

    def _slot_player_id(self, slot: str) -> Optional[int]:
        """Player id for slot."""
        try:
            for pid, info in self.owner.slot_info.items():
                if isinstance(pid, int) and getattr(info, "name", None) == slot:
                    return pid
        except Exception:
            pass
        return None

    def _patch_own_slot_entry(self, slot: str, packet: dict, reveal_name: bool) -> dict:
        """Patch slot entry."""
        info: Dict[str, str] = self.owner.identities.get(slot, {})
        real_name: str = info.get("name", slot)
        real_game: str = info.get("game", self.owner.real_slots.get(slot, ""))
        if not real_game and not (reveal_name and real_name != slot):
            return packet
        out: Dict[str, Any] = dict(packet)
        pid: Optional[int] = self._slot_player_id(slot)
        slot_info: Any = out.get("slot_info")
        if pid is None or not isinstance(slot_info, dict):
            return packet
        key: Any = pid if pid in slot_info else str(pid) if str(pid) in slot_info else None
        if key is None:
            return packet
        try:
            entry: Any = slot_info[key]
            if hasattr(entry, "_replace"):
                if reveal_name and real_name != slot:
                    entry = entry._replace(name=real_name)
                if real_game and getattr(entry, "game", None) != real_game:
                    entry = entry._replace(game=real_game)
            elif isinstance(entry, dict):
                entry = dict(entry)
                if reveal_name and real_name != slot:
                    entry["name"] = real_name
                if real_game:
                    entry["game"] = real_game
            elif isinstance(entry, (list, tuple)):
                entry = list(entry)
                if reveal_name and real_name != slot and len(entry) > 0:
                    entry[0] = real_name
                if real_game and len(entry) > 1:
                    entry[1] = real_game
            else:
                return packet
            slot_info = dict(slot_info)
            slot_info[key] = entry
            out["slot_info"] = slot_info
        except Exception:
            pass
        return out

    def _revealed_for(self, slot: str, packet: dict) -> dict:
        """Reveal names."""
        if slot not in self.owner.unlocked_slots:
            return packet
        return self._patch_own_slot_entry(slot, packet, reveal_name=True)

    def _connected_for(self, slot: str, packet: dict) -> dict:
        """Connected packet."""
        if packet.get("cmd") != "Connected":
            return self._revealed_for(slot, packet)
        return self._patch_own_slot_entry(
            slot, packet, reveal_name=slot in self.owner.unlocked_slots)

    def _forwardable(self, slot: str, packet: dict) -> bool:
        """Check forwardable."""
        if not isinstance(packet, dict) or packet.get("cmd") != "PrintJSON":
            return True
        mine: Optional[int] = self._slot_player_id(slot)
        if packet.get("type") == "Hint":
            return mine is not None and packet.get("receiving") == mine
        mystery: Any = self.owner.slot
        if mystery is None:
            return True
        parts: Any = packet.get("data", [])
        if not isinstance(parts, list):
            return True
        for part in parts:
            if not isinstance(part, dict) or part.get("type") != "player_id":
                continue
            try:
                if int(str(part.get("text", ""))) == mystery:
                    return False
            except (TypeError, ValueError):
                continue
        return True

    async def deliver_held(self, slot: str) -> None:
        """Deliver held items."""
        if self.owner.is_locked(slot):
            return
        entry: Dict[str, Any] = self.owner.cache_entry(slot)
        held: List[dict] = list(entry.get("held_items", []))
        if not held:
            return
        connected: bool = len(self._get_sockets_for_slot(slot)) > 0
        if not connected:
            # legacy fallback via routes
            for alias, routed in list(self.routes.items()):
                if routed == slot and alias in self.game_sockets and self.game_sockets.get(alias):
                    # value is list; non-empty means connected
                    try:
                        lst = self.game_sockets.get(alias)
                        if lst and len(lst) > 0:
                            connected = True
                            break
                    except Exception:
                        connected = True
                        break
        if not connected:
            return
        await self.send_to_slot_game(slot, {"cmd": "ReceivedItems", "index": 0, "items": [
            [item.get("item"), item.get("location"), item.get("player"), item.get("flags", 0)]
            for item in held]})
        entry["held_items"] = []
        key: Optional[str] = self.owner._cache_key_for(slot)
        if key is not None:
            await self.owner.send_msgs([set_operation(key, entry, default={})])

async def main(args: Any) -> None:
    """Main."""
    ctx = MysteryContext(args.connect, args.password)
    ctx.auth = args.name
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")

    if gui_enabled:
        ctx.run_gui()
    else:
        ctx.run_cli()

    await ctx.exit_event.wait()
    await ctx.shutdown()

def launch(*args: str) -> None:
    """Launch."""
    parser = get_base_parser(description="Mystery Game Archipelago Client")
    parser.add_argument("--name", default=None, help="Slot Name to connect as")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")

    parsed_args = handle_url_arg(parser.parse_args(args))

    asyncio.run(main(parsed_args))

if __name__ == "__main__":
    import sys
    launch(*sys.argv[1:])

if gui_enabled:
    from kvui import MDLabel, GameManager, MDButton, MDButtonText  # noqa: E402
    from kivy.uix.boxlayout import BoxLayout  # noqa: E402
    from kivy.uix.gridlayout import GridLayout  # noqa: E402
    from kivy.uix.scrollview import ScrollView  # noqa: E402

    class MysteryTab(BoxLayout):
        """Mystery status tab."""

        def __init__(self, ctx: MysteryContext, **kwargs: Any) -> None:
            super().__init__(orientation="vertical", **kwargs)
            self.ctx: MysteryContext = ctx
            self.ctx.mystery_tab = self
            self.status_label = MDLabel(text="Mystery - Waiting to connect...",
                                        halign="center", size_hint_y=None, height=60)
            self.add_widget(self.status_label)
            scroll = ScrollView(size_hint=(1, 1))
            self.grid = GridLayout(cols=1, spacing=4, size_hint_y=None, padding=8)
            self.grid.bind(minimum_height=self.grid.setter("height"))
            scroll.add_widget(self.grid)
            self.add_widget(scroll)
            self.update_status()

        def update_status(self) -> None:
            ctx: MysteryContext = self.ctx
            if not ctx.slot:
                self.status_label.text = "Mystery - Waiting to connect..."
                self.grid.clear_widgets()
                return
            self.status_label.text = (
                f"Mystery - {len(ctx.unlocked_slots)} unlocked | lock: {ctx.lock_mode_name()}")
            self.grid.clear_widgets()
            self.grid.add_widget(MDLabel(text="Slots:", halign="left", size_hint_y=None, height=28))
            for slot in sorted(ctx.real_slots):
                if slot in ctx.unlocked_slots:
                    text = f"  [open] {slot} = {ctx.real_slots[slot]}"
                elif ctx.guessable():
                    text = f"  [locked] {slot} = ?"
                else:
                    text = f"  [locked] {slot} = {ctx.shown_game(slot)}"
                if ctx.nuzlocke_enabled:
                    lives = ctx.get_nuzlocke_lives(slot)
                    hits = ctx.get_nuzlocke_hits(slot)
                    if slot in ctx.nuzlocke_dead:
                        text += f"  DEAD ({hits}/{lives})"
                    elif hits > 0:
                        text += f"  ({hits}/{lives} hits, {lives - hits} left)"
                    elif lives != 1:
                        text += f"  ({lives} lives)"
                self.grid.add_widget(MDLabel(text=text, halign="left", size_hint_y=None, height=24))
            if ctx.nuzlocke_enabled:
                self.grid.add_widget(MDLabel(text=f"Nuzlocke: {ctx.nuzlocke_lives} lives default", halign="left", size_hint_y=None, height=24))

    class ProxyTab(BoxLayout):
        """Proxy tab."""

        def __init__(self, ctx: MysteryContext, **kwargs: Any) -> None:
            super().__init__(orientation="vertical", **kwargs)
            self.ctx: MysteryContext = ctx
            self.ctx.proxy_tab = self
            self.status_label = MDLabel(text="Proxy - stopped", halign="center",
                                        size_hint_y=None, height=60)
            self.add_widget(self.status_label)
            scroll = ScrollView(size_hint=(1, 1))
            self.grid = GridLayout(cols=1, spacing=4, size_hint_y=None, padding=8)
            self.grid.bind(minimum_height=self.grid.setter("height"))
            scroll.add_widget(self.grid)
            self.add_widget(scroll)
            self.update_status()

        def update_status(self) -> None:
            ctx: MysteryContext = self.ctx
            proxy: Optional[MysteryProxy] = ctx.proxy
            gbridge: Optional[MysteryProxy] = ctx.global_bridge
            parts: List[str] = []
            if proxy and proxy.running:
                parts.append(f"Proxy ws://{proxy.host}:{proxy.port}")
            else:
                parts.append("Proxy stopped")
            if ctx.global_bridge_enabled:
                if gbridge and gbridge.running:
                    parts.append(f"Global ws://{gbridge.host}:{gbridge.port}")
                else:
                    parts.append(f"Global :{ctx.global_bridge_port} (starting)")
            self.status_label.text = " | ".join(parts)
            self.grid.clear_widgets()
            for slot in sorted(ctx.real_slots):
                shown_game: str = ctx.shown_game(slot)
                if slot in ctx.nuzlocke_dead:
                    state = "DEAD"
                elif slot in ctx.relays:
                    state = "relay up" + (" *" if ctx.active_relay == slot else "")
                elif ctx.is_locked(slot):
                    state = "FROZEN"
                else:
                    state = "open"
                port_info = ""
                try:
                    ports: List[str] = []
                    if proxy and slot in getattr(proxy, "slot_ports", {}):
                        ports.append(f":{proxy.slot_ports[slot]}")
                    if gbridge and slot in getattr(gbridge, "slot_ports", {}):
                        ports.append(f"G:{gbridge.slot_ports[slot]}")
                    if not ports:
                        if proxy and proxy.running:
                            ports.append(f"main:{proxy.port}")
                        if gbridge and gbridge.running:
                            ports.append(f"G:{gbridge.port}")
                    if ports:
                        port_info = " " + " ".join(ports)
                except Exception:
                    pass
                # Multi-client count
                try:
                    cnt = 0
                    if proxy is not None:
                        cnt += len(proxy._get_sockets_for_slot(slot))
                    if gbridge is not None and gbridge is not proxy:
                        cnt += len(gbridge._get_sockets_for_slot(slot))
                    if cnt > 0:
                        port_info += f" [{cnt} client(s)]"
                        # Show per-client handling breakdown for debugging
                        try:
                            handlings = []
                            for ws in proxy._get_sockets_for_slot(slot) if proxy else []:
                                h = proxy._socket_handling.get(proxy._sid(ws))
                                if h is not None:
                                    handlings.append(str(h))
                            if handlings:
                                port_info += f" h:{','.join(handlings)}"
                        except Exception:
                            pass
                except Exception:
                    pass
                if ctx.nuzlocke_enabled:
                    lives = ctx.get_nuzlocke_lives(slot)
                    hits = ctx.get_nuzlocke_hits(slot)
                    if slot in ctx.nuzlocke_dead:
                        port_info += f" DEAD {hits}/{lives}"
                    elif hits:
                        port_info += f" {hits}/{lives} ({lives-hits} left)"
                row = BoxLayout(orientation="horizontal", size_hint_y=None, height=36)
                row.add_widget(MDLabel(text=f"  {slot} [{shown_game}] [{state}]{port_info}",
                                       halign="left", size_hint_x=0.6))
                connect_button = MDButton(MDButtonText(text="Connect"), style="filled")
                connect_button.bind(on_release=lambda _btn, name=slot: self._connect_slot(name))
                row.add_widget(connect_button)
                disconnect_button = MDButton(MDButtonText(text="Stop"), style="filled")
                disconnect_button.bind(on_release=lambda _btn, name=slot: self._disconnect_slot(name))
                row.add_widget(disconnect_button)
                self.grid.add_widget(row)
            self.grid.add_widget(MDLabel(text=ctx.proxy_help(), halign="left",
                                         size_hint_y=None, height=220))

        def _connect_slot(self, slot: str) -> None:
            """Connect button."""
            try:
                self.ctx.start_relay(slot, via_command=True)
            except Exception as exc:
                logger.warning("Mystery: relay button failed for %s: %s", slot, exc)
            try:
                self.update_status()
            except Exception:
                pass

        def _disconnect_slot(self, slot: str) -> None:
            """Stop button."""
            try:
                self.ctx.stop_relay(slot)
            except Exception as exc:
                logger.warning("Mystery: relay stop button failed for %s: %s", slot, exc)
            try:
                self.update_status()
            except Exception:
                pass

    class MysteryManager(GameManager):
        """Stub manager."""

        base_title = "Mystery Client"

        def build(self) -> Any:  # type: ignore[override]
            container = super().build()
            self.add_client_tab("Mystery", MysteryTab(self.ctx))
            self.add_client_tab("Proxy", ProxyTab(self.ctx))
            # Optional Relay Tracker tab – only if Universal Tracker is installed
            try:
                from .tracker_bridge import is_tracker_available, create_relay_tracker_tab
                if is_tracker_available():
                    tab = create_relay_tracker_tab(self.ctx)
                    if tab is not None:
                        self.add_client_tab("Relay Tracker", tab)
            except Exception as exc:
                logger.debug("Mystery: Relay Tracker tab not added: %s", exc)
            return container

        def update_hints(self) -> None:
            """Update hints."""
            try:
                ctx: Any = self.ctx
                combined: list = []
                seen: set = set()
                def _hint_key(h: Any) -> Any:
                    try:
                        if isinstance(h, dict):
                            return (
                                h.get("receiving_player"),
                                h.get("finding_player"),
                                h.get("location"),
                                h.get("item"),
                                h.get("entrance", ""),
                            )
                        # Hint NamedTuple or object
                        return (
                            getattr(h, "receiving_player", None),
                            getattr(h, "finding_player", None),
                            getattr(h, "location", None),
                            getattr(h, "item", None),
                            getattr(h, "entrance", ""),
                        )
                    except Exception:
                        return str(h)
                def _add_unique(items: Any) -> None:
                    for h in items or []:
                        k = _hint_key(h)
                        if k not in seen:
                            seen.add(k)
                            combined.append(h)
                if getattr(ctx, "slot", None) is not None:
                    _add_unique(ctx.stored_data.get(f"_read_hints_{ctx.team}_{ctx.slot}", []))
                for name in sorted(getattr(ctx, "relays", {})):
                    relay: Any = ctx.relays[name]
                    if getattr(relay, "slot", None) is None:
                        continue
                    _add_unique(relay.stored_data.get(f"_read_hints_{relay.team}_{relay.slot}", []))
                self.hint_log.refresh_hints(combined)
            except Exception:
                super().update_hints()
else:
    class MysteryManager:
        """Stub manager."""

        def __init__(self, ctx: MysteryContext) -> None:
            self.ctx = ctx
            self.base_title = "Mystery Client"
