# Copyright (c) 2022 FelicitusNeko
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from dataclasses import dataclass
from Options import Toggle, OptionSet, OptionList, Range, PerGameCommonOptions, OptionGroup, DeathLink, FreeText
from .Items import FNFBaseList


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


class UnlockType(OptionSet):
    """The way you wish to unlock songs."""
    display_name = "Unlock Type"
    valid_keys = ["Per Song", "Per Week"]
    default = "Per Song"


class UnlockMethod(OptionSet):
    """The way you wish to get checks."""
    display_name = "Check Method"
    valid_keys = ["Note Checks", "Song Completion", "Both"]
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

class gradeNeeded(OptionList):
    """The percentage of tickets in the item pool that are needed to unlock the winning song."""
    valid_keys = ["Any", "MFC", "SFC", "GFC", "AFC", "FC", "SDCB"]
    default = "Any"
    display_name = "Grade Required"

class accuracyNeeded(OptionList):
    """The percentage of tickets in the item pool that are needed to unlock the winning song."""
    valid_keys = ["Any", "P", "X", "X-", "SS+", "SS", "SS-", "S+", "S", "S-", "A+", "A", "A-", "B", "C", "D", "E",]
    default = "Any"
    display_name = "Grade Required"

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
