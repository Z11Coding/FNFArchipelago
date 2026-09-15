from __future__ import annotations

"""Options for Mystery Game: YAML contract for game/slot counts and lock modes."""

from dataclasses import dataclass
from typing import Any

from Options import Choice, Option, OptionDict, OptionGroup, OptionSet, PerGameCommonOptions, Range, Toggle

from worlds.APAPI.options_api import FlexibleRange


class GameCountMap(OptionDict):
    """How many slots to create for each game.

    Each entry creates that many slots with creative automatic names. The first
    of a game is usually just its compact name (no trailing '1', usually no
    spaces, e.g. "TUNIC" or "SOH" for Ship of Harkinian), later ones are
    leet/acronym variations with a minimal numeric suffix and no space
    (e.g. "TUN1C", "TUNIC2", "S0H", "SOH2"). The name is always <=16 chars.
    Example: {"TUNIC": 2, "Celeste 64": 1} might add "TUNIC", "TUN1C" and a Celeste slot.
    Use Slot Game Map if you need an exact name.
    """

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
    """Create specific named slots for specific games.

    The key is the exact slot name you want to see in the lobby, the value is the game it will be.
    Example: {"My Tunic Run": "TUNIC"} creates a slot named "My Tunic Run" that will be TUNIC.
    Slot names must be 16 characters or less or the website will reject the seed.
    """

    display_name = "Slot Game Map"
    default = {}
    supports_weighting = False

    def verify(self, world: Any, player_name: str, plando_options: Any) -> None:
        from worlds.AutoWorld import AutoWorldRegister

        for slot_name, game in dict(self.value).items():
            if game not in AutoWorldRegister.world_types:
                raise ValueError(f"Unknown game {game!r} for slot {slot_name!r} ({player_name}).")
            if len(slot_name) > 16:
                raise ValueError(f"Slot name {slot_name!r} for game {game!r} is too long (must be <= 16 characters).")


class AnonymousGameCount(Option[int]):
    """Add this many slots where the game is chosen completely at random.

    The game is picked from all installed games, respecting your Filtered Games setting.
    Useful for chaotic or surprise seeds.
    """

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
    """Hide what Mystery created until you unlock it.

    When enabled, both the slot names and game names of Mystery-created slots are scrambled
    on the server. You must use the Mystery Client to discover what they really are.
    """

    display_name = "Scrambled Slots"
    default = False


class GameOptions(OptionDict):
    """Change options for every Mystery-created slot of a given game.

    Applies the same overrides to all slots of that game.
    Example: {"TUNIC": {"hexagon_quest": true}} enables hexagon quest for every TUNIC slot.
    """

    display_name = "Per-Game Option Overrides"
    default = {}

    def verify(self, world: Any, player_name: str, plando_options: Any) -> None:
        for game, opts in dict(self.value).items():
            if not isinstance(opts, dict):
                raise ValueError(f"Options for {game!r} must be a mapping, got {opts!r}.")


class SlotOptions(OptionDict):
    """Change options for one specific slot by its exact name.

    This beats the per-game overrides above.
    Example: {"TUNIC 1": {"hexagon_goal": 10}} changes only the slot named "TUNIC 1".
    """

    display_name = "Per-Slot Option Overrides"
    default = {}

    def verify(self, world: Any, player_name: str, plando_options: Any) -> None:
        for slot, opts in dict(self.value).items():
            if not isinstance(opts, dict):
                raise ValueError(f"Options for {slot!r} must be a mapping, got {opts!r}.")


class PuzzleCount(Range):
    """How many puzzle checks the Mystery slot itself will have.

    Each puzzle is a location you can check once you collect its pieces.
    Set to 0 to play with no puzzles and focus only on slot locks.
    """

    display_name = "Puzzle Checks"
    range_start = 0
    range_end = 64
    default = 0


class PiecesPerPuzzle(Range):
    """How many pieces you need to collect before a puzzle can be solved.

    Pieces are placed in your item pool. Set to 0 to make every puzzle solvable immediately.
    """

    display_name = "Pieces Per Puzzle"
    range_start = 0
    range_end = 8
    default = 3


class EnableUnlocks(Toggle):
    """Enable slot-unlock items and checks.

    When on, Mystery creates an "Unlock Slot X" item for each hidden slot.
    Finding "Unlock Check: Slot N" gives you the key that makes that game's locations reachable.
    """

    display_name = "Enable Slot Unlocks"
    default = True


