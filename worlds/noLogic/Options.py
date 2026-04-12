# Copyright (c) 2024
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from dataclasses import dataclass
import logging
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
    - Shards - Percentage of Items: Shard count is calculated as a percentage of the number of progression items
    """
    display_name = "Progression Item Mode"
    option_normal = 0
    option_shards_all = 1
    option_shards_percentage = 2
    option_shards_percentage_of_items = 3
    default = 0

class FlexibleRange(Range):
    """
    A Range that allows out-of-bounds values with warnings instead of hard errors.
    Set allow_below_range and allow_above_range to control whether values outside bounds are permitted.
    When allowed, a warning is logged and verify() will prompt for confirmation.
    """
    allow_below_range: bool = False
    allow_above_range: bool = False
    
    def __init__(self, value: int):
        # Check bounds but allow if configured to do so
        if value < self.range_start:
            if not self.allow_below_range:
                raise Exception(f"{value} is lower than minimum {self.range_start} for option {self.__class__.__name__}")
            else:
                # Value is below range but allowed - store with warning
                logging.warning(f"{self.__class__.__name__}: {value} is below recommended minimum of {self.range_start}")
        elif value > self.range_end:
            if not self.allow_above_range:
                raise Exception(f"{value} is higher than maximum {self.range_end} for option {self.__class__.__name__}")
            else:
                # Value is above range but allowed - store with warning
                logging.warning(f"{self.__class__.__name__}: {value} is above recommended maximum of {self.range_end}")
        self.value = value
    
    def verify(self, world, player_name: str, plando_options) -> None:
        """Verify method called during world generation to warn about out-of-bounds values and request confirmation."""
        display_name = getattr(self, 'display_name', self.__class__.__name__)
        
        if self.value < self.range_start and self.allow_below_range:
            warning_msg = (
                f"Player {player_name}: {display_name} is set to {self.value}, which is below the recommended "
                f"minimum of {self.range_start}. This may cause unexpected behavior. Proceed? (y/n): "
            )
            response = input(warning_msg).strip().lower()
            if response != "y":
                raise Exception(f"Generation cancelled for player {player_name}. {display_name} out-of-bounds value was not confirmed.")
        elif self.value > self.range_end and self.allow_above_range:
            warning_msg = (
                f"Player {player_name}: {display_name} is set to {self.value}, which is above the recommended "
                f"maximum of {self.range_end}. This may cause unexpected behavior. Proceed? (y/n): "
            )
            response = input(warning_msg).strip().lower()
            if response != "y":
                raise Exception(f"Generation cancelled for player {player_name}. {display_name} out-of-bounds value was not confirmed.")

class ProgressionShardCount(FlexibleRange):
    """
    How many shards to split progression items into (only applies when using Shards mode).
    Recommended range: 5-200 shards. Values above 200 are allowed but may impact performance or make things much more difficult.
    (This option can be set above the maximum, but it's not recommended.)
    """
    display_name = "Progression Shard Count"
    range_start = 5
    range_end = 200
    default = 15
    allow_below_range = False
    allow_above_range = True

class ProgressionShardPercentage(FlexibleRange):
    """
    When using Shards - Percentage of Items mode, sets the shard count as a percentage of 
    the number of progression items. For example, if there are 10 progression items and this 
    is set to 200%, there will be 20 shards total. Recommended range: 10-1000%. 
    Values above 1000% are allowed but may impact performance, or make things much more difficult.
    (WARNING: This may cause fill errors at a high percentage! If you encounter fill errors, reduce this percentage or switch to a fixed shard count.)
    (This option can be set above the maximum, but it's not recommended.)
    """
    display_name = "Progression Shard Percentage"
    range_start = 10
    range_end = 1000
    default = 100
    allow_below_range = False
    allow_above_range = True

class AutoHintProgressionItems(Toggle):
    """
    When enabled, progression item locations will be automatically hinted when the game generates.
    This makes it easier to track which world each progression item comes from.
    """
    display_name = "Auto-Hint Progression Items"
    default = False


class FunnyFillers(Toggle):
    """
    When enabled, filler items will have random funny names instead of just "Filler".
    Purely cosmetic and doesn't affect gameplay.
    """
    display_name = "Funny Fillers"
    default = False


class ProgressionTrapWeight(Range):
    """
    Percentage chance (0-100%) that each filler item becomes a trap item instead.
    For example, 50% means approximately half of the filler items will be traps.
    Default: 0 (no traps).
    """
    display_name = "Progression Trap Weight"
    range_start = 0
    range_end = 100
    default = 0


class ProgressionTrapMode(Choice):
    """
    How traps are distributed across the multiworld:
    - Disabled: No traps are created
    - Global: Traps are shared randomly among all players
    - World-Specific: Each player gets their own trap(s) based on weight
    - Finders-Keepers: Trap goes to whoever finds it during normal fill
    """
    display_name = "Progression Trap Mode"
    option_disabled = 0
    option_global = 1
    option_world_specific = 2
    option_finders_keepers = 3
    default = 0


class ProgressionTrapLocality(Choice):
    """
    Where traps can be placed (only applies to World-Specific mode):
    - Anywhere: No restrictions
    - Local: Traps stay within their target world
    - Non-Local: Traps cannot be in their target world
    """
    display_name = "Progression Trap Locality"
    option_anywhere = 0
    option_local = 1
    option_non_local = 2
    default = 0


class GlobalShardsBehavior(Choice):
    """
    How claim_dict is organized when using global progression items with percentage-based shards:
    - Shared Pool: All locations stored under the shard item ID (classic behavior)
    - Per-Player: Locations organized by player ID instead of item ID
    (This option only affects global progression items with percentage modes.)
    """
    display_name = "Global Shards Behavior"
    option_shared_pool = 0
    option_per_player = 1
    default = 0


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
    progression_shard_percentage: ProgressionShardPercentage
    global_shards_behavior: GlobalShardsBehavior
    auto_hint_progression_items: AutoHintProgressionItems
    funny_fillers: FunnyFillers
    progression_trap_weight: ProgressionTrapWeight
    progression_trap_mode: ProgressionTrapMode
    progression_trap_locality: ProgressionTrapLocality


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
        ProgressionShardPercentage,
        GlobalShardsBehavior,
        AutoHintProgressionItems,
        FunnyFillers,
    ]),
    OptionGroup("Progression Traps", [
        ProgressionTrapWeight,
        ProgressionTrapMode,
        ProgressionTrapLocality,
    ])
]
