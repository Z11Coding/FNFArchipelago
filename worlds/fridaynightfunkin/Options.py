# Copyright (c) 2022 FelicitusNeko
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from dataclasses import dataclass
from Options import Toggle, TextChoice, OptionList, Range, PerGameCommonOptions, OptionGroup, DeathLink, FreeText, OptionError
from .Items import FNFBaseList


class VerifiedTextChoice(TextChoice):
    """A TextChoice that requires valid_keys to be defined and validates against them.
    Automatically initializes the options dictionary from valid_keys with integer IDs.
    Accepts both string and integer values."""
    valid_keys: set = set()
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Build options dictionary from valid_keys with integer IDs
        if hasattr(cls, 'valid_keys') and cls.valid_keys:
            sorted_keys = sorted(cls.valid_keys)
            cls.options = {key.lower(): i for i, key in enumerate(sorted_keys)}
            # Build reverse mapping for integer to key lookup
            cls._reverse_options = {i: key for i, key in enumerate(sorted_keys)}
    
    def __init__(self, value):
        if not self.__class__.valid_keys:
            raise OptionError(f"{self.__class__.__name__} must define valid_keys")
        
        # If value is an integer, convert to the corresponding key string
        if isinstance(value, int):
            if hasattr(self.__class__, '_reverse_options') and value in self.__class__._reverse_options:
                value = self.__class__._reverse_options[value]
            else:
                # Build error message with valid range and mappings
                if hasattr(self.__class__, '_reverse_options'):
                    max_int = len(self.__class__._reverse_options) - 1
                    mapping = ', '.join(f'{i}: "{self.__class__._reverse_options[i]}"' 
                                      for i in range(len(self.__class__._reverse_options)))
                    raise OptionError(f"Invalid integer value {value} for {self.__class__.__name__}. "
                                    f"Valid range is 0-{max_int}: {mapping}")
                else:
                    raise OptionError(f"Invalid integer value {value} for {self.__class__.__name__}")
        
        super().__init__(value)
    
    def verify(self, *args, **kwargs) -> None:
        if self.value not in self.valid_keys:
            # Build error message with valid range and mappings
            if hasattr(self.__class__, '_reverse_options'):
                max_int = len(self.__class__._reverse_options) - 1
                mapping = ', '.join(f'{i}: "{self.__class__._reverse_options[i]}"' 
                                  for i in range(len(self.__class__._reverse_options)))
                raise OptionError(f"Invalid value '{self.value}' for {self.__class__.__name__}. "
                                f"Valid range is 0-{max_int}: {mapping}")
            else:
                raise OptionError(f"Invalid value '{self.value}' for {self.__class__.__name__}. "
                                f"Valid options are: {', '.join(sorted(self.valid_keys))}")
    
    def get_int_value(self) -> int:
        """Get the integer index of the current option."""
        return self.__class__.options[self.value.lower()]
    
    def get_string_value(self) -> str:
        """Get the string key of the current option."""
        return self.value


class AllowMods(Toggle):
    """Enables the ability to use mods for your run.
    (Should be kept off if you don't have any mods.)
    """
    display_name = "Enable Mods"
    default = False


class SongStarter(FreeText):
    """The song you wish to start with."""
    display_name = "Starting Songs"
    default = ""


class UnlockType(VerifiedTextChoice):
    """The way you wish to unlock songs."""
    display_name = "Unlock Type"
    valid_keys = {"Per Song", "Per Week"}
    default = "Per Song"


class UnlockMethod(VerifiedTextChoice):
    """The way you wish to get checks."""
    display_name = "Check Method"
    valid_keys = {"Note Checks", "Song Completion", "Both"}
    default = "Song Completion"

class CheckCount(Range):
    """How many checks a song contains."""
    display_name = "Checks Per Song"
    range_start = 1
    range_end = 3
    default = 1

class songList(OptionList):
    """The list of songs that will be added to the game"""
    display_name = "Song List"
    default = FNFBaseList.baseSongList.copy()


