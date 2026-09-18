from __future__ import annotations

"""Mystery Game: randomizes which games fill other slots with unlock/lock and identity scrambling."""

import logging
import os
from typing import Any, ClassVar, TextIO

from BaseClasses import Item, ItemClassification, Location, MultiWorld, Region
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, components, Type as ComponentType

from worlds.APAPI import get_current_stage, on_stage
from worlds.APAPI.debug import dprint

from .options import MysteryGameOptions, MysteryNuzlockeDeathLink, MysteryNuzlockeLives, mystery_option_groups
from .cache import puzzle_hint_name, puzzle_piece_name
from .expansion import MultipleMysteryWorldsError
from .names import hash_slot_game, hash_slot_name, make_unique
from .puzzles import (
    unlock_item_name_for_slot,
    unlock_location_name_for_slot,
)

# Make the per-game Nuzlocke DeathLink override available to every game via APAPI.
# Games with broken DeathLink can set this in their yaml to "suppress" or "isolate".
# When Mystery creates a slot, it will also set this for you if its own Nuzlocke
# suppress/isolate options are enabled, so the generated slot's slot_data shows it.
try:
    from worlds.APAPI import inject_option

    inject_option(
        "mystery_nuzlocke_deathlink",
        MysteryNuzlockeDeathLink,
        games=None,
        group_name="Mystery Nuzlocke",
    )
    inject_option(
        "mystery_nuzlocke_lives",
        MysteryNuzlockeLives,
        games=None,
        group_name="Mystery Nuzlocke",
    )
except Exception:
    pass

# Patch every game's fill_slot_data via APAPI so the per-game preference actually
# appears in that game's own slot_data when Mystery sets it.
try:
    from worlds.APAPI import inject_world_behavior

    def _mystery_nuzlocke_after_fill_slot_data(result: Any, world_self: Any, *args: Any, **kwargs: Any) -> Any:
        if not isinstance(result, dict):
            result = {}
        try:
            if hasattr(world_self.options, "mystery_nuzlocke_deathlink"):
                val = world_self.options.mystery_nuzlocke_deathlink.value
                if int(val) != 0:
                    result.setdefault("mystery_nuzlocke_deathlink", int(val))
                    try:
                        name = world_self.options.mystery_nuzlocke_deathlink.current_key
                    except Exception:
                        name = str(val)
                    result.setdefault("mystery_nuzlocke_deathlink_name", name)
        except Exception:
            pass
        try:
            if hasattr(world_self.options, "mystery_nuzlocke_lives"):
                val = world_self.options.mystery_nuzlocke_lives.value
                if int(val) != 1:
                    result.setdefault("mystery_nuzlocke_lives", int(val))
        except Exception:
            pass
        return result

    # Inject for all currently loaded games and future ones via world_ready
    try:
        from worlds.AutoWorld import AutoWorldRegister
        from worlds.APAPI.world_ready import on_worlds_loaded

        for _g in list(AutoWorldRegister.world_types.keys()):
            try:
                inject_world_behavior(_g, "fill_slot_data", after=_mystery_nuzlocke_after_fill_slot_data)
            except Exception:
                pass

        def _inject_nuzlocke_late() -> None:
            from worlds.AutoWorld import AutoWorldRegister as _Reg

            for _g in list(_Reg.world_types.keys()):
                try:
                    inject_world_behavior(_g, "fill_slot_data", after=_mystery_nuzlocke_after_fill_slot_data)
                except Exception:
                    pass

        on_worlds_loaded(_inject_nuzlocke_late)
    except Exception:
        pass
except Exception:
    pass
