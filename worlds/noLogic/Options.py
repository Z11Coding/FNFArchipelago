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
    (Not currently fully implemented.)
    """
    display_name = "Add Progression Item"
    default = False


class ProgressionItemType(Choice):
    """
    How the progression item should be distributed:
    - Per World: One item per world that contains that world's required progression items
    - Global: A single item that links to ALL worlds' progression items
    (Not currently fully implemented.)
    """
    display_name = "Progression Item Distribution"
    option_per_world = 0
    option_global = 1
    default = 1


class ProgressionItemLocality(Choice):
    """
    Whether progression items from other worlds should be local or non-local:
    - local: Items must go to their original worlds
    - non_local: Items can go anywhere in the multiworld
    (Not currently fully implemented.)

    """
    display_name = "Progression Item Locality"
    option_local = 0
    option_non_local = 1
    default = 1


class RemoveEntranceLogic(Toggle):
    """
    Whether to remove access rules from entrances (region connections).
    When enabled, all entrances in every world become freely accessible.
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
    (Not currently fully implemented.)
    """
    display_name = "No Progression Maze (Risky)"
    default = False


@dataclass
class NoLogicOptions(PerGameCommonOptions):
    add_progression_item: AddProgressionItem
    progression_item_type: ProgressionItemType
    progression_item_locality: ProgressionItemLocality
    remove_entrance_logic: RemoveEntranceLogic
    respect_early_locations: RespectEarlyLocations
    no_progression_maze: NoProgressionMaze


no_logic_option_groups = [
    OptionGroup("No Logic Options", [
        AddProgressionItem,
        ProgressionItemType,
        ProgressionItemLocality,
        RemoveEntranceLogic,
        RespectEarlyLocations,
        NoProgressionMaze,
    ])
]
