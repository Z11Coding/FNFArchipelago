from dataclasses import dataclass
from typing import Dict
from Options import (
    Choice, Toggle, Range, PerGameCommonOptions,
    Accessibility, DeathLink, StartingInventoryPool
)


class Difficulty(Choice):
    """Starting game difficulty."""
    display_name = "Starting Difficulty"
    option_easy = 0
    option_normal = 1
    option_hard = 2
    option_insanity = 3
    default = 1


class IncludeEndlessAnimatronics(Toggle):
    """Include animatronics only available in Endless Mode.
        (Not implemented yet.)
    """
    display_name = "Include Endless Mode Animatronics"
    default = False


class EndingFilter(Choice):
    """Which endings should be included as victory conditions."""
    display_name = "Ending Victory Conditions"
    option_all_endings = 0
    option_good_ending_only = 1
    option_bad_ending_only = 2
    option_money_ending_only = 3
    option_mystery_ending_only = 4
    option_exclude_mystery = 5
    default = 0


class AnimatronicPoolSize(Choice):
    """How many animatronics to include in the item pool."""
    display_name = "Animatronic Pool Size"
    option_minimal = 0
    option_standard = 1
    option_expanded = 2
    option_complete = 3
    default = 1


class ShopItemDifficulty(Choice):
    """How readily available shop items should be."""
    display_name = "Shop Item Availability"
    option_abundant = 0
    option_normal = 1
    option_scarce = 2
    default = 1


class LocationOrderRandomization(Toggle):
    """Randomize the order in which days/locations appear."""
    display_name = "Randomize Location Order"
    default = False


class StartingTokens(Range):
    """Number of tokens to start with (0-1000)."""
    display_name = "Starting Tokens"
    range_start = 0
    range_end = 1000
    default = 100


class ProgressiveAnimatronic(Toggle):
    """Make animatronic unlocks progressive (each unlock grants a random animatronic)."""
    display_name = "Progressive Animatronic Unlocks"
    default = False


class TrapsEnabled(Toggle):
    """Enable trap items in the pool (consume resources/hamper progress)."""
    display_name = "Enable Trap Items"
    default = False


class GoalRequirements(Choice):
    """How many animatronics must be rescued to win."""
    display_name = "Goal Requirements"
    option_all_animatronics = 0
    option_ending_requirements = 1
    option_75_percent = 2
    option_50_percent = 3
    default = 1


@dataclass
class Frickbears3ReOptions(PerGameCommonOptions):
    """Options for Five Nights at Frickbear's 3 randomizer."""
    
    difficulty: Difficulty
    include_endless_animatronics: IncludeEndlessAnimatronics
    ending_filter: EndingFilter
    animatronic_pool_size: AnimatronicPoolSize
    shop_item_difficulty: ShopItemDifficulty
    location_order_randomization: LocationOrderRandomization
    starting_tokens: StartingTokens
    progressive_animatronic: ProgressiveAnimatronic
    traps_enabled: TrapsEnabled
    goal_requirements: GoalRequirements
    death_link: DeathLink
