from __future__ import annotations

"""Mystery Game world by Yutamon.

One slot randomizes which games fill the other slots (added live during
generate_early), with a slot-unlock system, slot locking (frozen / guess /
both), and server-side identity scrambling so direct connection is
impossible and only the proxy resolves slots.
(Puzzles are deferred for now; locks are the focus.)

Custom_worlds-only: never edits the server, other games, or core files.
"""

import logging
import os
from typing import Any, ClassVar, TextIO

from BaseClasses import Item, ItemClassification, Location, MultiWorld, Region
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, components, Type as ComponentType

from worlds.APAPI import get_current_stage, on_stage
from worlds.APAPI.debug import dprint

from .options import MysteryGameOptions, mystery_option_groups
from .cache import puzzle_hint_name, puzzle_piece_name
from .expansion import MultipleMysteryWorldsError
from .names import hash_slot_game, hash_slot_name, make_unique
from .puzzles import (
    MAX_PIECES,
    MAX_PUZZLES,
    MAX_UNLOCK_SLOTS,
    MYSTERY_TOKEN_ITEM,
    PUZZLE_HINTS,
    PUZZLE_PIECE_OVERRIDES,
    PUZZLE_ROSTER,
    build_item_name_to_id,
    build_location_name_to_id,
    puzzle_item_name,
    puzzle_location_name,
    unlock_item_name,
    unlock_location_name,
)

logger = logging.getLogger("APAPI.MysteryGame")

EXPANSION_NOTES: str = (
    "Mystery expansion adds players to the LIVE MultiWorld during generate_early "
    "via APAPI inject_player_now (worlds/APAPI/midgen.py): the roster, caches, "
    "CollectionState, and current-stage catch-up are all repaired, and every "
    "later stage evaluates player_ids fresh so newcomers flow through naturally. "
    "True post-generation resizing is impossible (frozen sizing)."
)


def launch_client(*args: Any) -> None:
    """Launch the Mystery client from the Archipelago launcher."""
    from worlds.LauncherComponents import launch
    from .MysteryClient import launch as MysteryMain
    launch(MysteryMain, name="Mystery Client", args=args)


components.append(Component(
    "Mystery Client",
    func=launch_client,
    component_type=ComponentType.CLIENT,
    supports_uri=True,
    description="Plays Mystery Game slots: solves puzzles, unlocks hidden slots, translates scrambled names.",
))


class MysteryWeb(WebWorld):
    """Web integration for Mystery Game."""

    theme = "partyTime"
    game = "Mystery Game"
    option_groups = mystery_option_groups


class MysteryItem(Item):
    """Item in the Mystery Game world."""

    game: str = "Mystery Game"


class MysteryLocation(Location):
    """Location in the Mystery Game world."""

    game: str = "Mystery Game"


