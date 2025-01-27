# Copyright (c) 2022 FelicitusNeko
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from dataclasses import dataclass
from Options import Toggle, OptionSet, OptionList, Range, PerGameCommonOptions, OptionGroup, DeathLink
from .Items import FNFBaseList


class AllowMods(Toggle):
    """Enables the ability to use mods for your run.
    (Should be kept off if you don't have any mods.)
    """
    display_name = "Enable Mods"
    default = False


class SongStarter(OptionSet):
    """The song you wish to start with.
    (Tutorial is recommended, but not required.
    Any song will work. Or none at all if that's your thing.)"""
    display_name = "Starting Songs"
    valid_keys = [song for song in FNFBaseList.baseSongList]
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
    default = "Note Checks"


class songList(OptionList):
    """The list of songs that will be added to the game"""
    display_name = "Song List"
    default = FNFBaseList.baseSongList.copy()


class trapAmount(Range):
    """The amount of traps that will be added to the game"""
    display_name = "Trap Weight"
    range_start = 0
    range_end = 60
    default = 10


class bbcWeight(Range):
    """The amount of BBC (haha very funny yuta) in a run"""
    display_name = "Blue Balls Curse Trap Weight"
    range_start = 0
    range_end = 10
    default = 10


class ghostChatWeight(Range):
    """The amount of Ghost Chat Traps in a run"""
    display_name = "Ghost Chat Trap Weight"
    range_start = 0
    range_end = 10
    default = 10


class svcWeight(Range):
    """The amount of Ghost Chat Traps in a run"""
    display_name = "SvC Effect Trap Weight"
    range_start = 0
    range_end = 10
    default = 10


class tutorialWeight(Range):
    """The amount of Tutorial Traps in a run"""
    display_name = "Tutorial Trap Weight"
    range_start = 0
    range_end = 10
    default = 10


class fakeTransWeight(Range):
    """The amount of Fake Transition Traps in a run"""
    display_name = "Fake Transition Trap Weight"
    range_start = 0
    range_end = 10
    default = 10


class shieldWeight(Range):
    """The amount of Shield in a run"""
    display_name = "Shield Item Weight"
    range_start = 0
    range_end = 10
    default = 10


class MHPWeight(Range):
    """The amount of Shield in a run"""
    display_name = "Max HP Up Item Weight"
    range_start = 0
    range_end = 10
    default = 10


class ChartModChangeChance(Range):
    """
        The amount of times you'll get a Chart Modifier Trap.
    """
    display_name = "Chart Modifier Trap Count"
    range_start = 0
    range_end = 10
    default = 10


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


fnf_option_groups = [
    OptionGroup("Base Settings", [
        AllowMods,
        SongStarter,
        UnlockType,
        UnlockMethod,
        songList,
        DeathLink,
        TicketPercentage,
        TicketWinPercentage,
        gradeNeeded,
        accuracyNeeded
    ]),
    OptionGroup("Traps", [
        trapAmount,
        bbcWeight,
        ghostChatWeight,
        svcWeight,
        tutorialWeight,
        fakeTransWeight,
        shieldWeight,
        MHPWeight,
        ChartModChangeChance
    ]),
]


@dataclass
class FunkinOptions(PerGameCommonOptions):
    mods_enabled: AllowMods
    starting_song: SongStarter
    chart_modifier_change_chance: ChartModChangeChance
    unlock_type: UnlockType
    unlock_method: UnlockMethod
    songList: songList
    trapAmount: trapAmount
    bbcWeight: bbcWeight
    ghostChatWeight: ghostChatWeight
    svcWeight: svcWeight
    tutorialWeight: tutorialWeight
    fakeTransWeight: fakeTransWeight
    shieldWeight: shieldWeight
    MHPWeight: MHPWeight
    deathlink: DeathLink
    ticket_percentage: TicketPercentage
    ticket_win_percentage: TicketWinPercentage
    graderequirement: gradeNeeded
    accrequirement: accuracyNeeded
