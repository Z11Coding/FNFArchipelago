# Copyright (c) 2024
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from dataclasses import dataclass
from Options import Toggle, Choice, PerGameCommonOptions, OptionGroup



class AddProgressionItem(Toggle):
    """
    Whether to add a special progression item that links to all required progression items
    from each world in the multiworld. This item grants immediate access to everything.
    """
    display_name = "Add Progression Item"
    default = False


class ProgressionItemType(Choice):
    """
    How the progression item should be distributed:
    - Per World: One item per world that contains that world's required progression items
    - Global: A single item that links to ALL worlds' progression items
    (Not currently fully implemented. Might work, not tested.)
    """
    display_name = "Progression Item Distribution"
    option_per_world = 0
    option_global = 1
    default = 1


class ProgressionItemLocality(Choice):
    """
    Where progression items from other worlds can be placed:
    - local: Each player's progression item can ONLY be placed in that player's own world
    - non_local: Each player's progression item CANNOT be placed in that player's own world (must go elsewhere)
    - anywhere: No restrictions, items can be placed anywhere in the multiworld
    """
    display_name = "Progression Item Locality"
    option_local = 0
    option_non_local = 1
    option_anywhere = 2
    default = 2


class RemoveEntranceLogic(Toggle):
    """
    Whether to remove access rules from entrances (region connections).
    When enabled, all entrance requirements will also be ignored, meaning the seed could be even more impossible than it already is.
    Disable this if you want to keep entrance logic intact while still
    removing location access rules.
    """
    display_name = "Remove Entrance Logic"
    default = True


class RespectEarlyLocations(Toggle):
    """
    Whether to respect early location placement when removing logic.
    When enabled (True), logic removal happens at stage_pre_fill, which runs after
    early location placement has already occurred.
    When disabled (False), logic removal happens at stage_connect_entrances, which
    runs earlier and ignores early location considerations.
    """
    display_name = "Respect Early Locations"
    default = True


class NoProgressionMaze(Toggle):
    """
    RISKY: When enabled, removes the original progression items from the pool and only provides
    the linked progression item. This can make the game unwinnable more often than not.
    Leave disabled for safer gameplay.
    (Not currently implemented.)
    """
    display_name = "No Progression Maze (Risky)"
    default = False


class IncludeLesserProgression(Toggle):
    """
    When enabled, progression item collections will also include items classified as:
    - progression_skip_balancing
    - progression_deprioritized
    - progression_deprioritized_skip_balancing
    """
    display_name = "Include Lesser Progression Items"
    default = False


class AutoHintProgressionItems(Toggle):
    """
    When enabled, progression item locations will be automatically hinted when the game generates.
    This makes it easier to track which world each progression item comes from.
    """
    display_name = "Auto-Hint Progression Items"
    default = False


@dataclass
class NoLogicOptions(PerGameCommonOptions):
    add_progression_item: AddProgressionItem
    progression_item_type: ProgressionItemType
    progression_item_locality: ProgressionItemLocality
    remove_entrance_logic: RemoveEntranceLogic
    respect_early_locations: RespectEarlyLocations
    no_progression_maze: NoProgressionMaze
    include_lesser_progression: IncludeLesserProgression
    auto_hint_progression_items: AutoHintProgressionItems


no_logic_option_groups = [
    OptionGroup("No Logic Options", [
        AddProgressionItem,
        ProgressionItemType,
        ProgressionItemLocality,
        RemoveEntranceLogic,
        RespectEarlyLocations,
        NoProgressionMaze,
        IncludeLesserProgression,
        AutoHintProgressionItems,
    ])
]