class MysteryGameWorld(World):
    """Randomized-games slot with puzzles and a slot-unlock system."""

    game: str = "Mystery Game"
    author: str = "Yutamon"
    web: ClassVar[WebWorld] = MysteryWeb()

    options_dataclass = MysteryGameOptions
    options: MysteryGameOptions

    item_name_to_id: ClassVar[dict[str, int]] = build_item_name_to_id()
    location_name_to_id: ClassVar[dict[str, int]] = build_location_name_to_id()

    def __init__(self, multiworld: MultiWorld, player: int) -> None:
        super().__init__(multiworld, player)
        self.active_puzzles: list[str] = []
        self.active_unlock_count: int = 0
        self.unlock_map: dict[str, str] = {}
        #: {slot_name: game_name} for every other slot (guess answers live here).
        #: Re-keyed by server (possibly hashed) slot names in pre_output.
        self.real_slots: dict[str, str] = {}
        #: {player: {slot, game, server_slot, server_game}} once renamed.
        self.identity_map: dict[int, dict[str, str]] = {}
        #: Other player ids with unlock items, in id order (stable across renames).
        self.unlock_order: list[int] = []
        #: Other player ids left open from the start (first one, when locking).
        self.preunlocked: list[int] = []
        #: {puzzle: required piece count} for this seed.
        self.puzzle_pieces: dict[str, int] = {}
        #: {puzzle: [hint texts]} for this seed.
        self.puzzle_hints: dict[str, list[str]] = {}
        #: Rare Easter egg: this slot reports as "Mystery Cheese" server-side.
        self.cheese: bool = False

    def generate_early(self) -> None:
        # Only one Mystery Game per multiworld (like No Logic). The expansion
        # provider enforces the same rule before mutating generation input.
        mystery_count: int = sum(
            1 for world in self.multiworld.worlds.values()
            if isinstance(world, MysteryGameWorld))
        if mystery_count > 1:
            raise MultipleMysteryWorldsError(
                f"Found {mystery_count} Mystery Game worlds. "
                "Only one Mystery Game is allowed per multiworld session.")
        # Rare Easter egg roll (1%): decided here so it is seed-deterministic.
        self.cheese = self.random.random() < 0.01
        if self.cheese:
            dprint("mystery", f"player {self.player}: MYSTERY CHEESE rolled!")
        # Live expansion FIRST: unlock counts and tracked slots below must
        # include the added players. Skipped for tracker fake-gens (which
        # carry no specs) and unknown (non-staged) contexts.
        added: list[int] = self._expand_now()
        if added:
            dprint("mystery", f"player {self.player}: live-added players {added}")
        counts: dict[str, int] = dict(getattr(self.options, "game_counts", {}).value or {})
        slots: dict[str, str] = dict(getattr(self.options, "slot_games", {}).value or {})
        anon: int = int(getattr(self.options, "anonymous_games", 0).value or 0)
        scrambled: bool = bool(self.options.scrambled.value)
        requested_puzzles: int = int(self.options.puzzle_count.value)
        unlocks_on: bool = bool(self.options.enable_unlocks.value)
        dprint("mystery", (
            f"player {self.player}: stage={get_current_stage()} counts={counts} "
            f"slots={slots} anon={anon} scrambled={scrambled} "
            f"puzzles={requested_puzzles} unlocks={unlocks_on}"
        ))
        # Fail fast on unknown games so the YAML author sees it early.
        from worlds.AutoWorld import AutoWorldRegister
        for game in list(counts) + list(slots.values()):
            if game not in AutoWorldRegister.world_types:
                raise ValueError(f"[Mystery] Unknown game {game!r} in mystery options.")

        puzzle_total: int = max(0, min(requested_puzzles, MAX_PUZZLES))
        self.active_puzzles = PUZZLE_ROSTER[:puzzle_total]

        # Per-puzzle mechanics: YAML piece override wins, else the option.
        try:
            default_pieces: int = int(self.options.pieces_per_puzzle.value)
        except (TypeError, ValueError):
            default_pieces = 0
        default_pieces = max(0, min(default_pieces, MAX_PIECES))
        self.puzzle_pieces = {}
        self.puzzle_hints = {}
        for puzzle in self.active_puzzles:
            override: Any = PUZZLE_PIECE_OVERRIDES.get(puzzle)
            count: int = default_pieces if override is None else max(0, min(int(override), MAX_PIECES))
            self.puzzle_pieces[puzzle] = count
            hints: list[str] = list(PUZZLE_HINTS.get(puzzle, []))
            if hints:
                self.puzzle_hints[puzzle] = hints

        # Unlock slots: one per other slot in the multiworld (capped), so
        # every hidden slot can in principle get an "Unlock Slot N" check.
        other_slots: int = max(0, len(self.multiworld.player_ids) - 1)
        self.active_unlock_count = min(other_slots, MAX_UNLOCK_SLOTS) if unlocks_on else 0
        self.unlock_map = {
            unlock_location_name(index + 1): f"Slot {index + 1}" for index in range(self.active_unlock_count)
        }
        # Unlock mapping uses player-id order (stable across renames, unlike names).
        self.unlock_order = sorted(
            player for player in self.multiworld.player_ids if player != self.player
        )[:max(self.active_unlock_count, 0)]
        # Lock modes always leave the first other slot open so the seed is
        # playable from the start (traffic flows; its name stays hashed).
        try:
            locking: bool = int(self.options.slot_lock_mode.value) != 0
        except (TypeError, ValueError):
            locking = False
        others: list[int] = sorted(
            player for player in self.multiworld.player_ids if player != self.player)
        self.preunlocked = [others[0]] if locking and others else []
        # Real slot->game table for lock/guess modes. Only ever sent in THIS
        # slot's slot_data, so only the Mystery client sees the answers.
        self.real_slots = {}
        for other in self.multiworld.player_ids:
            if other == self.player:
                continue
            try:
                slot_name: str = self.multiworld.player_name[other]
                game_name: str = self.multiworld.game[other]
            except Exception:
                continue
            self.real_slots[slot_name] = game_name
        dprint("mystery", (
            f"player {self.player}: {len(self.active_puzzles)} puzzle(s), "
            f"{self.active_unlock_count} unlock(s), "
            f"{len(self.real_slots)} tracked slot(s) activated"
        ))

    def _expand_now(self) -> list[int]:
        """Add requested slots to the live MultiWorld (mid-generation path).

        Builds expansion specs from this slot's own options (same builder as
        the args-based flow, fed through an args-shaped shim) and injects
        each via :func:`worlds.APAPI.midgen.inject_player_now`.
        """
        from types import SimpleNamespace

        from worlds.APAPI.midgen import inject_player_now
        from worlds.APAPI.yaml_tools import resolve_player_files_dir

        from .expansion import build_mystery_specs

        if getattr(self.multiworld, "generation_is_fake", False):
            dprint("mystery", "skipping live expansion for fake generation")
            return []
        players_dir = resolve_player_files_dir()
        shim = SimpleNamespace(
            game={player: self.multiworld.game[player] for player in self.multiworld.player_ids},
            name={player: self.multiworld.player_name[player] for player in self.multiworld.player_ids},
            player_files_path=str(players_dir) if players_dir is not None else None,
            plando_options=getattr(self.multiworld, "plando_options", None),
            game_counts={self.player: self.options.game_counts},
            slot_games={self.player: self.options.slot_games},
            anonymous_games={self.player: self.options.anonymous_games},
            game_options={self.player: self.options.game_options},
            slot_options={self.player: self.options.slot_options},
        )
        added: list[int] = []
        for spec in build_mystery_specs(shim, self.multiworld.seed):
            added.append(inject_player_now(self.multiworld, spec))
        return added

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        hall = Region("Puzzle Hall", self.player, self.multiworld)
        shrine = Region("Unlock Shrine", self.player, self.multiworld)
        for puzzle in self.active_puzzles:
            location = MysteryLocation(
                self.player, puzzle_location_name(puzzle),
                self.location_name_to_id[puzzle_location_name(puzzle)], hall)
            location.place_locked_item(self.create_item(puzzle_item_name(puzzle)))
            hall.locations.append(location)
        for index in range(self.active_unlock_count):
            location = MysteryLocation(
                self.player, unlock_location_name(index + 1),
                self.location_name_to_id[unlock_location_name(index + 1)], shrine)
            # Each unlock check holds its own unlock item (pre-locked, always
            # reachable): this is the progression that opens gated slots.
            location.place_locked_item(self.create_item(unlock_item_name(index + 1)))
            shrine.locations.append(location)
        menu.connect(hall)
        menu.connect(shrine)
        self.multiworld.regions += [menu, hall, shrine]
        dprint("mystery", (
            f"player {self.player}: regions created "
            f"({len(hall.locations)} puzzle, {len(shrine.locations)} unlock locations)"
        ))

    def create_item(self, name: str) -> MysteryItem:
        classification = ItemClassification.progression if name.startswith("Unlock Slot") else ItemClassification.filler
        return MysteryItem(name, classification, self.item_name_to_id[name], self.player)

    def create_items(self) -> None:
        self.multiworld.itempool.append(self.create_item(MYSTERY_TOKEN_ITEM))
        # Unlock + puzzle-completion items are pre-locked at their locations
        # in create_regions (never in the pool).
        # Pieces + hints enter the general pool for this slot: finding them
        # is what lets the client solve / reveals hint text.
        for puzzle in self.active_puzzles:
            for piece in range(1, self.puzzle_pieces.get(puzzle, 0) + 1):
                self.multiworld.itempool.append(self.create_item(puzzle_piece_name(puzzle, piece)))
            for hint in range(1, len(self.puzzle_hints.get(puzzle, [])) + 1):
                self.multiworld.itempool.append(self.create_item(puzzle_hint_name(puzzle, hint)))
        dprint("mystery", f"player {self.player}: item pool extended")

    def get_filler_item_name(self) -> str:
        return MYSTERY_TOKEN_ITEM

    @classmethod
    def stage_set_rules(cls, multiworld: MultiWorld) -> None:
        """Make every location of locked slots rely on its Unlock Slot item.

        Runs once after every world's set_rules. In frozen/both modes each
        locked, non-preunlocked slot's locations (except events) require its
        Unlock Slot item (id-order mapping, stable across renames). Location
        level (not regions): custom Region subclasses may ignore access_rule
        entirely, while locations always funnel through it. Guess-only mode
        is proxy-enforced instead (no items are granted on guesses).
        """
        me: MysteryGameWorld | None = None
        for world in multiworld.worlds.values():
            if isinstance(world, cls):
                me = world
                break
        if me is None:
            return
        try:
            gated_modes: bool = int(me.options.slot_lock_mode.value) in (1, 3)
        except (TypeError, ValueError):
            gated_modes = False
        if not gated_modes or not me.unlock_order:
            if gated_modes:
                dprint("mystery", "frozen/both with no unlock items: logic gates skipped (proxy only)")
            return
        gated: int = 0
        for position, player in enumerate(me.unlock_order, start=1):
            if player in me.preunlocked:
                continue
            item_name: str = unlock_item_name(position)
            owner: int = me.player
            try:
                locations = list(multiworld.get_locations(player))
            except Exception as exc:
                logger.warning("[Mystery] Cannot list locations for player %s: %s", player, exc)
                continue
            for location in locations:
                if location.address is None:
                    continue  # events stay ungated (logic triggers, not checks)
                rule = lambda state, _item=item_name, _owner=owner: state.has(_item, _owner)
                try:
                    old_rule = getattr(location, "access_rule", None)
                    if old_rule is None or old_rule is Location.access_rule:
                        location.access_rule = rule
                    else:
                        location.access_rule = (
                            lambda state, _rule=rule, _old=old_rule:
                                _rule(state) and _old(state))
                    gated += 1
                except Exception as exc:
                    logger.warning("[Mystery] Cannot gate %s: %s", location.name, exc)
        dprint("mystery", f"gated {gated} location(s) on unlock items")

    def _rename_wanted(self) -> bool:
        """Games are hashed in every lock mode; slot names too on full scramble."""
        try:
            locked: bool = int(self.options.slot_lock_mode.value) != 0
        except (TypeError, ValueError):
            locked = False
        return locked or bool(self.options.scrambled.value)

    def _incoming_item_names(self) -> dict[int, list[str]]:
        """Sorted names of items sent to each slot (placement-final by pre_output)."""
        incoming: dict[int, list[str]] = {}
        multiworld = self.multiworld

        def _collect(item: Any) -> None:
            if item is None:
                return
            player: Any = getattr(item, "player", None)
            name: Any = getattr(item, "name", None)
            if isinstance(player, int) and isinstance(name, str):
                incoming.setdefault(player, []).append(name)

        for item in list(getattr(multiworld, "itempool", [])):
            _collect(item)
        try:
            for location in multiworld.get_filled_locations():
                _collect(getattr(location, "item", None))
        except Exception:
            pass
        for items in list(getattr(multiworld, "precollected_items", {}).values()):
            for item in list(items):
                _collect(item)
        return {player: sorted(names) for player, names in incoming.items()}

    def pre_output(self) -> None:
        """Replace locked slots' server-side identities with chained-hash names.

        Runs single-threaded after all generation (so ``get_game_worlds``
        and friends already ran) but before the output threads capture
        ``multiworld.game`` / ``player_name`` into multidata. The mystery
        slot itself is never renamed; ``world.game`` attributes are never
        touched (the datapackage step resolves those by real name).
        """
        multiworld = self.multiworld
        # Easter egg: this slot reports a different game server-side. Only
        # multiworld.game changes (never world.game: the datapackage step
        # resolves that by real name). The client retries as the new name.
        if self.cheese:
            multiworld.game[self.player] = "Mystery Cheese"
            dprint("mystery", f"player {self.player}: reporting as Mystery Cheese")
        if not self._rename_wanted():
            return
        seed_name: str = str(getattr(multiworld, "seed_name", multiworld.seed))
        incoming: dict[int, list[str]] = self._incoming_item_names()
        full_scramble: bool = bool(self.options.scrambled.value)
        used_games: set[str] = set(str(game) for game in multiworld.game.values())
        used_names: set[str] = set(str(name) for name in multiworld.player_name.values())
        # Shared across mystery slots so a second one adopts (never re-hashes)
        # and never renames fellow mystery slots (their clients must connect).
        shared: dict[int, dict[str, str]] = getattr(multiworld, "_mystery_identities", None)  # type: ignore[assignment]
        if not isinstance(shared, dict):
            shared = {}
            try:
                multiworld._mystery_identities = shared  # type: ignore[attr-defined]
            except Exception:
                pass
        renamed: int = 0
        for player in list(multiworld.player_ids):
            if player == self.player:
                continue
            try:
                if getattr(multiworld.worlds[player], "game", "") == "Mystery Game":
                    continue
            except Exception:
                continue
            if player in shared:
                self.identity_map[player] = shared[player]
                continue
            real_game: str = str(multiworld.game[player])
            real_name: str = str(multiworld.player_name[player])
            salt_items: list[str] = incoming.get(player, [])
            new_game: str = make_unique(
                hash_slot_game(real_game, seed_name, player, salt_items),
                used_games,
                lambda extra, _r=real_game, _s=seed_name, _p=player, _i=salt_items:
                    hash_slot_game(_r, _s, _p, _i, extra=extra),
            )
            if full_scramble:
                new_name: str = make_unique(
                    hash_slot_name(real_name, seed_name, player, salt_items),
                    used_names,
                    lambda extra, _r=real_name, _s=seed_name, _p=player, _i=salt_items:
                        hash_slot_name(_r, _s, _p, _i, extra=extra),
                )
            else:
                new_name = real_name
            self.identity_map[player] = {
                "slot": real_name,
                "game": real_game,
                "server_slot": new_name,
                "server_game": new_game,
            }
            shared[player] = self.identity_map[player]
            multiworld.game[player] = new_game
            if new_name != real_name:
                multiworld.player_name[player] = new_name
            renamed += 1
        # Items owned by renamed slots carry the hashed game name as well.
        game_of: dict[int, str] = {player: info["server_game"]
                                   for player, info in self.identity_map.items()}

        def _sync(item: Any) -> None:
            if item is None:
                return
            player = getattr(item, "player", None)
            if player in game_of and hasattr(item, "game"):
                try:
                    item.game = game_of[player]
                except Exception:
                    pass

        for item in list(multiworld.itempool):
            _sync(item)
        try:
            for location in multiworld.get_filled_locations():
                _sync(getattr(location, "item", None))
        except Exception:
            pass
        for items in list(multiworld.precollected_items.values()):
            for item in list(items):
                _sync(item)
        # Re-key answers by the names the server (and proxy) now use.
        # Shared map, so every mystery slot answers for every renamed slot.
        self.real_slots = {info["server_slot"]: info["game"] for info in shared.values()}
        self.identity_map = {player: shared[player] for player in shared}
        dprint("mystery", f"player {self.player}: renamed {renamed} slot identity(ies) "
                          f"({len(shared)} total, full_scramble={full_scramble})")

    def cheat_sheet_lines(self) -> list[str]:
        """Human-readable real<->server identity mapping (host eyes only)."""
        lines: list[str] = [
            "Mystery Identities (cheat sheet — host eyes only):",
            f"Seed: {getattr(self.multiworld, 'seed_name', self.multiworld.seed)}",
            "",
        ]
        for player in sorted(self.identity_map):
            info: dict[str, str] = self.identity_map[player]
            lines.append(f"  {info['server_slot']} ({info['server_game']}) "
                         f"is really {info['slot']} ({info['game']})")
        if self.cheese:
            lines.append("  This Mystery slot itself reports as 'Mystery Cheese' "
                         "(rare Easter egg; the client retries automatically).")
        if len(lines) == 3:
            lines.append("  (no renamed slots)")
        return lines

    def _has_cheat_sheet(self) -> bool:
        return bool(self.identity_map) or bool(self.cheese)

    def write_spoiler(self, spoiler_handle: TextIO) -> None:
        """Append the cheat sheet to the spoiler log (spoiler-enabled seeds)."""
        if not self._has_cheat_sheet():
            return
        spoiler_handle.write("\n\n" + "\n".join(self.cheat_sheet_lines()) + "\n")

    def generate_output(self, output_directory: str) -> None:
        """Write a mini cheat-sheet file into the zip when no spoiler exists.

        ``generate_output`` targets land in the final archive automatically.
        Skipped when a full spoiler will carry the cheat sheet instead
        (APAPI run-state knows); written fail-open when state is unknown.
        """
        if not self._has_cheat_sheet():
            return
        try:
            from worlds.APAPI.run_info import get_spoiler_level
            level: int | None = get_spoiler_level()
        except Exception:
            level = None
        if level:
            return
        path: str = os.path.join(output_directory, f"Mystery_Cheat_Sheet_P{self.player}.txt")
        try:
            with open(path, "w", encoding="utf-8-sig") as handle:
                handle.write("\n".join(self.cheat_sheet_lines()) + "\n")
            dprint("mystery", f"player {self.player}: mini cheat sheet written")
        except Exception as exc:
            logger.warning("[Mystery] Could not write mini cheat sheet: %s", exc)

    def _server_slot_name(self, player: int) -> str:
        """Slot name the server uses (post-rename when scrambled)."""
        info: dict[str, str] | None = self.identity_map.get(player)
        if info is not None:
            return info["server_slot"]
        try:
            return str(self.multiworld.player_name[player])
        except Exception:
            return f"Player{player}"

    def fill_slot_data(self) -> dict[str, Any]:
        # Data contract for the Mystery Client / future proxy work.
        # NOTE: mystery_real_slots / mystery_identities only reach THIS slot,
        # so guess answers never leak to the slots being guessed. Keys use
        # the server (possibly hashed) slot names, matching lobby/connect.
        return {
            "mystery_game_counts": dict(getattr(self.options, "game_counts", {}).value or {}),
            "mystery_slot_games": dict(getattr(self.options, "slot_games", {}).value or {}),
            "mystery_anonymous": int(getattr(self.options, "anonymous_games", 0).value or 0),
            "mystery_scrambled": bool(self.options.scrambled.value),
            "mystery_puzzles": list(self.active_puzzles),
            "mystery_unlock_map": dict(self.unlock_map),
            "mystery_lock_mode": int(self.options.slot_lock_mode.value),
            "mystery_real_slots": dict(self.real_slots),
            "mystery_preunlocked": [self._server_slot_name(player) for player in self.preunlocked],
            "mystery_cheese": bool(self.cheese),
            "mystery_puzzle_pieces": dict(self.puzzle_pieces),
            "mystery_puzzle_hints": {puzzle: list(hints)
                                     for puzzle, hints in self.puzzle_hints.items()},
            "mystery_identities": {
                info["server_slot"]: {"game": info["game"], "server_game": info["server_game"],
                                      "name": info["slot"]}
                for info in self.identity_map.values()
            },
            "mystery_seal_games": int(self.options.slot_lock_mode.value) != 0,
            "mystery_cache_prefix": "mystery_cache",
            "mystery_unlocks_prefix": "mystery_unlocks",
            "mystery_stage_at_output": get_current_stage(),
        }


def _log_stage(multiworld: MultiWorld, *args: Any) -> None:
    dprint("mystery", f"entering stage {get_current_stage()}")


for _stage in ("generate_early", "create_regions", "create_items", "set_rules", "pre_fill", "post_fill"):
    try:
        on_stage(_stage, _log_stage)
    except Exception:
        pass

dprint("init", f"mystery_game world loaded ({len(PUZZLE_ROSTER)} puzzles, "
               f"{len(MysteryGameWorld.item_name_to_id)} items, "
               f"{len(MysteryGameWorld.location_name_to_id)} locations)")
