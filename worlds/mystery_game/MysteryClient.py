"""Mystery Game Archipelago Client.

Two connections: MysteryContext (the mystery slot: puzzles, unlocks,
guesses, locks, proxy) and per-slot RelayContexts (logged in as real game
slots, piped through the proxy).

Lock modes freeze traffic into server-side cached_checks until unlocked
(items, guesses, or both). Game clients play via the in-client proxy
(``!mystery_proxy`` prints how) and receive genuine server data.
"""

import asyncio
import functools
import logging
import time
from typing import Any, Dict, List, Optional

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
    MYSTERY_PROXY_HOST,
    MYSTERY_PROXY_PORT,
    cache_key,
    check_guess,
    merge_held_items,
    merge_pending_checks,
    merge_puzzle_state,
    new_cache_entry,
    normalize_cache_entry,
    normalize_puzzle_state,
    parse_puzzle_hint,
    parse_puzzle_piece,
    proxy_instructions,
    puzzle_ready,
    puzzle_state_key,
    set_operation,
    unlocks_key,
)
from .puzzles import puzzle_location_name

logger = logging.getLogger("Mystery")
client_logger = logging.getLogger("Client")

LOCK_OFF: int = 0
LOCK_FROZEN: int = 1
LOCK_GUESS: int = 2
LOCK_BOTH: int = 3

#: Rare server-side alias for the Mystery slot itself (see the Easter egg).
#: The client tries this game name if "Mystery Game" is refused.
CHEESE_GAME: str = "Mystery Cheese"


class MysteryCommandProcessor(ClientCommandProcessor):
    """Chat commands for the Mystery client (primary context)."""

    def __call__(self, raw: str) -> bool | None:
        # Client marker is "/"; server owns "!". Bridge !mystery_* to local
        # handling (these exist only here); every other !command still goes
        # to the server untouched.
        if raw.startswith("!mystery_"):
            return super().__call__("/" + raw[1:])
        return super().__call__(raw)

    def default(self, raw: str) -> None:
        """Plain chat: send via the active relay when one is connected."""
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
        """Show puzzles, unlocks, locks and guesses."""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        puzzles: List[str] = ctx.puzzle_names
        solved: int = sum(1 for name in puzzles if name in ctx.solved_puzzles)
        self.output(f"Mystery puzzles solved: {solved}/{len(puzzles)}")
        self.output(f"Lock mode: {ctx.lock_mode_name()}")
        if ctx.game == CHEESE_GAME:
            self.output("MYSTERY CHEESE MODE ACTIVE")
        locked: List[str] = ctx.locked_slots()
        self.output(f"Locked slots: {len(locked)} | Unlocked: {len(ctx.unlocked_slots)}")
        for slot in sorted(ctx.real_slots):
            state: str = f"unlocked ({ctx.unlocked_slots[slot]})" if slot in ctx.unlocked_slots else "LOCKED"
            self.output(f"  {slot} [{ctx.shown_game(slot)}] - {state}")
        return True

    def _cmd_mystery_solve(self, puzzle: str) -> bool:
        """Solve a puzzle (needs all pieces first): !mystery_solve <puzzle>"""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        match: Optional[str] = ctx.find_puzzle(puzzle)
        if match is None:
            self.output(f"No puzzle matching {puzzle!r}.")
            return False
        ready, reason = ctx.can_solve(match)
        if not ready:
            self.output(reason)
            return False
        async_start(ctx.check_puzzle(match))
        self.output(f"Checking {match}...")
        return True

    def _cmd_mystery_puzzle(self, puzzle: str) -> bool:
        """Show pieces/hints status: !mystery_puzzle <puzzle>"""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        match: Optional[str] = ctx.find_puzzle(puzzle)
        if match is None:
            self.output(f"No puzzle matching {puzzle!r}.")
            return False
        self.output(ctx.puzzle_detail(match))
        return True

    def _cmd_mystery_hint(self, puzzle: str) -> bool:
        """Re-read earned hints: !mystery_hint <puzzle>"""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        match: Optional[str] = ctx.find_puzzle(puzzle)
        if match is None:
            self.output(f"No puzzle matching {puzzle!r}.")
            return False
        for line in ctx.earned_hints(match):
            self.output(line)
        return True

    def _cmd_mystery_unlock(self, slot: str) -> bool:
        """Reveal/unlock by item location or slot: !mystery_unlock <slot>"""
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
        """List guessable/locked slots (games hidden in guess mode)."""
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
        return True

    def _cmd_mystery_guess(self, slot: str, game: str) -> bool:
        """Guess a slot's game: !mystery_guess <slot> <game>"""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        result: Optional[str] = ctx.submit_guess(slot, game)
        self.output(result if result else f"No slot matching {slot!r}.")
        return True

    def _cmd_mystery_relay(self, slot: str = "") -> bool:
        """Connect a relay for a slot (no args: list relays)."""
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
        result: Optional[str] = ctx.start_relay(slot)
        self.output(result if result else f"No slot matching {slot!r}.")
        return True

    def _cmd_mystery_unrelay(self, slot: str) -> bool:
        """Disconnect a relay: !mystery_unrelay <slot>"""
        ctx: Any = self.ctx
        if not isinstance(ctx, MysteryContext):
            self.output("Not connected as a Mystery Game slot.")
            return False
        result = ctx.stop_relay(slot)
        self.output(result if result else f"No slot matching {slot!r}.")
        return True

    def _cmd_mystery_proxy(self, action: str = "") -> bool:
        """Proxy help / control: !mystery_proxy [start|stop]"""
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
        """Print server-console alias lines revealing unlocked scrambled slots."""
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