class StartingSlots(FlexibleRange):
    """How many Mystery-created slots start unlocked and playable right away.

    Mystery picks them at random. Only applies to mystery-only seeds (no pre-existing slots)
    unless Allow Starting Slots With Others is enabled.
    You can set this above 5, but it will warn you first since it makes the seed easier.
    """

    display_name = "Starting Slots"
    range_start = 1
    range_end = 5
    default = 1
    allow_below_range = False
    allow_above_range = True
    needs_confirmation = False


class AllowUnlockWithOthers(Toggle):
    """Allow unlocking slots even when there are non-Mystery slots in the multiworld.

    When enabled, Mystery will still create and randomize starting unlocked slots even if
    there are other human players (non-controlled slots) in the seed. This allows Mystery
    to act as a player's own game rather than just a meta-game, letting them start with
    one of their own games. When disabled (default), starting slots only apply to
    mystery-only seeds.
    """

    display_name = "Allow Starting Slots With Others"
    default = False


class UnlockPerSet(Toggle):
    """Randomize and unlock per set instead of per slot.

    When enabled and Game Code Sets are used, starting_slots and slot randomization
    treat each code set as a single player. For example, if you have 3 sets each with
    2 slots and starting_slots is 1, it will unlock 1 entire set (2 slots) instead of
    1 individual slot. When disabled (default), randomization is per individual slot.
    Only matters when Game Code Sets are used.
    """

    display_name = "Unlock Per Set (not per slot)"
    default = False


class SlotLockMode(Choice):
    """How hidden slots stay locked until you unlock them.

    - off: Everything is playable immediately (scramble can still hide names).
    - frozen: You can connect, but checks and items are held on the server until you unlock.
    - guess the game: You must type the correct game name with !mystery_guess to unlock.
    - both: You need both the unlock item and a correct guess.
    """

    display_name = "Slot Lock Mode"
    option_off = 0
    option_frozen = 1
    option_guess_the_game = 2
    option_both = 3
    default = 0


class FilteredGames(OptionSet):
    """Games to keep out of random picks.

    By default this is a blacklist — any game in this list will never be randomly chosen.
    Turn on "Filtered Games as Whitelist" to flip this into a whitelist where only these games can be chosen.
    Example: ["Hytale", "SoE"] blocks those two games.
    """

    display_name = "Filtered Games"
    default = frozenset()


class FilteredGamesAsWhitelist(Toggle):
    """Treat Filtered Games as a whitelist instead of a blacklist.

    When on, only the games listed in Filtered Games are allowed.
    When off (default), the listed games are the only ones that are blocked.
    """

    display_name = "Filtered Games as Whitelist"
    default = False


class RandomOptions(Toggle):
    """Randomize any option you didn't set yourself.

    When on, every option not covered by a preset or your per-game / per-slot overrides
    will be set to a random valid value, if that option normally supports "random".
    """

    display_name = "Randomize Remaining Options"
    default = False


class RandomSetOptions(Toggle):
    """Also randomize set / list options that have a fixed list of choices.

    Many games have options like "excluded locations" that are a set of valid names.
    When this is on together with Randomize Remaining Options, Mystery will pick a random
    subset of those valid names (random count and random entries) instead of leaving them empty.
    """

    display_name = "Randomize Set Options"
    default = False


class NuzlockeMode(Toggle):
    """Enable Nuzlocke for Mystery slots.

    When a Mystery-created slot that is currently connected sends a DeathLink
    (your game died), its proxy relay is permanently closed. You can never
    reconnect that slot in this multiworld, and the death is saved to the server
    so it stays dead even if you close and reopen the client. Use this for true
    Nuzlocke runs where one death = that slot is done.
    """

    display_name = "Nuzlocke Mode"
    default = False


class NuzlockeDeathLink(Choice):
    """What happens to the DeathLink itself when Nuzlocke kills a slot.

    Only matters when Nuzlocke Mode is on.

    - normal: The DeathLink is sent normally to everyone with DeathLink enabled, then the dead slot's relay closes.
    - suppress: The DeathLink is not sent to anyone at all. The slot just silently dies and closes.
    - isolate: The DeathLink is only sent to slots Mystery didn't create (your pre-existing slots). This keeps other Mystery slots safe if the dying game has a broken DeathLink that echoes a received DeathLink as a new one and would otherwise wipe itself out in the process.
    Most hosts can leave this on normal. Use suppress or isolate only if a specific game in your pool is known to have a busted DeathLink.
    This can also be configured per-game via its own yaml file.
    """

    display_name = "Nuzlocke DeathLink"
    option_normal = 0
    option_suppress = 1
    option_isolate = 2
    default = 0


