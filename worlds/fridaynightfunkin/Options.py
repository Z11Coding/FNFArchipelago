# Copyright (c) 2022 FelicitusNeko
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from dataclasses import dataclass
from Options import Toggle, OptionSet, Range, PerGameCommonOptions, OptionGroup, DeathLink
from Items import FNFBaseList
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
    valid_keys = [song for song in FNFBaseList.baseSongs]
    default = "Tutorial"

class UnlockType(OptionSet):
    """The way you wish to unlock songs."""
    display_name = "Unlock Type"
    valid_keys = ["Per Song", "Per Week"]
    default = "Per Song"


class UnlockMethod(OptionSet):
    """The way you wish to get checks."""
    display_name = "Check Method"
    valid_keys = ["Note Checks", "Song Completion"]
    default = "Note Checks"

class songList(OptionSet):
    """The list of songs that will be added to the game"""
    display_name = "Song List"
    valid_keys = []
    default = []

class trapAmount(Range):
    """The list of songs that will be added to the game"""
    display_name = "Trap Weight"
    range_start = 0
    range_end = 1367
    default = 15

class bbcWeight(Range):
    """The amount of BBC (haha very funny yuta) in a run"""
    display_name = "Blue Balls Curse Trap Weight"
    range_start = 0
    range_end = 87
    default = 15

class ghostChatWeight(Range):
    """The amount of Ghost Chat Traps in a run"""
    display_name = "Ghost Chat Trap Weight"
    range_start = 0
    range_end = 844
    default = 15

class svcWeight(Range):
    """The amount of Ghost Chat Traps in a run"""
    display_name = "SvC Effect Trap Weight"
    range_start = 0
    range_end = 132
    default = 15

class tutorialWeight(Range):
    """The amount of Tutorial Traps in a run"""
    display_name = "Tutorial Trap Weight"
    range_start = 0
    range_end = 369
    default = 15

class fakeTransWeight(Range):
    """The amount of Fake Transition Traps in a run"""
    display_name = "Fake Transition Trap Weight"
    range_start = 0
    range_end = 38
    default = 15

class shieldWeight(Range):
    """The amount of Shield in a run"""
    display_name = "Shield Item Weight"
    range_start = 0
    range_end = 38
    default = 15

class MHPWeight(Range):
    """The amount of Shield in a run"""
    display_name = "Max HP Up Item Weight"
    range_start = 0
    range_end = 38
    default = 15

class ChartModChangeChance(Range):
    """
        The amount of times you'll get a Chart Modifier Trap.
    """
    display_name = "Chart Modifier Trap Count"
    range_start = 0
    range_end = 18
    default = 15

option_groups = [
    OptionGroup("Base Settings", [
        AllowMods,
        SongStarter,
        UnlockType,
        UnlockMethod,
        songList,
        DeathLink
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
    allow_mods: AllowMods
    starting_songs: SongStarter
    chart_modifier_change_chance: ChartModChangeChance
    unlock_type: UnlockType
    unlock_method: UnlockMethod
    songList: songList
    trapAmount: trapAmount
    trapAmount: trapAmount