class MysteryContext(CommonContext):
    """Primary context: the Mystery Game slot itself."""

    game: str = "Mystery Game"
    tags = CommonContext.tags | {"Mystery"}
    command_processor = MysteryCommandProcessor
    items_handling: int = 0b111

    def __init__(self, server_address: Optional[str], password: Optional[str]) -> None:
        super().__init__(server_address, password)
        self.puzzle_names: List[str] = []
        self.unlock_map: Dict[str, str] = {}
        self.solved_puzzles: set = set()
        self.revealed_unlocks: Dict[str, str] = {}
        self.lock_mode: int = LOCK_OFF
        self.real_slots: Dict[str, str] = {}
        self.identities: Dict[str, Dict[str, str]] = {}
        self.unlocked_slots: Dict[str, str] = {}
        #: Full scramble flag (slot names hashed server-side).
        self.scrambled: bool = False
        #: {puzzle: required piece count} for this seed.
        self.puzzle_pieces: Dict[str, int] = {}
        #: {puzzle: [hint texts]} for this seed.
        self.puzzle_hints: Dict[str, List[str]] = {}
        #: {puzzle: {pieces: [i], hints: [i], solved: bool}}, server-synced.
        self.puzzle_state: Dict[str, Dict[str, Any]] = {}
        self.caches: Dict[str, Dict[str, Any]] = {}
        self.relays: Dict[str, "RelayContext"] = {}
        #: Slot chat is spoken through (most recently started relay).
        self.active_relay: Optional[str] = None
        self.proxy: Optional["MysteryProxy"] = None
        self.mystery_tab: Any = None
        self.proxy_tab: Any = None
        #: Mystery Cheese fallback: tried the alternate game name yet?
        self._cheese_tried: bool = False
        #: Local name->id maps (fallback when the server lacks our tables).
        self._local_item_ids: Dict[str, int] = {}
        self._local_location_ids: Dict[str, int] = {}
        self._local_item_names: Dict[int, str] = {}
        #: Last genuine RoomInfo (replayed scrubbed as the proxy hello).
        self._last_roominfo: Dict[str, Any] = {}

    # -- connection ---------------------------------------------------------
    async def server_auth(self, password_requested: bool = False) -> None:
        """Authenticate: username first, then send Connect (base never sends it)."""
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect(name=self.auth, password=self.password)

    def event_invalid_game(self) -> None:
        """Retry once as Mystery Cheese (rare server-side Easter egg)."""
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
        """Local name maps plus an explicit server datapackage request.

        Tables come from the server (soft-coded: game names from slot_data,
        so this works in every mode including Mystery Cheese), never from
        the apworld. Local maps are fallback only.
        """
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
        """Resolve a received item id to its name (server tables, else local)."""
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
            # Keep the genuine article: the proxy hello replays this with
            # names scrubbed, so games can't distinguish it from the server.
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
            self._check_puzzle_items(args)
            self._refresh_ui()
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
        self.scrambled = bool(slot_data.get("mystery_scrambled", False))
        self.identities = {str(slot): dict(info) for slot, info in
                           dict(slot_data.get("mystery_identities", {})).items()}
        self._ensure_local_datapackage()
        self.puzzle_pieces = {str(puzzle): int(count) for puzzle, count in
                              dict(slot_data.get("mystery_puzzle_pieces", {})).items()}
        self.puzzle_hints = {str(puzzle): [str(text) for text in hints] for puzzle, hints in
                             dict(slot_data.get("mystery_puzzle_hints", {})).items()}
        client_logger.info(
            "Mystery connected: %d puzzle(s), %d unlock(s), lock=%s, %d tracked slot(s)",
            len(self.puzzle_names), len(self.unlock_map),
            self.lock_mode_name(), len(self.real_slots),
        )
        # Seed-open slots start unlocked (persisted like any other unlock).
        for slot in slot_data.get("mystery_preunlocked", []):
            if isinstance(slot, str) and slot in self.real_slots and slot not in self.unlocked_slots:
                async_start(self._unlock_slot(slot, "seed"))
        if self.slot is not None:
            keys: List[str] = [unlocks_key(self.team), puzzle_state_key(self.team, self.slot)]
            async_start(self.send_msgs([
                {"cmd": "Get", "keys": keys},
                {"cmd": "SetNotify", "keys": keys},
            ]))
        # The proxy starts itself once properly connected (stop it by hand
        # with !mystery_proxy stop if you only want the mystery slot).
        if self.proxy is None or not self.proxy.running:
            async_start(self.start_proxy())
        self._refresh_ui()

    def _sync_server_state(self) -> None:
        if self.slot is None:
            return
        stored: Any = self.stored_data.get(unlocks_key(self.team), {})
        if isinstance(stored, dict):
            for slot, how in stored.items():
                if slot in self.real_slots and slot not in self.unlocked_slots:
                    self.unlocked_slots[slot] = how if isinstance(how, str) else "item"
                    async_start(self.flush_slot(slot))
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

    # -- puzzles --------------------------------------------------------------
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
        """Whether ``puzzle`` may be solved now (all pieces held)."""
        need: int = int(self.puzzle_pieces.get(puzzle, 0))
        if puzzle_ready(self.puzzle_state, puzzle, need):
            return True, ""
        have: int = len(self.puzzle_state.get(puzzle, {}).get("pieces", []))
        return False, f"{puzzle} needs {need} pieces ({have}/{need}). Find them first!"

    def puzzle_detail(self, puzzle: str) -> str:
        """One-line puzzle status for commands."""
        need: int = int(self.puzzle_pieces.get(puzzle, 0))
        have: int = len(self.puzzle_state.get(puzzle, {}).get("pieces", []))
        hints: int = len(self.puzzle_state.get(puzzle, {}).get("hints", []))
        total_hints: int = len(self.puzzle_hints.get(puzzle, []))
        solved: str = "SOLVED" if puzzle in self.solved_puzzles else "open"
        return (f"{puzzle}: pieces {have}/{need}, hints {hints}/{total_hints}, {solved}")

    def earned_hints(self, puzzle: str) -> List[str]:
        """Hint texts already earned for ``puzzle`` (indexed from 1)."""
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

    # -- locks ------------------------------------------------------------------
    def lock_mode_name(self) -> str:
        return {LOCK_OFF: "off", LOCK_FROZEN: "frozen",
                LOCK_GUESS: "guess_the_game", LOCK_BOTH: "both"}.get(self.lock_mode, "off")

    def guessable(self) -> bool:
        """Guessing unlocks in guess and both modes."""
        return self.lock_mode in (LOCK_GUESS, LOCK_BOTH)

    def item_unlockable(self) -> bool:
        """Item unlocks work in frozen and both modes."""
        return self.lock_mode in (LOCK_FROZEN, LOCK_BOTH)

    def locked_slots(self) -> List[str]:
        if self.lock_mode == LOCK_OFF:
            return []
        return [slot for slot in self.real_slots if slot not in self.unlocked_slots]

    def shown_game(self, slot: str) -> str:
        """Game display rule, applied everywhere: real names only when unlocked.

        The only exception is a fully open seed (no lock, no scramble),
        where nothing is hidden by design. In particular this stays hidden
        in guess modes until solved — showing it would give away answers.
        """
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

    def _unlock_order_names(self) -> List[str]:
        """Slots with unlock items, in player-id order (matches generation)."""
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
        """Map 'Unlock Slot N' onto the Nth slot by player id (1-based)."""
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
        """Record received piece/hint items into server-synced puzzle state."""
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

    def submit_guess(self, slot_query: str, game_guess: str) -> Optional[str]:
        slot: Optional[str] = self.find_slot(slot_query)
        if slot is None:
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

    # -- cached_checks ------------------------------------------------------------
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
        """Release a slot: send pending checks, deliver held items."""
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
        if self.proxy is not None:
            await self.proxy.deliver_held(slot)
        key: Optional[str] = self._cache_key_for(slot)
        if key is not None and (pending or entry.get("held_items")):
            await self.send_msgs([set_operation(key, entry, default={})])
        self._refresh_ui()

    # -- relays + proxy -------------------------------------------------------------
    def server_identity(self, slot: str) -> Dict[str, str]:
        """Handshake identity for a slot: server (possibly hashed) game/name.

        The server only knows the renamed identities, so relays MUST log in
        with these — the real game would be refused with InvalidGame.
        """
        info: Dict[str, str] = self.identities.get(slot, {})
        return {
            "game": info.get("server_game", self.real_slots.get(slot, "Unknown")),
            "slot": slot,
        }

    def start_relay(self, slot_query: str, make_active: bool = True) -> Optional[str]:
        slot: Optional[str] = self.find_slot(slot_query)
        if slot is None:
            return None
        if slot in self.relays:
            if make_active:
                self.active_relay = slot
                self._refresh_ui()
            return f"Relay for {slot} already running."
        game: str = self.real_slots.get(slot, "Unknown")
        identity: Dict[str, str] = self.server_identity(slot)
        relay = RelayContext(self.server_address, self.password, game, slot, self,
                             server_game=identity["game"])
        relay.auth = identity["slot"]
        relay.username = identity["slot"]
        relay.frozen = self.is_locked(slot)
        self.relays[slot] = relay
        if make_active:
            self.active_relay = slot
        relay.server_task = asyncio.create_task(server_loop(relay), name=f"relay {slot}")
        key: Optional[str] = self._cache_key_for(slot)
        if key is not None:
            async_start(relay.send_msgs([
                {"cmd": "Get", "keys": [key]},
                {"cmd": "SetNotify", "keys": [key]},
            ]))
        self._refresh_ui()
        shown: str = self.shown_game(slot)
        return f"Relay connecting as {slot} ({shown})" + (" [FROZEN]" if relay.frozen else "")

    def stop_relay(self, slot_query: str) -> Optional[str]:
        """Disconnect one relay (it stays out until started again)."""
        slot: Optional[str] = self.find_slot(slot_query)
        if slot is None:
            return None
        relay: Optional["RelayContext"] = self.relays.pop(slot, None)
        if relay is None:
            return f"No relay running for {slot}."
        if self.active_relay == slot:
            self.active_relay = None
        async_start(self._drop_relay(relay))
        self._refresh_ui()
        return f"Relay for {slot} disconnecting..."

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
        """Relay to speak through: active if online, else any single online relay."""
        active: Optional[str] = self.active_relay
        if active is not None:
            relay: Optional["RelayContext"] = self.relays.get(active)
            if relay is not None and self._relay_online(relay):
                return relay
        online: List["RelayContext"] = [
            relay for relay in self.relays.values() if self._relay_online(relay)]
        if len(online) == 1:
            return online[0]
        return None

    async def start_proxy(self) -> None:
        if self.proxy is not None and self.proxy.running:
            client_logger.info("Mystery: proxy already running")
            return
        self.proxy = MysteryProxy(self, MYSTERY_PROXY_HOST, MYSTERY_PROXY_PORT)
        await self.proxy.start()
        client_logger.info("Mystery: %s", self.proxy_help())
        self._refresh_ui()

    async def stop_proxy(self) -> None:
        if self.proxy is None:
            return
        await self.proxy.stop()
        self.proxy = None
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
        return text

    def _refresh_ui(self) -> None:
        try:
            if self.mystery_tab is not None:
                self.mystery_tab.update_status()
            if self.proxy_tab is not None:
                self.proxy_tab.update_status()
        except Exception:
            pass

    async def disconnect(self, allow_autoreconnect: bool = False) -> None:
        """Disconnect relays + proxy first: nothing outlives the mystery slot."""
        for relay in list(self.relays.values()):
            try:
                await relay.disconnect(allow_autoreconnect)
            except Exception:
                pass
        self.relays.clear()
        self.active_relay = None
        if self.proxy is not None:
            try:
                await self.stop_proxy()
            except Exception:
                pass
        await super().disconnect(allow_autoreconnect)

    def make_gui(self) -> Any:
        """Return the manager class (resolved at call time, like NoLogicClient)."""
        return MysteryManager