class ExposeProxiedItemNames(Toggle):
    """Allow games connecting via Mystery's proxy to see real item names.

    When enabled, the proxy's RoomInfo will expose the underlying game's
    datapackage checksums so game client shows 'Progressive Sword'
    instead of a placeholder. The items were always routed correctly; only the
    name table was hidden. Disable this if you want proxied games to stay
    blind to item names (IDs only) for extra mystery.
    """

    display_name = "Expose Proxied Item Names"
    default = True


class EnableGlobalBridge(Toggle):
    """Enable the global server bridge (separate port, for host broadcast).

    When enabled, Mystery starts an extra WebSocket listener on
    `global_bridge_port` (default 11330) that acts as a proper AP bridge:
    it does NOT connect to the Archipelago server itself until a game
    sends `Connect`. Each game `Connect` is then translated (hashed
    identities, lock checks, datapackage) and bridged to the real AP
    server, allowing MULTIPLE slots to share the same public endpoint.
    Use this with a localhost broadcast service (playit.gg / ngrok /
    bore) to expose your local Mystery proxy online without port-forwarding
    and without giving out the Mystery APWorld. Leave off for direct
    local connect via the normal proxy (`11318`).
    Global only (host broadcast).
    """

    display_name = "Enable Global Bridge"
    default = False


class GlobalBridgePort(Range):
    """Port for the global bridge listener (only when Enable Global Bridge is on).

    Use a high port that does not conflict with the normal proxy (11318)
    and per-slot ports (11319+). 11400 is outside the per-slot range
    (11319-11350 for 32 slots). Change if busy. Host broadcast services
    should tunnel this port (e.g., playit.gg / ngrok tcp 11400).
    """

    display_name = "Global Bridge Port"
    range_start = 1024
    range_end = 65535
    default = 11400


class NuzlockeLives(FlexibleRange):
    """How many lives a Nuzlocke slot has before it is permanently killed.

    Each time the slot sends a DeathLink, one life is lost. The relay is
    only closed when lives reach 0, and the remaining lives are saved to the
    server so they persist across reconnects. Set to 1 for classic one-shot
    Nuzlocke. You can set above 5 (FlexibleRange) if you want extra buffer.
    Only matters when Nuzlocke Mode is enabled. Can also be set per-game via
    its own yaml (mystery_nuzlocke_lives).
    """

    display_name = "Nuzlocke Lives"
    range_start = 1
    range_end = 5
    default = 1
    allow_below_range = False
    allow_above_range = True
    needs_confirmation = False


# Per-game override so individual games can declare their own broken-DeathLink preference.
# This is the same choice as above, but injected into every game via APAPI.
# When Mystery creates a slot for a game, if its own Nuzlocke DeathLink above is not
# "normal", Mystery will also set this per-game option for that generated slot so its
# slot_data visibly shows what was chosen. Game authors can also set this directly
# in their own yaml if they know their DeathLink echoes.
MysteryNuzlockeDeathLink = NuzlockeDeathLink
# Per-game lives override – also injected globally. Mystery sets it for generated
# slots when the global lives >1 or per-slot via slot_options.
MysteryNuzlockeLives = NuzlockeLives


class NuzlockeExtraLives(FlexibleRange):
    """How many Extra Life items are added (global setting only).

    Each Extra Life is a useful progression item that grants +1 max life to
    Nuzlocke slots (server-known). When found, the extra life is applied
    according to Extra Lives Distribution. 0 means no extra lives (classic).
    Normal range 0-50, higher allowed via FlexibleRange. Only matters when
    Nuzlocke Mode is enabled; otherwise they are filler.
    """

    display_name = "Extra Lives"
    range_start = 0
    range_end = 50
    default = 0
    allow_below_range = False
    allow_above_range = True
    needs_confirmation = False


class NuzlockeExtraLivesDistribution(Choice):
    """Who benefits when an Extra Life is collected.

    - for_picker: the slot that collected the check that held the Extra Life
      gets the life (if that slot is not a Nuzlocke slot, a random needy
      Nuzlocke slot is chosen).
    - for_all: every Nuzlocke slot gains +1 max life (global).
    - for_specific: each Extra Life is pre-assigned to a specific Nuzlocke
      slot at generation (round-robin), and only that slot benefits when it
      is found, regardless of who finds it.
    Only matters when Extra Lives >0 and Nuzlocke is enabled. Global only.
    """

    display_name = "Extra Lives Distribution"
    option_for_picker = 0
    option_for_all = 1
    option_for_specific = 2
    default = 0