class trapAmount(Range):
    """The amount of traps that will be added to the game"""
    display_name = "Trap Weight"
    range_start = 0
    range_end = 100
    default = 10


class bbcWeight(Range):
    """The amount of BBC (haha very funny yuta) in a run"""
    display_name = "Blue Balls Curse Trap Weight"
    range_start = 0
    range_end = 10
    default = 5


class ghostChatWeight(Range):
    """The amount of Ghost Chat Traps in a run"""
    display_name = "Ghost Chat Trap Weight"
    range_start = 0
    range_end = 10
    default = 5


class svcWeight(Range):
    """The amount of Ghost Chat Traps in a run"""
    display_name = "SvC Effect Trap Weight"
    range_start = 0
    range_end = 10
    default = 5


class tutorialWeight(Range):
    """The amount of Tutorial Traps in a run"""
    display_name = "Tutorial Trap Weight"
    range_start = 0
    range_end = 10
    default = 5


class fakeTransWeight(Range):
    """The amount of Fake Transition Traps in a run"""
    display_name = "Fake Transition Trap Weight"
    range_start = 0
    range_end = 10
    default = 5

class chartModWeight(Range):
    """The amount of Chart Modifier Traps in a run"""
    display_name = "Chart Modifier Trap Weight"
    range_start = 0
    range_end = 10
    default = 5


class shieldWeight(Range):
    """The amount of Shield in a run"""
    display_name = "Shield Item Weight"
    range_start = 0
    range_end = 10
    default = 5


class MHPWeight(Range):
    """The amount of Shield in a run"""
    display_name = "Max HP Up Item Weight"
    range_start = 0
    range_end = 10
    default = 5

class MHPDWeight(Range):
    """The chances of getting a Max HP Down Trap"""
    display_name = "Max HP Down Trap Weight"
    range_start = 0
    range_end = 10
    default = 5

class ExtraLifeWeight(Range):
    """The chances of getting an Extra Life"""
    display_name = "Extra Life Weight"
    range_start = 0
    range_end = 10
    default = 5

class ResistWeight(Range):
    """The chances of having Zenetta sneak up behind and "kill" boyfriend"""
    display_name = "Resistance Trap Weight"
    range_start = 0
    range_end = 10
    default = 5

class UnoWeight(Range):
    """The chances of being forced to play a round of UNO"""
    display_name = "UNO CHALLENGE Trap Weight"
    range_start = 0
    range_end = 10
    default = 5

class PongWeight(Range):
    """The chances of being forced to play a round of PONG"""
    display_name = "Pong CHALLENGE Trap Weight"
    range_start = 0
    range_end = 10
    default = 5

class SongSwitchWeight(Range):
    """The chances of being forced to play a different song and then being returned to the song you were originally playing"""
    display_name = "Song Switch Trap Weight"
    range_start = 0
    range_end = 10
    default = 5

class OpponentWeight(Range):
    """The chances of being forced to play as the opponent instead"""
    display_name = "Opponent Mode Trap Weight"
    range_start = 0
    range_end = 10
    default = 5

class BothWeight(Range):
    """The chances of being forced to play as the opponent AND the player instead"""
    display_name = "Both Play Trap Weight"
    range_start = 0
    range_end = 10
    default = 5

class UltimateConfusionWeight(Range):
    """The chances of never figuring out what song you just selected"""
    display_name = "Ultimate Confusion Trap Weight"
    range_start = 0
    range_end = 10
    default = 5

class TicketPercentage(Range):
    """
    How many tickets you need to collect based on the number of songs.
    Like Muse Dash, Higher numbers leads to more consistent game lengths, but will cause individual music sheets to be less important.
    """
    range_start = 10
    range_end = 50
    default = 30
    display_name = "Ticket Percentage"


class TicketWinPercentage(Range):
    """The percentage of tickets in the item pool that are needed to unlock the winning song."""
    range_start = 50
    range_end = 100
    default = 80
    display_name = "Tickets Needed to Win"