def _game_known_locally(game: str) -> bool:
    """Whether the local datapackage has checksum tables for ``game``."""
    try:
        from worlds import network_data_package
        return "checksum" in network_data_package.get("games", {}).get(game, {})
    except Exception:
        return False


class RelayContext(CommonContext):
    """Secondary context: logged in as a real game slot, piped via the proxy.

    When the slot is locked (frozen), outbound checks and inbound items are
    held into server-side ``cached_checks`` instead of flowing; on unlock
    everything replays. Nothing here edits the server or the game.
    """
    game: str = "Mystery Relay"
    tags = CommonContext.tags | {"MysteryRelay"}
    #: Full flags: relays must send checks and receive items to hold/forward.
    items_handling: int = 0b111

    def __init__(self, server_address: Optional[str], password: Optional[str],
                 game: str, slot_name: str, owner: MysteryContext,
                 server_game: Optional[str] = None) -> None:
        self.real_game: str = game
        self.relay_slot: str = slot_name
        self.owner: MysteryContext = owner
        self.frozen: bool = True
        self.aliased: bool = False
        #: Last connection refusal, if any (wakes waiting games immediately).
        self.connect_error: Optional[str] = None
        # __init__ reads checksums for self.game: use the real game when the
        # local tables know it, else neutral. The handshake game (what the
        # server knows — scrambled in lock modes) is set right after.
        self.game = game if _game_known_locally(game) else "Archipelago"
        super().__init__(server_address, password)
        if server_game:
            self.game = server_game

    async def server_auth(self, password_requested: bool = False) -> None:
        """Authenticate as the relayed slot (base never sends Connect)."""
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        # Speak with the game's tags too: tag-gated server features (e.g.
        # DeathLink) key off these, and the relay is the game as far as the
        # server is concerned. Only the relay marker is added.
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
        """No-op: relays keep no group tables (hashed games have none)."""

    def consume_network_location_groups(self) -> None:
        """No-op: relays keep no group tables (hashed games have none)."""

    async def _maybe_alias(self) -> None:
        """Alias this slot to its real slot name once unlocked and scrambled.

        Uses the client !alias command (sets our own display name); no-op
        when the server name already equals the real one. Server persists it.
        """
        if self.aliased:
            return
        real: str = self.owner.identities.get(self.relay_slot, {}).get("name", self.relay_slot)
        if real == self.relay_slot:
            return
        if self.relay_slot not in self.owner.unlocked_slots:
            return
        self.aliased = True
        await self.send_msgs([{"cmd": "Say", "text": f"!alias {real[:16]}"}])

    def on_package(self, cmd: str, args: dict) -> None:
        super().on_package(cmd, args)
        if cmd in ("Connected", "RoomInfo"):
            if self.owner.proxy is not None:
                async_start(self.owner.proxy.note_preamble(self.relay_slot, cmd, dict(args)))
            if cmd == "Connected":
                # Relay just came online: flush anything held for this slot.
                async_start(self.owner.flush_slot(self.relay_slot))
                async_start(self._maybe_alias())
            return
        if cmd == "ReceivedItems":
            items: List[dict] = [
                {"item": item.item, "location": item.location,
                 "player": item.player, "flags": int(item.flags),
                 "index": idx}
                for idx, item in enumerate(args.get("items", []), start=args.get("index", 0))
            ]
            if self.frozen:
                async_start(self.owner.stash_items(self.relay_slot, items))
                return
            if self.owner.proxy is not None:
                async_start(self.owner.proxy.send_to_slot_game(
                    self.relay_slot, {"cmd": cmd, **args}))
            return
        if self.owner.proxy is not None and cmd in (
                "PrintJSON", "Retrieved", "SetReply", "LocationInfo",
                "RoomUpdate", "DataPackage"):
            async_start(self.owner.proxy.send_to_slot_game(
                self.relay_slot, {"cmd": cmd, **args}))