class GameCodeSets(OptionDict):
    """Named mapping of base64-encoded yaml sets for adding games.

    Each key is a set name (e.g., "My Tunic Set"), each value is a base64-encoded
    gzipped yaml or zip containing one or more yaml files. Use the Mystery Code
    Builder in the launcher to generate these codes from single yaml, multiple
    yamls, or a zip. The generator will copy the code to clipboard and/or save
    as a text file. At generation, each set is decoded and its slots are added
    as if they were in slot_games/game_counts. Slot names from the same set
    share a lives pool if Nuzlocke Shared Lives is enabled.
    """

    display_name = "Game Code Sets"
    default = {}
    supports_weighting = False

    def verify(self, world: Any, player_name: str, plando_options: Any) -> None:
        import base64
        import gzip
        import io
        import zipfile
        from Utils import parse_yaml
        from worlds.AutoWorld import AutoWorldRegister
        for set_name, code in dict(self.value).items():
            if not isinstance(set_name, str) or not set_name.strip():
                raise ValueError(f"Game code set name must be a non-empty string for {player_name}.")
            if not isinstance(code, str) or not code.strip():
                raise ValueError(f"Game code for set {set_name!r} must be a non-empty base64 string for {player_name}.")
            # Full validation: base64 -> gzip -> yaml(s) -> game/slot
            try:
                decoded = base64.b64decode(code.strip(), validate=True)
            except Exception as exc:
                raise ValueError(f"Game code for set {set_name!r} is not valid base64 for {player_name}: {exc}") from exc
            # Try to decode as gzipped content
            decompressed = None
            is_gzipped = False
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(decoded)) as f:
                    decompressed = f.read()
                is_gzipped = True
            except Exception:
                decompressed = None
                is_gzipped = False
            
            yaml_contents: list[str] = []
            if is_gzipped and decompressed is not None:
                # Check if it's a zip
                if decompressed[:4] == b'PK\x03\x04':
                    try:
                        with zipfile.ZipFile(io.BytesIO(decompressed)) as zf:
                            for zi in zf.infolist():
                                if zi.is_dir() or not zi.filename.lower().endswith(('.yaml', '.yml')):
                                    continue
                                try:
                                    yaml_content = zf.read(zi).decode('utf-8-sig')
                                    yaml_contents.append(yaml_content)
                                except Exception as exc:
                                    raise ValueError(f"Failed to read zip entry {zi.filename!r} in game code set {set_name!r} for {player_name}: {exc}") from exc
                            if not yaml_contents:
                                raise ValueError(f"Zip in game code set {set_name!r} contains no yaml files for {player_name}")
                    except zipfile.BadZipFile as exc:
                        raise ValueError(f"Invalid zip in game code set {set_name!r} for {player_name}: {exc}") from exc
                else:
                    # Gzipped yaml(s)
                    try:
                        yaml_content = decompressed.decode('utf-8-sig')
                        yaml_contents.append(yaml_content)
                    except Exception as exc:
                        raise ValueError(f"Failed to decode gzipped yaml in game code set {set_name!r} for {player_name}: {exc}") from exc
            else:
                # Plain base64 yaml (not gzipped)
                try:
                    yaml_content = decoded.decode('utf-8-sig')
                    yaml_contents.append(yaml_content)
                except Exception as exc:
                    raise ValueError(f"Failed to decode plain yaml in game code set {set_name!r} for {player_name}: {exc}") from exc
            
            # Now validate each yaml content
            for yaml_content in yaml_contents:
                # Handle multiple docs with ---
                docs: list[str] = []
                if "---" in yaml_content:
                    current = []
                    for line in yaml_content.splitlines():
                        if line.strip() == "---":
                            if current:
                                docs.append('\n'.join(current))
                                current = []
                        else:
                            current.append(line)
                    if current:
                        docs.append('\n'.join(current))
                else:
                    docs = [yaml_content]
                
                for doc_content in docs:
                    doc_content = doc_content.strip()
                    if not doc_content:
                        continue
                    try:
                        parsed = parse_yaml(doc_content)
                    except Exception as exc:
                        raise ValueError(f"Invalid yaml in game code set {set_name!r} for {player_name}: {exc}") from exc
                    if not isinstance(parsed, dict):
                        raise ValueError(f"Invalid yaml structure in game code set {set_name!r} for {player_name}: expected dict")
                    yaml_game = parsed.get('game')
                    yaml_name = parsed.get('name')
                    if not isinstance(yaml_name, str) or not yaml_name.strip():
                        raise ValueError(f"Missing or invalid 'name' in yaml for game code set {set_name!r} for {player_name}")
                    if not isinstance(yaml_game, str) or not yaml_game.strip():
                        raise ValueError(f"Missing or invalid 'game' in yaml for game code set {set_name!r} for {player_name} name {yaml_name!r}")
                    game_name = str(yaml_game).strip()
                    if game_name == "Mystery Game":
                        raise ValueError(f"Game code set {set_name!r} contains a Mystery Game yaml (name {yaml_name!r}) for {player_name} - not allowed")
                    if game_name not in AutoWorldRegister.world_types:
                        raise ValueError(f"Unknown game {game_name!r} in game code set {set_name!r} for {player_name} name {yaml_name!r}")
                    slot_name = yaml_name.strip()
                    if len(slot_name) > 16:
                        raise ValueError(f"Slot name {slot_name!r} in game code set {set_name!r} for {player_name} is {len(slot_name)} chars; max is 16")


