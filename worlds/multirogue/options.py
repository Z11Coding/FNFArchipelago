"""
MultiRogue World Options

Configures the roguelike/roguelite generation:
- Stage count and difficulty progression
- Game selection (whitelist/blacklist)
- Scenario generation
- Retry behavior
"""

from dataclasses import dataclass
from Options import (
    PerGameCommonOptions, Range, Choice, Toggle, FreeText, OptionGroup
)


class NumStages(Range):
    """How many stages/mini-multiworlds to generate."""
    display_name = "Number of Stages"
    range_start = 1
    range_end = 50
    default = 10


class DifficultyCurve(Choice):
    """How difficulty should scale across stages."""
    display_name = "Difficulty Curve"
    option_linear = 0
    option_exponential = 1
    option_sigmoid = 2
    default = 0


class GoalCompletionCount(Range):
    """In multiplayer: how many stages must be beaten to achieve goal.
    
    In singleplayer, this is ignored (goal is to clear all stages).
    """
    display_name = "Goal Stage Count (Multiplayer)"
    range_start = 1
    range_end = 50
    default = 5


class GameWhitelist(FreeText):
    """Comma-separated list of games to include in stage generation.
    
    If empty, ANY available game can be used (you'll get a warning to confirm).
    Examples: "A Link to the Past, Super Metroid, Undertale"
    """
    display_name = "Game Whitelist"
    default = ""


class GameBlacklist(FreeText):
    """Comma-separated list of games to EXCLUDE from stage generation.
    
    Applied after whitelist (if whitelist is set).
    Examples: "Sega Genesis, Game Boy Advance"
    """
    display_name = "Game Blacklist"
    default = ""


class MaxPlayersPerStage(Range):
    """Maximum number of players allowed in a single stage (mini-multiworld).
    
    For multiplayer main worlds, stages will have random player counts up to this limit.
    """
    display_name = "Max Players Per Stage"
    range_start = 1
    range_end = 4
    default = 2


class UseDuplicateGames(Toggle):
    """Allow the same game to appear in multiple stages.
    
    If False, each game can only appear once across all stages.
    """
    display_name = "Allow Duplicate Games"
    default = True


class ThemedStages(Toggle):
    """Create themed stages (e.g., multiple Zelda variants, or games with common words).
    
    When enabled, some stages will group related games together for variety.
    """
    display_name = "Themed Stages"
    default = True


class GenerateScenarios(Toggle):
    """Enable scenario save state generation.
    
    When enabled, some stages will include pre-played saves at various progression points.
    """
    display_name = "Generate Scenarios"
    default = True


class ScenarioRandomness(Range):
    """What percentage of stages should have scenario saves generated.
    
    0 = no scenarios, 100 = attempt scenario for every stage.
    """
    display_name = "Scenario Generation Rate (%)"
    range_start = 0
    range_end = 100
    default = 50


class MaxRetries(Range):
    """Maximum number of retry attempts for each stage before failing the entire seed.
    
    If a stage cannot be generated after this many attempts, generation fails.
    """
    display_name = "Max Generation Retries Per Stage"
    range_start = 1
    range_end = 10
    default = 3


class StageComposition(Choice):
    """Strategy for selecting games in each stage.
    
    - Diverse: Prefer different games in each stage
    - Duplicates: Allow/encourage same games across stages
    - Themed: Group related games together
    """
    display_name = "Stage Composition Strategy"
    option_diverse = 0
    option_duplicates = 1
    option_themed = 2
    default = 0


class ProgressionGating(Choice):
    """Should stages be gated by progression?
    
    - None: All stages available from start
    - Sequential: Must beat Stage 1, then 2, etc. in order
    - Progressive: Getting items unlocks access to higher-tier stages
    """
    display_name = "Progression Gating"
    option_none = 0
    option_sequential = 1
    option_progressive = 2
    default = 0


class FuzzIterations(Range):
    """How many test generations per game during complexity detection (first run).
    
    Higher = better complexity data but slower initial generation.
    Subsequent runs reuse cached data.
    """
    display_name = "Fuzz Test Iterations Per Game"
    range_start = 5
    range_end = 100
    default = 20


@dataclass
class MultiRogueOptions(PerGameCommonOptions):
    """MultiRogue World Options"""
    num_stages: NumStages
    difficulty_curve: DifficultyCurve
    goal_completion_count: GoalCompletionCount
    game_whitelist: GameWhitelist
    game_blacklist: GameBlacklist
    max_players_per_stage: MaxPlayersPerStage
    use_duplicate_games: UseDuplicateGames
    themed_stages: ThemedStages
    generate_scenarios: GenerateScenarios
    scenario_randomness: ScenarioRandomness
    max_retries: MaxRetries
    stage_composition: StageComposition
    progression_gating: ProgressionGating
    fuzz_iterations: FuzzIterations