class MysteryProxy:
    """Local websocket proxy: game clients connect here, not to the server.

    Routes aliases to real slots and enforces freezes: held traffic lands
    in server-side ``cached_checks`` via the primary context. Everything
    forwarded is genuine server data (games need exact information to
    function); hiding applies only to player-visible surfaces (Mystery UI,
    commands, server lobby names), never to game traffic.
    Start with ``!mystery_proxy start``; clients connect to
    ``ws://localhost:11318`` using the alias as slot name, or to their
    per-slot port (``!mystery_proxy`` prints the exact steps).
    """

    def __init__(self, owner: MysteryContext, host: str, port: int) -> None:
        self.owner: MysteryContext = owner
        self.host: str = host
        self.port: int = port
        self.routes: Dict[str, str] = {}
        self.game_sockets: Dict[str, Any] = {}
        self.preamble: Dict[str, List[dict]] = {}
        #: Per-slot relay readiness (set on preamble change/refusal).
        self._relay_events: Dict[str, asyncio.Event] = {}
        #: Slots whose relay was refused, with the reason.
        self._relay_failed: Dict[str, str] = {}
        #: Real datapackage checksums seen on relay RoomInfos, by game.
        self._known_checksums: Dict[str, str] = {}
        #: Game tags per slot, intercepted from game Connects for relay auth.
        self.game_tags: Dict[str, set] = {}
        #: Aliases already sent a Connected packet (preamble burst).
        self._sent_connected: set = set()
        #: Per-slot listeners: slot -> server / port (port implies the slot).
        self.slot_servers: Dict[str, Any] = {}
        self.slot_ports: Dict[str, int] = {}
        self.server: Any = None
        self.running: bool = False
        #: Real datapackage checksums seen on relay RoomInfos, by game.
        self._known_checksums: Dict[str, str] = {}
        #: Game tags per slot, intercepted from game Connects for relay auth.
        self.game_tags: Dict[str, set] = {}
        #: Aliases already sent a Connected packet (preamble burst).
        self._sent_connected: set = set()
        #: Per-slot listeners: slot -> server / port (port implies the slot).
        self.slot_servers: Dict[str, Any] = {}
        self.slot_ports: Dict[str, int] = {}
        self.server: Any = None
        self.running: bool = False

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
            # Speak first like a real server: games wait for RoomInfo before
            # sending Connect. Without this they sit silent until timeout.
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
            # Legacy serve() only binds once awaited (like AHIT's proxy).
            self.server = await websockets.serve(
                functools.partial(handler, owner=owner),
                # Ping games regularly, but never drop slow ones for missing
                # pongs (single-threaded game loops can answer late).
                host=self.host, port=self.port, ping_interval=20, ping_timeout=999999)
        except OSError as exc:
            client_logger.warning("Mystery: proxy cannot listen on ws://%s:%d (%s). "
                                  "Is another proxy running?", self.host, self.port, exc)
            self.server = None
            return
        self.running = True
        logger.info("MysteryProxy listening on ws://%s:%d", self.host, self.port)
        # Per-slot listeners: the port implies the slot, so games behind them
        # get genuine relay RoomInfo immediately (no guessing, no gaps).
        for index, slot in enumerate(sorted(self.owner.real_slots)):
            slot_port: int = self.port + 1 + index

            def _slot_handler(websocket: Any, path: str = "/",
                              _slot: str = slot) -> Any:
                return self._serve_slot_socket(websocket, _slot)

            try:
                slot_server = await websockets.serve(
                    _slot_handler, host=self.host, port=slot_port,
                    ping_interval=20, ping_timeout=999999)
            except OSError as exc:
                client_logger.warning("Mystery: no slot listener for %s on :%d (%s).",
                                      slot, slot_port, exc)
                continue
            self.slot_servers[slot] = slot_server
            self.slot_ports[slot] = slot_port
            logger.info("MysteryProxy: slot listener for %s on ws://%s:%d", slot, self.host, slot_port)
        # Eager relays: bring every tracked slot online now, so checksums,
        # preambles, and seal data predate the first game connection.
        # Without these the first game gets a hello with no checksums and
        # declares itself incompatible before any relay exists to fix it.
        for slot in sorted(self.owner.real_slots):
            try:
                if slot not in self.owner.relays:
                    self.owner.start_relay(slot, make_active=False)
            except Exception as exc:
                logger.warning("MysteryProxy: eager relay failed for %s: %s", slot, exc)

    async def _serve_slot_socket(self, websocket: Any, slot: str) -> None:
        """Serve one game socket on its dedicated slot port."""
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
            self.owner.start_relay(slot)
        if not await self._wait_relay(slot, lambda: self._has_roominfo(slot), timeout=30):
            await self._send_connect_error(
                websocket, f"MysteryProxy: could not reach {slot} "
                           f"({self._relay_failed.get(slot, 'relay unreachable')}).")
            try:
                await websocket.close()
            except Exception:
                pass
            return
        await websocket.send(encode([self._roominfo_for(slot)]))
        await self._socket_loop(websocket, slot)

    def _roominfo_for(self, slot: str) -> dict:
        """Latest relay RoomInfo for a slot ({} when none yet)."""
        for packet in self.preamble.get(slot, []):
            if packet.get("cmd") == "RoomInfo":
                return packet
        return {"cmd": "RoomInfo"}

    async def _wait_relay(self, slot: str, ready: Any, timeout: float = 30.0) -> bool:
        """Wait until ``ready()`` holds (single-threaded, race-free)."""
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
        """Shared read loop; fixed_slot pins slot-port sockets to their slot."""
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
                    continue
                for msg in messages:
                    try:
                        if not isinstance(msg, dict) or not isinstance(msg.get("cmd"), str):
                            continue
                        got_message = True
                        if msg.get("cmd") == "Connect":
                            alias = await self._handle_connect(websocket, msg, fixed_slot)
                            if alias is None:
                                return
                        else:
                            if alias is None:
                                continue
                            await self._handle_game_message(alias, msg)
                    except Exception as exc:
                        logger.warning("MysteryProxy: dropping bad message: %s", exc)
                        continue
        except Exception as exc:
            logger.debug("MysteryProxy socket closed: %s", exc)
        finally:
            if not got_message:
                logger.info("MysteryProxy: %s closed without sending anything "
                            "(probe, retry abort, or wrong address?)", peer)
            if alias is not None:
                self.game_sockets.pop(alias, None)
                self._sent_connected.discard(alias)

    async def stop(self) -> None:
        self.running = False
        for socket in list(self.game_sockets.values()):
            try:
                await socket.close()
            except Exception:
                pass
        self.game_sockets.clear()
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
        """Resolve a proxy alias to its real slot (identity when known)."""
        if alias in self.routes:
            return self.routes[alias]
        if alias in self.owner.real_slots:
            return alias
        return None

    def notify_relay_ready(self, slot: str) -> None:
        """Mark a relay connected (wakes games waiting on genuine packets)."""
        self._relay_failed.pop(slot, None)
        self._relay_events.setdefault(slot, asyncio.Event()).set()

    def notify_relay_failed(self, slot: str, error: str) -> None:
        """Mark a relay refused so waiting games fail fast with a reason."""
        self._relay_failed[slot] = error
        self._relay_events.setdefault(slot, asyncio.Event()).set()

    def _has_roominfo(self, slot: str) -> bool:
        return any(packet.get("cmd") == "RoomInfo" for packet in self.preamble.get(slot, []))

    def _relay_preamble_ready(self, slot: str) -> bool:
        relay: Optional[RelayContext] = self.owner.relays.get(slot)
        return (bool(self.preamble.get(slot)) and relay is not None
                and bool(relay.server) and relay.slot is not None)

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
        if slot is None:
            await websocket.send(encode([{"cmd": "PrintJSON", "data": [
                {"text": f"MysteryProxy: unknown alias {alias!r}. Ask for !mystery_proxy help."}]}]))
            await websocket.close()
            return None
        # Guess-only mode never lets locked games play early: custom refusal.
        # (Frozen/both must accept so traffic exists to hold; the server
        # itself cannot send custom connection errors.)
        if self.owner.lock_mode == LOCK_GUESS and self.owner.is_locked(slot):
            await websocket.send(encode([{"cmd": "PrintJSON", "data": [
                {"text": "This game isn't unlocked yet."}]}]))
            await websocket.close()
            return None
        self.routes[alias] = slot
        self.game_sockets[alias] = websocket
        logger.info("MysteryProxy: %s connected as %s", alias, slot)
        # Intercept the game's tags for relay auth: tag-gated server
        # features follow the tags on the slot connection, so the relay
        # speaks with the game's tags plus the relay marker.
        try:
            incoming: Any = msg.get("tags", [])
            if isinstance(incoming, list):
                self.game_tags[slot] = {str(tag) for tag in incoming}
        except Exception:
            pass
        # Ensure a relay exists: without one there is no server side, so the
        # game would wait forever (its timeout then looks like our fault).
        relay: Optional[RelayContext] = self.owner.relays.get(slot)
        if relay is not None and slot in self._relay_failed:
            self.owner.relays.pop(slot, None)
            relay = None
        if relay is None:
            self.owner.start_relay(slot)
            relay = self.owner.relays.get(slot)
        else:
            # Relay already up (possibly with default tags): re-auth it with
            # the intercepted tags so features follow immediately.
            try:
                stored: set = self.game_tags.get(slot, set())
                if stored:
                    relay.tags = set(stored) | {"MysteryRelay"}
                    await relay.send_connect(name=relay.auth, password=relay.password)
            except Exception as exc:
                logger.debug("MysteryProxy: relay re-auth skipped for %s: %s", slot, exc)
        if self._relay_preamble_ready(slot):
            await self._send_preamble(alias, slot)
        else:
            # Wait for genuine RoomInfo/Connected from the real server via
            # the relay. Game-side pings are answered by the protocol stack
            # meanwhile; queued input waits in TCP buffers.
            if not await self._wait_relay(
                    slot, lambda: self._relay_preamble_ready(slot), timeout=30):
                reason: str = self._relay_failed.get(slot, "relay unreachable")
                await self._send_connect_error(
                    websocket, f"MysteryProxy: could not reach {slot} ({reason}).")
                self.routes.pop(alias, None)
                self.game_sockets.pop(alias, None)
                try:
                    await websocket.close()
                except Exception:
                    pass
                return None
            await self._send_preamble(alias, slot)
        await self.deliver_held(slot)
        return alias

    async def _send_preamble(self, alias: str, slot: str) -> None:
        """Send the stored Connected packet to a game socket.

        RoomInfo is skipped: every socket already got the proxy hello on
        open, and a second one would re-trigger datapackage/auth flows.
        Unlocked slots get their real slot/game names stitched in.
        """
        socket: Any = self.game_sockets.get(alias)
        if socket is None:
            return
        for packet in self.preamble.get(slot, []):
            if packet.get("cmd") == "RoomInfo":
                continue
            out: dict = self._revealed_for(slot, packet) if slot in self.owner.unlocked_slots else packet
            try:
                await socket.send(encode([out]))
            except Exception:
                self.game_sockets.pop(alias, None)
                return
        self._sent_connected.add(alias)

    async def _send_connect_error(self, websocket: Any, text: str) -> None:
        try:
            await websocket.send(encode([{"cmd": "PrintJSON", "data": [{"text": text}]}]))
        except Exception:
            pass

    def _hello_room_info(self) -> dict:
        """RoomInfo sent to every game socket first, like a real server.

        Real servers speak first; compliant games wait for this before
        sending Connect. This replays the genuine server RoomInfo with
        the real games list plus known datapackage checksums.
        """
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
            if not guessy:
                games: list[str] = ["Archipelago", "Mystery Game"]
                try:
                    games.extend(sorted(set(ctx.real_slots.values())))
                except Exception:
                    pass
                packet["games"] = games
                try:
                    known: Dict[str, str] = dict(getattr(self, "_known_checksums", {}))
                except Exception:
                    known = {}
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

    async def _handle_game_message(self, alias: str, msg: dict) -> None:
        slot: Optional[str] = self.slot_for_alias(alias)
        if slot is None:
            return
        if msg.get("cmd") == "Connect":
            # Consumed, never forwarded: the game authenticates to the proxy
            # here; the relay holds its own separate server auth. Forwarding
            # would re-auth the relay with the game's real game name and get
            # it refused (plus poison the failure tracking).
            logger.debug("MysteryProxy: consumed game Connect for %s", alias)
            return
        relay: Optional[RelayContext] = self.owner.relays.get(slot)
        if relay is None:
            # Auto-relay so anything thrown at the proxy has a server side.
            self.owner.start_relay(slot)
            relay = self.owner.relays.get(slot)
        if msg.get("cmd") == "LocationChecks":
            checks: List[int] = [loc for loc in msg.get("locations", []) if isinstance(loc, int)]
            if self.owner.is_locked(slot):
                await self.owner.stash_checks(slot, checks)
                return
            if relay is not None and relay.server:
                await relay.send_msgs([msg])
            else:
                # Relay not up yet: hold server-side; flushed on connect.
                await self.owner.stash_checks(slot, checks)
            return
        if relay is not None and relay.server:
            if msg.get("cmd") == "Connect":
                # Consumed, never forwarded: the game authenticates to the
                # proxy here; the relay holds its own separate server auth.
                # Forwarding would re-auth it under the game's real game name
                # and get it refused (plus poison failure tracking).
                logger.debug("MysteryProxy: consumed game Connect for %s", alias)
                return
            if msg.get("cmd") == "ConnectUpdate":
                # Merge the relay marker back in: tag updates from the game
                # would otherwise drop it (seen as DeathLink losing MysteryRelay).
                try:
                    tags: Any = msg.get("tags", [])
                    if isinstance(tags, list):
                        cleaned: set = {str(tag) for tag in tags}
                        cleaned.discard("MysteryRelay")
                        self.game_tags[slot] = cleaned
                        msg = dict(msg, tags=sorted(cleaned | {"MysteryRelay"}))
                except Exception:
                    pass
            await relay.send_msgs([msg])

    async def note_preamble(self, slot: str, cmd: str, packet: dict) -> None:
        """Remember Connected/RoomInfo so late game clients still get them."""
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
        """Forward one server packet to the game behind ``slot`` (if connected)."""
        if not self._forwardable(slot, packet):
            return
        # Unlocked games see their real slot/game names (server holds hashed).
        if slot in self.owner.unlocked_slots:
            packet = self._revealed_for(slot, packet)
        for alias, routed in list(self.routes.items()):
            if routed == slot and alias in self.game_sockets:
                try:
                    await self.game_sockets[alias].send(encode([packet]))
                except Exception:
                    self.game_sockets.pop(alias, None)

    def _slot_player_id(self, slot: str) -> Optional[int]:
        """Player id for a slot name from live slot_info (None when unknown)."""
        try:
            for pid, info in self.owner.slot_info.items():
                if isinstance(pid, int) and getattr(info, "name", None) == slot:
                    return pid
        except Exception:
            pass
        return None

    def _revealed_for(self, slot: str, packet: dict) -> dict:
        """If slot is unlocked, rewrite its hashed slot/game names to real ones."""
        if slot not in self.owner.unlocked_slots:
            return packet
        info: Dict[str, str] = self.owner.identities.get(slot, {})
        real_name: str = info.get("name", slot)
        real_game: str = info.get("game", self.owner.real_slots.get(slot, ""))
        if not real_name and not real_game:
            return packet
        out: Dict[str, Any] = dict(packet)
        # Patch slot_info entry for this slot's player id
        pid: Optional[int] = self._slot_player_id(slot)
        slot_info: Any = out.get("slot_info")
        if pid is not None and isinstance(slot_info, dict) and pid in slot_info:
            try:
                entry: Any = dict(slot_info[pid])
                # NetworkSlot is a namedtuple; rebuild if needed
                if hasattr(entry, "_replace"):
                    if real_name != slot:
                        entry = entry._replace(name=real_name)
                    if real_game and getattr(entry, "game", None) != real_game:
                        entry = entry._replace(game=real_game)
                else:
                    if isinstance(entry, dict):
                        if real_name != slot:
                            entry["name"] = real_name
                        if real_game:
                            entry["game"] = real_game
                slot_info = dict(slot_info)
                slot_info[pid] = entry
                out["slot_info"] = slot_info
            except Exception:
                pass
        return out

    def _forwardable(self, slot: str, packet: dict) -> bool:
        """Whether a packet may reach the game behind ``slot``.

        Drops anything involving the Mystery slot (its chat and item-get
        noise would duplicate on the game side), except hints addressed to
        this slot. Everything else passes through untouched.
        """
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
        """Replay held items to the game socket once it may receive them."""
        if self.owner.is_locked(slot):
            return
        entry: Dict[str, Any] = self.owner.cache_entry(slot)
        held: List[dict] = list(entry.get("held_items", []))
        if not held:
            return
        connected: bool = any(
            routed == slot and sock is not None
            for routed, sock in self.game_sockets.items())
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
    """Main async entry point."""
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
    """Launch the Mystery client."""
    parser = get_base_parser(description="Mystery Game Archipelago Client")
    parser.add_argument("--name", default=None, help="Slot Name to connect as")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")

    parsed_args = handle_url_arg(parser.parse_args(args))

    asyncio.run(main(parsed_args))