class NuzlockeSharedLives(Toggle):
    """Make slots from the same Game Code set share lives.

    When enabled, all slots that came from the same base64 Game Code set share
    a single lives pool in Nuzlocke mode. A hit on any slot in the set reduces
    lives for the whole set, and the set dies together. When disabled, each slot
    has its own lives as per Nuzlocke Lives. Only matters when Nuzlocke is enabled
    and Game Code Sets are used.
    """

    display_name = "Nuzlocke Shared Lives (per set)"
    default = False


class NuzlockeSharedExtraLives(Toggle):
    """Make Extra Lives shared per Game Code set.

    When enabled, Extra Lives with distribution for_picker or for_specific will
    give the life to the whole set that the picker or assigned slot belongs to,
    rather than just the single slot. for_all remains global. Only matters when
    Nuzlocke is enabled, Extra Lives >0, and Game Code Sets are used.
    """

    display_name = "Nuzlocke Shared Extra Lives (per set)"
    default = False


@dataclass
class MysteryGameOptions(PerGameCommonOptions):
    game_counts: GameCountMap
    slot_games: SlotGameMap
    anonymous_games: AnonymousGameCount
    scrambled: Scrambled
    puzzle_count: PuzzleCount
    pieces_per_puzzle: PiecesPerPuzzle
    enable_unlocks: EnableUnlocks
    starting_slots: StartingSlots
    allow_unlock_with_others: AllowUnlockWithOthers
    unlock_per_set: UnlockPerSet
    slot_lock_mode: SlotLockMode
    filtered_games: FilteredGames
    filtered_games_as_whitelist: FilteredGamesAsWhitelist
    random_options: RandomOptions
    random_set_options: RandomSetOptions
    nuzlocke: NuzlockeMode
    nuzlocke_deathlink: NuzlockeDeathLink
    nuzlocke_lives: NuzlockeLives
    nuzlocke_extra_lives: NuzlockeExtraLives
    nuzlocke_extra_distribution: NuzlockeExtraLivesDistribution
    nuzlocke_shared_lives: NuzlockeSharedLives
    nuzlocke_shared_extra_lives: NuzlockeSharedExtraLives
    game_code_sets: GameCodeSets
    expose_proxied_items: ExposeProxiedItemNames
    enable_global_bridge: EnableGlobalBridge
    global_bridge_port: GlobalBridgePort
    game_options: GameOptions
    slot_options: SlotOptions


mystery_option_groups = [
    OptionGroup("Mystery Setup", [
        GameCountMap,
        SlotGameMap,
        AnonymousGameCount,
        GameCodeSets,
        Scrambled,
        FilteredGames,
        FilteredGamesAsWhitelist,
    ]),
    OptionGroup("Direct Options", [
        GameOptions,
        SlotOptions,
    ]),
    OptionGroup("Puzzles & Unlocks", [
        PuzzleCount,
        PiecesPerPuzzle,
        EnableUnlocks,
        StartingSlots,
        AllowUnlockWithOthers,
        UnlockPerSet,
        SlotLockMode,
    ]),
    OptionGroup("Proxy", [
        ExposeProxiedItemNames,
        EnableGlobalBridge,
        GlobalBridgePort,
    ]),
    OptionGroup("Random Options", [
        RandomOptions,
        RandomSetOptions,
    ]),
    OptionGroup("Nuzlocke", [
        NuzlockeMode,
        NuzlockeDeathLink,
        NuzlockeLives,
        NuzlockeExtraLives,
        NuzlockeExtraLivesDistribution,
        NuzlockeSharedLives,
        NuzlockeSharedExtraLives,
    ]),
]
