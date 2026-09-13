from __future__ import annotations

"""Options specific to the Mystery Game world.

These live here — not in APAPI — because they describe Mystery Game's own
YAML contract (game-count map, slot->game map, anonymous count, scramble
toggle). APAPI stays game-agnostic; it only offers the generic
``VariantOption`` base for worlds that want multi-shape options.
"""

from dataclasses import dataclass
from typing import Any

from Options import Choice, Option, OptionDict, OptionGroup, PerGameCommonOptions, Range, Toggle


class GameCountMap(OptionDict):
    """``{game_name: count}`` map, e.g. ``{"TUNIC": 2}``."""

    display_name = "Game Counts"
    default = {}
    supports_weighting = False

    def verify(self, world: Any, player_name: str, plando_options: Any) -> None:
        from worlds.AutoWorld import AutoWorldRegister

        for game, count in dict(self.value).items():
            if game not in AutoWorldRegister.world_types:
                raise ValueError(f"Unknown game {game!r} for {player_name}.")
            if not isinstance(count, int) or count < 0:
                raise ValueError(f"Count for {game!r} must be a non-negative int.")


class SlotGameMap(OptionDict):
    """``{slot_name: game_name}`` map for explicit slot setup."""

    display_name = "Slot Game Map"
    default = {}
    supports_weighting = False

    def verify(self, world: Any, player_name: str, plando_options: Any) -> None:
        from worlds.AutoWorld import AutoWorldRegister

        for slot_name, game in dict(self.value).items():
            if game not in AutoWorldRegister.world_types:
                raise ValueError(f"Unknown game {game!r} for slot {slot_name!r} ({player_name}).")


class AnonymousGameCount(Option[int]):
    """Plain int: number of anonymous games to generate."""

    display_name = "Anonymous Game Count"
    default = 0

    def __init__(self, value: int) -> None:
        self.value = int(value)

    @classmethod
    def from_any(cls, data: Any) -> "AnonymousGameCount":
        return cls(int(data))

    @classmethod
    def get_option_name(cls, value: int) -> str:
        return str(value)

    def verify(self, world: Any, player_name: str, plando_options: Any) -> None:
        if not isinstance(self.value, int) or self.value < 0:
            raise ValueError(f"Anonymous game count must be >= 0 for {player_name}.")


class Scrambled(Toggle):
    """Full scramble: slot names AND games are replaced server-side by hashes.

    Locked slots become unconnectable directly (InvalidSlot/InvalidGame);
    only the proxy, which holds the real map, can resolve them.
    Only the spoiler cheat sheet (or the mini log in the zip) reveals the truth.
    """
    display_name = "Scrambled Slots"
    default = False


class GameOptions(OptionDict):
    """Direct options per game: ``{game: {option: value}}``.

    Applies to every added slot of that game, without preset files.
    """
    display_name = "Per-Game Option Overrides"
    default = {}

    def verify(self, world: Any, player_name: str, plando_options: Any) -> None:
        for game, opts in dict(self.value).items():
            if not isinstance(opts, dict):
                raise ValueError(f"Options for {game!r} must be a mapping, got {opts!r}.")


class SlotOptions(OptionDict):
    """Direct options per slot: ``{slot: {option: value}}``. Wins over game options."""

    display_name = "Per-Slot Option Overrides"
    default = {}

    def verify(self, world: Any, player_name: str, plando_options: Any) -> None:
        for slot, opts in dict(self.value).items():
            if not isinstance(opts, dict):
                raise ValueError(f"Options for {slot!r} must be a mapping, got {opts!r}.")


class PuzzleCount(Range):
    """How many puzzle checks this Mystery slot gets (0 disables; puzzles
    are deferred for now while slot locks are the focus)."""
    display_name = "Puzzle Checks"
    range_start = 0
    range_end = 64
    default = 0


class PiecesPerPuzzle(Range):
    """Required pieces per puzzle (0 = solve freely). Piece items enter the
    pool for this slot; the client gates solving until all are held."""
    display_name = "Pieces Per Puzzle"
    range_start = 0
    range_end = 8
    default = 3


class EnableUnlocks(Toggle):
    """Add 'Unlock Slot' locations holding the items that reveal/progress locked slots."""
    display_name = "Enable Slot Unlocks"
    default = True


class SlotLockMode(Choice):
    """How locked slots behave. In EVERY lock mode each other slot's game is
    replaced server-side by an unpredictable chained-hash name (salted per
    seed, slot, and items sent there), so direct connection is impossible
    and only the proxy can resolve them. Slot names are hashed too on full
    scramble. Items owned by renamed slots carry the hashed game as well.

    Off: slots play normally (no renaming unless Scrambled).
    Frozen: slots connect but the Mystery proxy holds ALL traffic both ways
    until unlocked; checks pile up in server-side cached_checks per slot.
    Guess the Game: like Frozen, but unlocks come from naming the slot's
    game (!mystery_guess) instead of items. Pairs with Scrambled Slots.
    Both: frozen traffic with unlocks from items AND guesses.
    """
    display_name = "Slot Lock Mode"
    option_off = 0
    option_frozen = 1
    option_guess_the_game = 2
    option_both = 3
    default = 0


@dataclass
class MysteryGameOptions(PerGameCommonOptions):
    game_counts: GameCountMap
    slot_games: SlotGameMap
    anonymous_games: AnonymousGameCount
    scrambled: Scrambled
    puzzle_count: PuzzleCount
    pieces_per_puzzle: PiecesPerPuzzle
    enable_unlocks: EnableUnlocks
    slot_lock_mode: SlotLockMode
    game_options: GameOptions
    slot_options: SlotOptions


mystery_option_groups = [
    OptionGroup("Mystery Setup", [
        GameCountMap,
        SlotGameMap,
        AnonymousGameCount,
        Scrambled,
    ]),
    OptionGroup("Direct Options", [
        GameOptions,
        SlotOptions,
    ]),
    OptionGroup("Puzzles & Unlocks", [
        PuzzleCount,
        PiecesPerPuzzle,
        EnableUnlocks,
        SlotLockMode,
    ]),
]