if __name__ == "__main__":
    import sys
    launch(*sys.argv[1:])


# -- UI --------------------------------------------------------------------------
# Mirrors NoLogicClient: tab widgets stored on ctx, refreshed from on_package
# paths, created by a GameManager subclass returned from make_gui().


if gui_enabled:
    from kvui import MDLabel, GameManager, MDButton, MDButtonText  # noqa: E402
    from kivy.uix.boxlayout import BoxLayout  # noqa: E402
    from kivy.uix.gridlayout import GridLayout  # noqa: E402
    from kivy.uix.scrollview import ScrollView  # noqa: E402

    class MysteryTab(BoxLayout):
        """Status: puzzles (+pieces/hints), locks, unlocks, guesses."""

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
            solved: int = sum(1 for name in ctx.puzzle_names if name in ctx.solved_puzzles)
            self.status_label.text = (
                f"Mystery - {solved}/{len(ctx.puzzle_names)} puzzles | "
                f"{len(ctx.unlocked_slots)} unlocked | lock: {ctx.lock_mode_name()}")
            self.grid.clear_widgets()
            self.grid.add_widget(MDLabel(text="Puzzles (use !mystery_solve):", halign="left",
                                         size_hint_y=None, height=28))
            for name in ctx.puzzle_names:
                mark: str = "[X]" if name in ctx.solved_puzzles else "[ ]"
                need: int = int(ctx.puzzle_pieces.get(name, 0))
                have: int = len(ctx.puzzle_state.get(name, {}).get("pieces", []))
                hints: int = len(ctx.puzzle_state.get(name, {}).get("hints", []))
                total_hints: int = len(ctx.puzzle_hints.get(name, []))
                self.grid.add_widget(MDLabel(
                    text=f"  {mark} {name} (pieces {have}/{need}, hints {hints}/{total_hints})",
                    halign="left", size_hint_y=None, height=24))
            self.grid.add_widget(MDLabel(text="Slots:", halign="left", size_hint_y=None, height=28))
            for slot in sorted(ctx.real_slots):
                if slot in ctx.unlocked_slots:
                    text = f"  [open] {slot} = {ctx.real_slots[slot]}"
                elif ctx.guessable():
                    text = f"  [locked] {slot} = ?"
                else:
                    text = f"  [locked] {slot} = {ctx.shown_game(slot)}"
                self.grid.add_widget(MDLabel(text=text, halign="left", size_hint_y=None, height=24))

    class ProxyTab(BoxLayout):
        """Proxy routes, frozen state, and how to connect."""

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
            if proxy is None or not proxy.running:
                self.status_label.text = "Proxy - stopped (!mystery_proxy start)"
            else:
                self.status_label.text = f"Proxy - ws://{proxy.host}:{proxy.port}"
            self.grid.clear_widgets()
            for slot in sorted(ctx.real_slots):
                shown_game: str = ctx.shown_game(slot)
                if slot in ctx.relays:
                    state = "relay up" + (" *" if ctx.active_relay == slot else "")
                elif ctx.is_locked(slot):
                    state = "FROZEN"
                else:
                    state = "open"
                row = BoxLayout(orientation="horizontal", size_hint_y=None, height=36)
                row.add_widget(MDLabel(text=f"  {slot} [{shown_game}] [{state}]",
                                       halign="left", size_hint_x=0.7))
                connect_button = MDButton(MDButtonText(text="Connect"), style="filled")
                connect_button.bind(on_release=lambda _btn, name=slot: self._connect_slot(name))
                row.add_widget(connect_button)
                self.grid.add_widget(row)
            self.grid.add_widget(MDLabel(text=ctx.proxy_help(), halign="left",
                                         size_hint_y=None, height=220))

        def _connect_slot(self, slot: str) -> None:
            """Connect-button handler: start the relay, then refresh this tab."""
            try:
                self.ctx.start_relay(slot)
            except Exception as exc:
                logger.warning("Mystery: relay button failed for %s: %s", slot, exc)
            try:
                self.update_status()
            except Exception:
                pass

    class MysteryManager(GameManager):
        """Manager/UI for the Mystery client."""

        base_title = "Mystery Client"

        def build(self) -> Any:  # type: ignore[override]
            container = super().build()
            self.add_client_tab("Mystery", MysteryTab(self.ctx))
            self.add_client_tab("Proxy", ProxyTab(self.ctx))
            return container
else:
    class MysteryManager:
        """CLI-mode stub manager."""

        def __init__(self, ctx: MysteryContext) -> None:
            self.ctx = ctx
            self.base_title = "Mystery Client"