class gradeNeeded(VerifiedTextChoice):
    """The grade needed to win."""
    display_name = "Grade Required"
    valid_keys = {"Any", "MFC", "SFC", "GFC", "AFC", "FC", "SDCB"}
    default = "Any"

class accuracyNeeded(VerifiedTextChoice):
    """The accuracy needed to win."""
    display_name = "Accuracy Required"
    valid_keys = {"Any", "P", "X", "X-", "SS+", "SS", "SS-", "S+", "S", "S-", "A+", "A", "A-", "B", "C", "D", "E"}
    default = "Any"

class songLimit(Range):
    """The percentage of songs in the item pool."""
    range_start = 3
    range_end = 6000000  # This is only this high because there's no way to actually check how many songs there are before the songList is generated.
    default = 16
    display_name = "Song Limit"

class AllowDuplicateSongs(Toggle):
    """If there should be multiple of songs if there's room for them."""
    display_name = "Allow Duplicate Songs"
    default = False

class StarterDebuffs(Toggle):
    """If you want to add 5 debuffs that make the game near impossible to play immediately"""
    display_name = "Starter Debuffs"
    default = False

class PermaTraps(Toggle):
    """If you want to add 5 traps that stick until you get the anti-trap item to get rid of it"""
    display_name = "Perma-Traps"
    default = False

class HardMode(Toggle):
    """If you want to make elements of the game checks so that you don't have them until you get them"""
    display_name = "Hard Mode"
    default = False

class Shop(Toggle):
    """If you want to add the shop mechanic"""
    display_name = "Enable Shop"
    default = False


fnf_option_groups = [
    OptionGroup("Base Settings", [
        AllowMods,
        SongStarter,
        songLimit,
        UnlockType,
        UnlockMethod,
        songList,
        DeathLink,
        TicketPercentage,
        TicketWinPercentage,
        gradeNeeded,
        accuracyNeeded,
        AllowDuplicateSongs
    ]),
    OptionGroup("Traps", [
        trapAmount,
        bbcWeight,
        ghostChatWeight,
        svcWeight,
        MHPDWeight,
        tutorialWeight,
        SongSwitchWeight,
        OpponentWeight,
        BothWeight,
        fakeTransWeight,
        chartModWeight,
        ResistWeight,
        UnoWeight,
        PongWeight,
        UltimateConfusionWeight
    ]),
    OptionGroup("Items", [
        shieldWeight,
        MHPWeight,
        ExtraLifeWeight
    ]),
    OptionGroup("Z11's Optional Hell", [
        StarterDebuffs,
        PermaTraps,
        HardMode,
        Shop
    ]),
]


@dataclass
class FunkinOptions(PerGameCommonOptions):
    mods_enabled: AllowMods
    starting_song: SongStarter
    song_limit: songLimit
    chart_modifier_change_chance: chartModWeight
    unlock_type: UnlockType
    unlock_method: UnlockMethod
    songList: songList
    check_count: CheckCount
    trapAmount: trapAmount
    bbcWeight: bbcWeight
    ghostChatWeight: ghostChatWeight
    svcWeight: svcWeight
    tutorialWeight: tutorialWeight
    songSwitchWeight: SongSwitchWeight
    opponentWeight: OpponentWeight
    bothWeight: BothWeight
    resistanceWeight: ResistWeight
    unoWeight: UnoWeight
    pongWeight: PongWeight
    ultconfusion: UltimateConfusionWeight
    fakeTransWeight: fakeTransWeight
    shieldWeight: shieldWeight
    MHPWeight: MHPWeight
    MHPDWeight: MHPDWeight
    extralifeWeight: ExtraLifeWeight
    deathlink: DeathLink
    ticket_percentage: TicketPercentage
    ticket_win_percentage: TicketWinPercentage
    graderequirement: gradeNeeded
    accrequirement: accuracyNeeded
    allowDupes: AllowDuplicateSongs
    starter_debuffs: StarterDebuffs
    perma_traps: PermaTraps
    hard_mode: HardMode
    shop: Shop
