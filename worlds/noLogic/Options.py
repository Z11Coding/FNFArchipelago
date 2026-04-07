# Copyright (c) 2024
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from dataclasses import dataclass
from Options import Toggle, Choice, Range, PerGameCommonOptions, OptionGroup



class AddProgressionItem(Toggle):
    """
    Whether to add a special progression item that links to all required progression items
    from each world in the multiworld. This item grants immediate access to everything.
    (Requires the No Logic Client to be connected, to receive the items.)
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
    - local: Each player's progression item can ONLY be placed in that player's own world (or No Logic)
    - non_local: Each player's progression item CANNOT be placed in that player's own world (must go elsewhere)
    - one_per_world: Non-local variant where only ONE progression item is allowed per world total
    - anywhere: No restrictions, items can be placed anywhere in the multiworld
    """
    display_name = "Progression Item Locality"
    option_local = 0
    option_non_local = 1
    option_one_per_world = 2
    option_anywhere = 3
    default = 3


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


class NoProgressionMaze(Choice):
    """
    RISKY: When enabled, removes the original progression items from the pool and only provides
    the linked progression item. This can make the game unwinnable more often than not.
    Leave disabled for safer gameplay.
    Special Mode: Logical - Disables the no logic aspect of this APWorld in favor of a different unique check-hunting experience. (Made by request.)
    (Requires Progression Shards - In Percentage mode, for this option to work.)
    """
    display_name = "No Progression Maze"
    option_disabled = 0
    option_enabled = 1
    option_logical_mode = 2


class IncludeLesserProgression(Toggle):
    """
    When enabled, progression item collections will also include items classified as:
    - progression_skip_balancing
    - progression_deprioritized
    - progression_deprioritized_skip_balancing
    """
    display_name = "Include Lesser Progression Items"
    default = False

class IncludeUsefulProgressionItems(Toggle):
    """
    When enabled, progression item collections will also include items classified as:
    - useful progression. (Progression | Useful)
    """
    display_name = "Include Useful Progression Items"
    default = False

class IncludeUnusualProgressionItems(Toggle):
    """
    When enabled, progression item collections will also include items classified as:
    - progression items that don't fit into the above categories for whatever reason. (Anything with "progression" in the classification that isn't already included by the other options.)
    """
    display_name = "Include Unusual Progression Items"
    default = False

class ProgressionItemMode(Choice):
    """
    How progression items should be delivered:
    - Normal: The collected progression item is provided as-is (single item)
    - Shards - All: The progression item is split into shards; you must collect all shards to get all items
    - Shards - Percentage: As you collect shards, you progressively unlock items based on percentage collected
    """
    display_name = "Progression Item Mode"
    option_normal = 0
    option_shards_all = 1
    option_shards_percentage = 2
    default = 0

class ProgressionShardCount(Range):
    """
    How many shards to split progression items into (only applies when using Shards mode).
    Minimum: 5 shards, Maximum: 200 shards
    """
    display_name = "Progression Shard Count"
    range_start = 5
    range_end = 200
    default = 15

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
    include_useful_progression_items: IncludeUsefulProgressionItems
    include_unusual_progression_items: IncludeUnusualProgressionItems
    progression_item_mode: ProgressionItemMode
    progression_shard_count: ProgressionShardCount
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
        IncludeUsefulProgressionItems,
        IncludeUnusualProgressionItems,
        ProgressionItemMode,
        ProgressionShardCount,
        AutoHintProgressionItems,
    ])
]