from .puzzles import (
    EXTRA_LIFE_ITEM,
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
    """Input: args. Output: launches Mystery Client."""
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

# Import code builder to register its launcher component
try:
    from . import MysteryCodeBuilder  # noqa: F401
except Exception:
    pass


class MysteryWeb(WebWorld):
    """Web integration for Mystery Game."""

    theme = "partyTime"
    game = "Mystery Game"
    option_groups = mystery_option_groups


class MysteryItem(Item):
    """Mystery Game item."""

    game: str = "Mystery Game"


class MysteryLocation(Location):
    """Mystery Game location."""

    game: str = "Mystery Game"


class MysteryGameWorld(World):
    """Randomized-games slot with puzzles and unlocks."""

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
        self.real_slots: dict[str, str] = {}
        self.identity_map: dict[int, dict[str, str]] = {}
        self.unlock_order: list[int] = []
        self.pre_existing_players: list[int] = []
        self.expanded_players: list[int] = []
        self.untouched_slots: dict[str, str] = {}
        self.preunlocked: list[int] = []
        self.puzzle_pieces: dict[str, int] = {}
        self.puzzle_hints: dict[str, list[str]] = {}
        self.cheese: bool = False
        self.nuzlocke_deathlink_modes: dict[str, int] = {}
        self.nuzlocke_lives: int = 1
        self.nuzlocke_lives_per_slot: dict[str, int] = {}
        self.nuzlocke_extra_lives: int = 0
        self.nuzlocke_extra_distribution: int = 0
        self.nuzlocke_extra_assignments: list[str] = []  # for specific mode: slot per extra life index
        self.nuzlocke_shared_lives: bool = False
        self.nuzlocke_shared_extra_lives: bool = False
        self.game_code_sets: dict[str, str] = {}
        self.code_set_slots: dict[str, list[str]] = {}  # set_name -> list of slot names
        self.slot_to_code_set: dict[str, str] = {}  # slot_name -> set_name
        self.enable_global_bridge: bool = False
        self.global_bridge_port: int = 11400

    def generate_early(self) -> None:
        """Input: self. Output: expands world, sets puzzles/unlocks/slot maps."""
        mystery_count: int = sum(
            1 for world in self.multiworld.worlds.values()
            if isinstance(world, MysteryGameWorld))
        if mystery_count > 1:
            raise MultipleMysteryWorldsError(
                f"Found {mystery_count} Mystery Game worlds. "
                "Only one Mystery Game is allowed per multiworld session.")
        self.cheese = self.random.random() < 0.01
        if self.cheese:
            dprint("mystery", f"player {self.player}: MYSTERY CHEESE rolled!")
        self.pre_existing_players = sorted(
            player for player in self.multiworld.player_ids if player != self.player)
        added: list[int] = self._expand_now()
        self.expanded_players = list(added)
        if added:
            dprint("mystery", f"player {self.player}: live-added players {added} "
                               f"(pre-existing: {self.pre_existing_players})")
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
        from worlds.AutoWorld import AutoWorldRegister
        for game in list(counts) + list(slots.values()):
            if game not in AutoWorldRegister.world_types:
                raise ValueError(f"[Mystery] Unknown game {game!r} in mystery options.")

        puzzle_total: int = max(0, min(requested_puzzles, MAX_PUZZLES))
        self.active_puzzles = PUZZLE_ROSTER[:puzzle_total]

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

        self.active_unlock_count = min(len(self.expanded_players), MAX_UNLOCK_SLOTS) if unlocks_on else 0
        self.unlock_map = {
            unlock_location_name(index + 1): f"Slot {index + 1}" for index in range(self.active_unlock_count)
        }
        self.unlock_order = sorted(self.expanded_players)[:max(self.active_unlock_count, 0)]
        self.untouched_slots = {}
        for other in self.pre_existing_players:
            try:
                self.untouched_slots[str(self.multiworld.player_name[other])] = \
                    str(self.multiworld.game[other])
            except Exception:
                continue
        # Build code_set_slots mapping early for per-set unlock handling
        # (Need to populate before preunlocked logic)
        try:
            # Ensure game_code_sets is populated (from earlier nuzlocke handling, but ensure here)
            if not hasattr(self, 'game_code_sets') or not self.game_code_sets:
                try:
                    self.game_code_sets = dict(getattr(self.options, "game_code_sets", {}).value or {})  # type: ignore[attr-defined]
                except Exception:
                    self.game_code_sets = {}
            if not hasattr(self, 'code_set_slots') or not self.code_set_slots:
                self.code_set_slots = {}
                self.slot_to_code_set = {}
            if self.game_code_sets and self.expanded_players and not self.code_set_slots:
                import base64
                import gzip
                import io
                import zipfile
                from Utils import parse_yaml
                for set_name, code in self.game_code_sets.items():
                    if not isinstance(code, str) or not code.strip():
                        continue
                    try:
                        decoded = base64.b64decode(code.strip())
                        slot_names_in_set: list[str] = []
                        try:
                            with gzip.GzipFile(fileobj=io.BytesIO(decoded)) as f:
                                decompressed = f.read()
                            if decompressed[:4] == b'PK\x03\x04':
                                with zipfile.ZipFile(io.BytesIO(decompressed)) as zf:
                                    for zi in zf.infolist():
                                        if zi.is_dir() or not zi.filename.lower().endswith(('.yaml', '.yml')):
                                            continue
                                        try:
                                            yaml_content = zf.read(zi).decode('utf-8-sig')
                                            docs = [yaml_content] if "---" not in yaml_content else []
                                            if "---" in yaml_content:
                                                docs = []
                                                cur = []
                                                for line in yaml_content.splitlines():
                                                    if line.strip() == "---":
                                                        if cur:
                                                            docs.append('\n'.join(cur))
                                                            cur = []
                                                    else:
                                                        cur.append(line)
                                                if cur:
                                                    docs.append('\n'.join(cur))
                                            for doc in docs:
                                                doc = doc.strip()
                                                if not doc:
                                                    continue
                                                try:
                                                    parsed = parse_yaml(doc)
                                                except Exception:
                                                    continue
                                                if isinstance(parsed, dict) and parsed.get('name'):
                                                    name = str(parsed['name']).strip()
                                                    if name and name not in slot_names_in_set:
                                                        slot_names_in_set.append(name)
                                        except Exception:
                                            continue
                            else:
                                yaml_content = decompressed.decode('utf-8-sig')
                                docs = [yaml_content] if "---" not in yaml_content else []
                                if "---" in yaml_content:
                                    docs = []
                                    cur = []
                                    for line in yaml_content.splitlines():
                                        if line.strip() == "---":
                                            if cur:
                                                docs.append('\n'.join(cur))
                                                cur = []
                                        else:
                                            cur.append(line)
                                    if cur:
                                        docs.append('\n'.join(cur))
                                for doc in docs:
                                    doc = doc.strip()
                                    if not doc:
                                        continue
                                    try:
                                        parsed = parse_yaml(doc)
                                    except Exception:
                                        continue
                                    if isinstance(parsed, dict) and parsed.get('name'):
                                        name = str(parsed['name']).strip()
                                        if name and name not in slot_names_in_set:
                                            slot_names_in_set.append(name)
                        except Exception:
                            try:
                                yaml_content = decoded.decode('utf-8-sig')
                                docs = [yaml_content] if "---" not in yaml_content else []
                                if "---" in yaml_content:
                                    docs = []
                                    cur = []
                                    for line in yaml_content.splitlines():
                                        if line.strip() == "---":
                                            if cur:
                                                docs.append('\n'.join(cur))
                                                cur = []
                                        else:
                                            cur.append(line)
                                    if cur:
                                        docs.append('\n'.join(cur))
                                for doc in docs:
                                    doc = doc.strip()
                                    if not doc:
                                        continue
                                    try:
                                        parsed = parse_yaml(doc)
                                    except Exception:
                                        continue
                                    if isinstance(parsed, dict) and parsed.get('name'):
                                        name = str(parsed['name']).strip()
                                        if name and name not in slot_names_in_set:
                                            slot_names_in_set.append(name)
                            except Exception:
                                continue
                        expanded_names = {str(self.multiworld.player_name[p]): p for p in self.expanded_players}
                        matched: list[str] = []
                        for sname in slot_names_in_set:
                            if sname in expanded_names:
                                matched.append(sname)
                            else:
                                for exp_name in expanded_names:
                                    if exp_name.lower() == sname.lower():
                                        matched.append(exp_name)
                                        break
                        if matched:
                            self.code_set_slots[set_name] = matched
                            for sname in matched:
                                self.slot_to_code_set[sname] = set_name
                        dprint("mystery", f"early code set {set_name!r} -> {matched}")
                    except Exception as exc:
                        logger.debug(f"[Mystery] Failed to decode code set {set_name!r} early: {exc}")
                        continue
        except Exception as exc:
            logger.debug(f"[Mystery] early code_set build failed: {exc}")
        try:
            locking: bool = int(self.options.slot_lock_mode.value) != 0
        except (TypeError, ValueError):
            locking = False
        try:
            starting: int = int(getattr(self.options, "starting_slots", 1).value or 1)
        except (TypeError, ValueError):
            starting = 1
        starting = max(1, starting)
        try:
            allow_with_others = bool(self.options.allow_unlock_with_others.value)
        except Exception:
            allow_with_others = False
        try:
            unlock_per_set = bool(self.options.unlock_per_set.value)  # type: ignore[attr-defined]
        except Exception:
            unlock_per_set = False
        others: list[int] = sorted(self.expanded_players)
        if locking and others and (not self.pre_existing_players or allow_with_others):
            if unlock_per_set and self.game_code_sets and self.code_set_slots:
                # Per-set: treat each code set as a player, unlock that many sets
                # Build list of sets that have at least one expanded player
                set_to_players: dict[str, list[int]] = {}
                for player in others:
                    try:
                        slot_name = str(self.multiworld.player_name[player])
                        set_name = self.slot_to_code_set.get(slot_name)
                        if set_name:
                            set_to_players.setdefault(set_name, []).append(player)
                    except Exception:
                        continue
                # Also handle slots not in any set as individual sets
                non_set_players = [p for p in others if str(self.multiworld.player_name[p]) not in self.slot_to_code_set]
                # Create list of groups: each set is a group, each non-set player is its own group
                groups: list[list[int]] = list(set_to_players.values())
                for p in non_set_players:
                    groups.append([p])
                # Sample groups
                sampled_groups = self.random.sample(groups, min(starting, len(groups)))
                self.preunlocked = [p for group in sampled_groups for p in group]
                dprint("mystery", f"per-set unlock: starting={starting} sampled {len(sampled_groups)} sets -> {len(self.preunlocked)} slots")
            else:
                self.preunlocked = self.random.sample(others, min(starting, len(others)))
        else:
            self.preunlocked = []
        self.real_slots = {}
        for other in self.expanded_players:
            try:
                slot_name: str = self.multiworld.player_name[other]
                game_name: str = self.multiworld.game[other]
            except Exception:
                continue
            self.real_slots[slot_name] = game_name
        # Per-slot Nuzlocke DeathLink preference for visibility and proxy handling.
        # Filled from the actual per-game option values that were injected into each
        # Mystery-created slot (via APAPI). This shows in Mystery's slot_data as
        # {slot_name: mode} where mode 1=suppress, 2=isolate.
        self.nuzlocke_deathlink_modes = {}
        for player in self.expanded_players:
            try:
                w = self.multiworld.worlds[player]
                if hasattr(w.options, "mystery_nuzlocke_deathlink"):
                    mode = int(w.options.mystery_nuzlocke_deathlink.value)
                    if mode != 0:
                        slot_name = str(self.multiworld.player_name[player])
                        self.nuzlocke_deathlink_modes[slot_name] = mode
            except Exception:
                continue
        # Global + per-slot lives (FlexRange 1-5, allow higher). Stored server-known in slot_data.
        try:
            self.nuzlocke_lives = int(self.options.nuzlocke_lives.value)  # type: ignore[attr-defined]
        except Exception:
            self.nuzlocke_lives = 1
        if self.nuzlocke_lives < 1:
            self.nuzlocke_lives = 1
        self.nuzlocke_lives_per_slot = {}
        for player in self.expanded_players:
            try:
                w = self.multiworld.worlds[player]
                if hasattr(w.options, "mystery_nuzlocke_lives"):
                    lives = int(w.options.mystery_nuzlocke_lives.value)
                    # Only store when it differs from the global default to keep slot_data small.
                    if lives != self.nuzlocke_lives and lives >= 1:
                        slot_name = str(self.multiworld.player_name[player])
                        self.nuzlocke_lives_per_slot[slot_name] = lives
            except Exception:
                continue
        # Extra lives (global setting only, useful item). Server-known.
        try:
            self.nuzlocke_extra_lives = int(self.options.nuzlocke_extra_lives.value)  # type: ignore[attr-defined]
        except Exception:
            self.nuzlocke_extra_lives = 0
        if self.nuzlocke_extra_lives < 0:
            self.nuzlocke_extra_lives = 0
        try:
            self.nuzlocke_extra_distribution = int(self.options.nuzlocke_extra_distribution.value)  # type: ignore[attr-defined]
        except Exception:
            self.nuzlocke_extra_distribution = 0
        if self.nuzlocke_extra_distribution not in (0, 1, 2):
            self.nuzlocke_extra_distribution = 0
        self.nuzlocke_extra_assignments = []
        if self.nuzlocke_extra_lives > 0 and self.nuzlocke_extra_distribution == 2 and self.expanded_players:
            # Specific: round-robin pre-assign each extra life to a Nuzlocke slot
            candidates = sorted(self.real_slots.keys())
            if candidates:
                for i in range(self.nuzlocke_extra_lives):
                    self.nuzlocke_extra_assignments.append(candidates[i % len(candidates)])
                dprint("mystery", f"extra lives specific assignments: {self.nuzlocke_extra_assignments}")
        try:
            self.nuzlocke_shared_lives = bool(self.options.nuzlocke_shared_lives.value)  # type: ignore[attr-defined]
        except Exception:
            self.nuzlocke_shared_lives = False
        try:
            self.nuzlocke_shared_extra_lives = bool(self.options.nuzlocke_shared_extra_lives.value)  # type: ignore[attr-defined]
        except Exception:
            self.nuzlocke_shared_extra_lives = False
        try:
            self.game_code_sets = dict(getattr(self.options, "game_code_sets", {}).value or {})  # type: ignore[attr-defined]
        except Exception:
            self.game_code_sets = {}
        # Build code_set_slots mapping - decode each code set to get its slot names
        self.code_set_slots = {}
        self.slot_to_code_set = {}
        if self.game_code_sets and self.expanded_players:
            # Build mapping by decoding each code set and matching to expanded slot names
            # We need to know which expanded slots came from which code set
            # The expansion's build_mystery_specs already did this and created slots with those names
            # We can reconstruct by decoding each code set and seeing which slot names it contains
            try:
                import base64
                import gzip
                import io
                import zipfile
                from Utils import parse_yaml
                for set_name, code in self.game_code_sets.items():
                    if not isinstance(code, str) or not code.strip():
                        continue
                    try:
                        decoded = base64.b64decode(code.strip())
                        slot_names_in_set: list[str] = []
                        # Try gzip
                        try:
                            with gzip.GzipFile(fileobj=io.BytesIO(decoded)) as f:
                                decompressed = f.read()
                            # Check if zip
                            if decompressed[:4] == b'PK\x03\x04':
                                with zipfile.ZipFile(io.BytesIO(decompressed)) as zf:
                                    for zi in zf.infolist():
                                        if zi.is_dir() or not zi.filename.lower().endswith(('.yaml', '.yml')):
                                            continue
                                        try:
                                            yaml_content = zf.read(zi).decode('utf-8-sig')
                                            # Handle multiple docs
                                            docs = [yaml_content] if "---" not in yaml_content else []
                                            if "---" in yaml_content:
                                                docs = []
                                                cur = []
                                                for line in yaml_content.splitlines():
                                                    if line.strip() == "---":
                                                        if cur:
                                                            docs.append('\n'.join(cur))
                                                            cur = []
                                                    else:
                                                        cur.append(line)
                                                if cur:
                                                    docs.append('\n'.join(cur))
                                            for doc in docs:
                                                doc = doc.strip()
                                                if not doc:
                                                    continue
                                                try:
                                                    parsed = parse_yaml(doc)
                                                except Exception:
                                                    continue
                                                if isinstance(parsed, dict) and parsed.get('name'):
                                                    name = str(parsed['name']).strip()
                                                    if name and name not in slot_names_in_set:
                                                        slot_names_in_set.append(name)
                                        except Exception:
                                            continue
                            else:
                                yaml_content = decompressed.decode('utf-8-sig')
                                # Similar handling for gzipped yaml(s)
                                docs = [yaml_content] if "---" not in yaml_content else []
                                if "---" in yaml_content:
                                    docs = []
                                    cur = []
                                    for line in yaml_content.splitlines():
                                        if line.strip() == "---":
                                            if cur:
                                                docs.append('\n'.join(cur))
                                                cur = []
                                        else:
                                            cur.append(line)
                                    if cur:
                                        docs.append('\n'.join(cur))
                                for doc in docs:
                                    doc = doc.strip()
                                    if not doc:
                                        continue
                                    try:
                                        parsed = parse_yaml(doc)
                                    except Exception:
                                        continue
                                    if isinstance(parsed, dict) and parsed.get('name'):
                                        name = str(parsed['name']).strip()
                                        if name and name not in slot_names_in_set:
                                            slot_names_in_set.append(name)
                        except Exception:
                            # Try plain base64 (not gzipped)
                            try:
                                yaml_content = decoded.decode('utf-8-sig')
                                docs = [yaml_content] if "---" not in yaml_content else []
                                if "---" in yaml_content:
                                    docs = []
                                    cur = []
                                    for line in yaml_content.splitlines():
                                        if line.strip() == "---":
                                            if cur:
                                                docs.append('\n'.join(cur))
                                                cur = []
                                        else:
                                            cur.append(line)
                                    if cur:
                                        docs.append('\n'.join(cur))
                                for doc in docs:
                                    doc = doc.strip()
                                    if not doc:
                                        continue
                                    try:
                                        parsed = parse_yaml(doc)
                                    except Exception:
                                        continue
                                    if isinstance(parsed, dict) and parsed.get('name'):
                                        name = str(parsed['name']).strip()
                                        if name and name not in slot_names_in_set:
                                            slot_names_in_set.append(name)
                            except Exception:
                                continue
                        # Now match these slot names to actual expanded slot names
                        # Use case-insensitive matching and handle placeholder resolution
                        expanded_names = {str(self.multiworld.player_name[p]): p for p in self.expanded_players}
                        matched: list[str] = []
                        for sname in slot_names_in_set:
                            # Try exact match
                            if sname in expanded_names:
                                matched.append(sname)
                            else:
                                # Try case-insensitive
                                for exp_name in expanded_names:
                                    if exp_name.lower() == sname.lower():
                                        matched.append(exp_name)
                                        break
                        if matched:
                            self.code_set_slots[set_name] = matched
                            for sname in matched:
                                self.slot_to_code_set[sname] = set_name
                            dprint("mystery", f"code set {set_name!r} -> {matched}")
                    except Exception as exc:
                        logger.debug(f"[Mystery] Failed to decode code set {set_name!r}: {exc}")
                        continue
                if self.code_set_slots:
                    dprint("mystery", f"built code_set_slots: {self.code_set_slots}")
            except Exception as exc:
                logger.warning(f"[Mystery] Failed to build code_set_slots: {exc}")
            dprint("mystery", f"game_code_sets: {list(self.game_code_sets.keys())} shared_lives={self.nuzlocke_shared_lives} shared_extra={self.nuzlocke_shared_extra_lives} code_set_slots={self.code_set_slots}")

        try:
            self.enable_global_bridge = bool(self.options.enable_global_bridge.value)  # type: ignore[attr-defined]
        except Exception:
            self.enable_global_bridge = False
        try:
            self.global_bridge_port = int(self.options.global_bridge_port.value)  # type: ignore[attr-defined]
            if not (1024 <= self.global_bridge_port <= 65535):
                self.global_bridge_port = 11400
        except Exception:
            self.global_bridge_port = 11400
        if self.enable_global_bridge:
            dprint("mystery", f"global bridge enabled on port {self.global_bridge_port} (host broadcast, APWorld not required for clients)")
        dprint("mystery", (
            f"player {self.player}: {len(self.active_puzzles)} puzzle(s), "
            f"{self.active_unlock_count} unlock(s), "
            f"{len(self.real_slots)} tracked slot(s) activated"
            f" (nuzlocke lives={self.nuzlocke_lives}, per-slot={len(self.nuzlocke_lives_per_slot)},"
            f" extra={self.nuzlocke_extra_lives} mode={self.nuzlocke_extra_distribution},"
            f" global_bridge={self.enable_global_bridge}:{self.global_bridge_port})"
        ))

    def _expand_now(self) -> list[int]:
        """Input: self. Returns: list of added player ids via APAPI inject."""
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
            filtered_games={self.player: self.options.filtered_games},
            filtered_games_as_whitelist={self.player: self.options.filtered_games_as_whitelist},
            random_options={self.player: self.options.random_options},
            random_set_options={self.player: self.options.random_set_options},
            nuzlocke={self.player: self.options.nuzlocke},
            nuzlocke_deathlink={self.player: self.options.nuzlocke_deathlink},
            nuzlocke_lives={self.player: self.options.nuzlocke_lives},
            nuzlocke_extra_lives={self.player: self.options.nuzlocke_extra_lives},
            nuzlocke_extra_distribution={self.player: self.options.nuzlocke_extra_distribution},
            nuzlocke_shared_lives={self.player: self.options.nuzlocke_shared_lives},
            nuzlocke_shared_extra_lives={self.player: self.options.nuzlocke_shared_extra_lives},
            game_code_sets={self.player: self.options.game_code_sets},
            game_options={self.player: self.options.game_options},
            slot_options={self.player: self.options.slot_options},
        )
        added: list[int] = []
        for spec in build_mystery_specs(shim, self.multiworld.seed):
            added.append(inject_player_now(self.multiworld, spec))
        return added

    def create_regions(self) -> None:
        """Input: self. Output: creates Menu/Puzzle Hall/Unlock Shrine regions."""
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
            shrine.locations.append(location)
        menu.connect(hall)
        menu.connect(shrine)
        self.multiworld.regions += [menu, hall, shrine]
        dprint("mystery", (
            f"player {self.player}: regions created "
            f"({len(hall.locations)} puzzle, {len(shrine.locations)} unlock locations)"
        ))

    def create_item(self, name: str) -> MysteryItem:
        """Input: item name. Returns: MysteryItem with classification."""
        if name == EXTRA_LIFE_ITEM:
            # Useful when Nuzlocke is on, otherwise filler. Use useful|deprioritized|skip_balancing
            # so generation does not rely on its existence (no priority, no balancing pull).
            try:
                nuz = bool(self.options.nuzlocke.value)  # type: ignore[attr-defined]
            except Exception:
                nuz = False
            classification = (
                ItemClassification.useful | ItemClassification.deprioritized | ItemClassification.skip_balancing
            ) if nuz else ItemClassification.filler
        elif name.startswith("Unlock Slot"):
            classification = ItemClassification.progression_deprioritized_skip_balancing
        else:
            classification = ItemClassification.filler
        return MysteryItem(name, classification, self.item_name_to_id[name], self.player)

    def create_items(self) -> None:
        """Input: self. Output: adds tokens/unlocks/pieces/hints to itempool and precollected for starting slots."""
        self.multiworld.itempool.append(self.create_item(MYSTERY_TOKEN_ITEM))
        # Starting slots are given as precollected so logic (CollectionState) assumes them.
        # Map unlock_order position -> player for preunlocked detection.
        preunlocked_positions: set[int] = set()
        for pos, player in enumerate(self.unlock_order, start=1):
            if player in self.preunlocked:
                preunlocked_positions.add(pos)
        unlocked_precollected: int = 0
        for index in range(self.active_unlock_count):
            pos = index + 1
            item = self.create_item(unlock_item_name(pos))
            if pos in preunlocked_positions:
                # Give directly as precollected (not in pool) so spheres see it from start.
                self.multiworld.push_precollected(item)
                unlocked_precollected += 1
            else:
                self.multiworld.itempool.append(item)
        for puzzle in self.active_puzzles:
            for piece in range(1, self.puzzle_pieces.get(puzzle, 0) + 1):
                self.multiworld.itempool.append(self.create_item(puzzle_piece_name(puzzle, piece)))
            for hint in range(1, len(self.puzzle_hints.get(puzzle, [])) + 1):
                self.multiworld.itempool.append(self.create_item(puzzle_hint_name(puzzle, hint)))
        # Extra lives (global setting, useful item when Nuzlocke on)
        for _ in range(self.nuzlocke_extra_lives):
            self.multiworld.itempool.append(self.create_item(EXTRA_LIFE_ITEM))
        dprint("mystery", f"player {self.player}: item pool extended ({unlocked_precollected} unlock(s) precollected, {self.nuzlocke_extra_lives} extra lives)")

    def get_filler_item_name(self) -> str:
        """Returns: filler item name."""
        return MYSTERY_TOKEN_ITEM

    @classmethod
    def stage_pre_fill(cls, multiworld: MultiWorld) -> None:
        """Input: multiworld. Output: gates locked slots and unlock checks behind Unlock items."""
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

        def _gate(location: Any, item_name: str, owner: int) -> bool:
            rule = lambda state, _item=item_name, _owner=owner: state.has(_item, _owner)
            try:
                old_rule = getattr(location, "access_rule", None)
                if old_rule is None or old_rule is Location.access_rule:
                    location.access_rule = rule
                else:
                    location.access_rule = (
                        lambda state, _rule=rule, _old=old_rule:
                            _rule(state) and _old(state))
                return True
            except Exception as exc:
                logger.warning("[Mystery] Cannot gate %s: %s", location.name, exc)
                return False

        gated: int = 0
        # Gate ALL tracked slots behind their Unlock item. Starting slots are
        # precollected (create_items) so their gate is immediately satisfied for
        # logic / spheres – no longer skipped via slot_data.
        for position, player in enumerate(me.unlock_order, start=1):
            item_name: str = unlock_item_name(position)
            owner: int = me.player
            try:
                locations = list(multiworld.get_locations(player))
            except Exception as exc:
                logger.warning("[Mystery] Cannot list locations for player %s: %s", player, exc)
                continue
            for location in locations:
                if _gate(location, item_name, owner):
                    gated += 1
        checks_gated: int = 0
        try:
            own_locations = {location.name: location
                             for location in multiworld.get_locations(me.player)}
        except Exception as exc:
            logger.warning("[Mystery] Cannot list mystery locations: %s", exc)
            own_locations = {}
        for position in range(1, me.active_unlock_count + 1):
            location = own_locations.get(unlock_location_name(position))
            if location is None:
                continue
            if _gate(location, unlock_item_name(position), me.player):
                checks_gated += 1
        dprint("mystery", f"gated {gated} location(s) on unlock items, {checks_gated} unlock check(s)")

    def _rename_wanted(self) -> bool:
        """Returns: True if slot/game hashing is needed."""
        try:
            locked: bool = int(self.options.slot_lock_mode.value) != 0
        except (TypeError, ValueError):
            locked = False
        return locked or bool(self.options.scrambled.value)

    def _incoming_item_names(self) -> dict[int, list[str]]:
        """Returns: sorted item names per player."""
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
        """Input: self. Output: replaces locked slot identities with hashed names."""
        multiworld = self.multiworld
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
        shared: dict[int, dict[str, str]] = getattr(multiworld, "_mystery_identities", None)  # type: ignore[assignment]
        if not isinstance(shared, dict):
            shared = {}
            try:
                multiworld._mystery_identities = shared  # type: ignore[attr-defined]
            except Exception:
                pass
        renamed: int = 0
        for player in list(self.expanded_players):
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
        self.real_slots = {info["server_slot"]: info["game"] for info in shared.values()}
        self.identity_map = {player: shared[player] for player in shared}
        dprint("mystery", f"player {self.player}: renamed {renamed} slot identity(ies) "
                          f"({len(shared)} total, full_scramble={full_scramble})")

    def cheat_sheet_lines(self) -> list[str]:
        """Returns: host cheat sheet lines mapping real to server identities."""
        lines: list[str] = [
            "Mystery Identities (cheat sheet — host eyes only):",
            f"Seed: {getattr(self.multiworld, 'seed_name', self.multiworld.seed)}",
            "",
        ]
        for player in sorted(self.identity_map):
            info: dict[str, str] = self.identity_map[player]
            lines.append(f"  {info['server_slot']} ({info['server_game']}) "
                         f"is really {info['slot']} ({info['game']})")
        if self.untouched_slots:
            lines.append("")
            lines.append("Untouched slots (not managed by Mystery — connect directly):")
            for slot_name in sorted(self.untouched_slots):
                lines.append(f"  {slot_name} ({self.untouched_slots[slot_name]})")
        if self.cheese:
            lines.append("  This Mystery slot itself reports as 'Mystery Cheese' "
                         "(rare Easter egg; the client retries automatically).")
        if len(lines) == 3:
            lines.append("  (no renamed slots)")
        return lines

    def _has_cheat_sheet(self) -> bool:
        """Returns: True if cheat sheet has content."""
        return bool(self.identity_map) or bool(self.cheese)

    def write_spoiler(self, spoiler_handle: TextIO) -> None:
        """Input: spoiler_handle. Output: appends cheat sheet."""
        if not self._has_cheat_sheet():
            return
        spoiler_handle.write("\n\n" + "\n".join(self.cheat_sheet_lines()) + "\n")

    def generate_output(self, output_directory: str) -> None:
        """Input: output_directory. Output: writes mini cheat sheet if no spoiler."""
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
        """Input: player id. Returns: server slot name."""
        info: dict[str, str] | None = self.identity_map.get(player)
        if info is not None:
            return info["server_slot"]
        try:
            return str(self.multiworld.player_name[player])
        except Exception:
            return f"Player{player}"

    def fill_slot_data(self) -> dict[str, Any]:
        """Returns: slot_data dict for Mystery Client/proxy."""
        try:
            _expose = bool(self.options.expose_proxied_items.value)
        except Exception:
            _expose = True
        return {
            "mystery_game_counts": dict(getattr(self.options, "game_counts", {}).value or {}),
            "mystery_slot_games": dict(getattr(self.options, "slot_games", {}).value or {}),
            "mystery_anonymous": int(getattr(self.options, "anonymous_games", 0).value or 0),
            "mystery_scrambled": bool(self.options.scrambled.value),
            "mystery_puzzles": list(self.active_puzzles),
            "mystery_unlock_map": dict(self.unlock_map),
            "mystery_lock_mode": int(self.options.slot_lock_mode.value),
            "mystery_real_slots": dict(self.real_slots),
            "mystery_untouched_slots": dict(self.untouched_slots),
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
            "mystery_nuzlocke": bool(self.options.nuzlocke.value),
            "mystery_nuzlocke_deathlink": int(self.options.nuzlocke_deathlink.value) if hasattr(self.options, "nuzlocke_deathlink") else 0,
            "mystery_nuzlocke_deathlink_modes": dict(self.nuzlocke_deathlink_modes),
            "mystery_nuzlocke_lives": int(self.nuzlocke_lives),
            "mystery_nuzlocke_lives_per_slot": dict(self.nuzlocke_lives_per_slot),
            "mystery_nuzlocke_extra_lives": int(self.nuzlocke_extra_lives),
            "mystery_nuzlocke_extra_distribution": int(self.nuzlocke_extra_distribution),
            "mystery_nuzlocke_extra_assignments": list(self.nuzlocke_extra_assignments),
            "mystery_nuzlocke_shared_lives": bool(self.nuzlocke_shared_lives),
            "mystery_nuzlocke_shared_extra_lives": bool(self.nuzlocke_shared_extra_lives),
            "mystery_game_code_sets": list(self.game_code_sets.keys()),
            "mystery_code_set_slots": dict(self.code_set_slots),
            "mystery_slot_to_code_set": dict(self.slot_to_code_set),
            "mystery_enable_global_bridge": bool(self.enable_global_bridge),
            "mystery_global_bridge_port": int(self.global_bridge_port),
            "mystery_expose_proxied_items": _expose,
            "mystery_cache_prefix": "mystery_cache",
            "mystery_unlocks_prefix": "mystery_unlocks",
            "mystery_nuzlocke_prefix": "mystery_nuzlocke",
            "mystery_stage_at_output": get_current_stage(),
        }

    def modify_multidata(self, multidata: dict[str, Any]) -> None:
        """Input: multidata. Output: injects datapackages for renamed games."""
        try:
            package: Any = multidata.get("datapackage", {})
        except Exception:
            return
        if not isinstance(package, dict):
            return
        injected: int = 0
        for info in self.identity_map.values():
            real_game: str = info.get("game", "")
            hashed_game: str = info.get("server_game", "")
            if real_game and hashed_game and hashed_game not in package and real_game in package:
                try:
                    package[hashed_game] = dict(package[real_game])
                    injected += 1
                except Exception as exc:
                    logger.warning("[Mystery] Cannot inject datapackage for %s: %s", hashed_game, exc)
        if self.cheese and "Mystery Cheese" not in package and self.game in package:
            try:
                package["Mystery Cheese"] = dict(package[self.game])
                injected += 1
            except Exception as exc:
                logger.warning("[Mystery] Cannot inject datapackage for Mystery Cheese: %s", exc)
        if injected:
            dprint("mystery", f"injected {injected} datapackage entr(ies) for renamed games")


def _log_stage(multiworld: MultiWorld, *args: Any) -> None:
    """Input: multiworld. Output: logs current stage."""
    dprint("mystery", f"entering stage {get_current_stage()}")


for _stage in ("generate_early", "create_regions", "create_items", "set_rules", "pre_fill", "post_fill"):
    try:
        on_stage(_stage, _log_stage)
    except Exception:
        pass

dprint("init", f"mystery_game world loaded ({len(PUZZLE_ROSTER)} puzzles, "
               f"{len(MysteryGameWorld.item_name_to_id)} items, "
               f"{len(MysteryGameWorld.location_name_to_id)} locations)")
