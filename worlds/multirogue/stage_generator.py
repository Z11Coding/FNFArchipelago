"""
Stage Generator for MultiRogue World

Orchestrates the generation of mini-multiworlds (stages).
Handles game selection, difficulty targeting, and retry logic.
"""

import logging
import random
import hashlib
from typing import Dict, List, Optional, Tuple
from argparse import Namespace

from BaseClasses import MultiWorld, CollectionState
from worlds import AutoWorldRegister
from worlds.AutoWorld import call_all
from .cache_manager import get_cache_manager
from .fuzzer import measure_multiworld_complexity
from .output_packer import StageData

logger = logging.getLogger("MultiRogue")


class StageGenerationConfig:
    """Configuration for stage generation."""
    
    def __init__(self, options):
        self.num_stages = options.num_stages.value
        self.difficulty_curve = options.difficulty_curve.value
        self.max_retries = options.max_retries.value
        self.game_whitelist = self._parse_game_list(options.game_whitelist.value)
        self.game_blacklist = self._parse_game_list(options.game_blacklist.value)
        self.max_players_per_stage = options.max_players_per_stage.value
        self.use_duplicate_games = options.use_duplicate_games.value
        self.themed_stages = options.themed_stages.value
        self.stage_composition = options.stage_composition.value
        self.progression_gating = options.progression_gating.value
        self.is_multiplayer = False
    
    @staticmethod
    def _parse_game_list(game_str: str) -> List[str]:
        """Parse comma-separated game list."""
        if not game_str:
            return []
        return [g.strip() for g in game_str.split(",") if g.strip()]
    
    def get_available_games(self) -> List[str]:
        """Get list of available games after applying whitelist/blacklist."""
        available = list(AutoWorldRegister.world_types.keys())
        
        if self.game_whitelist:
            available = [g for g in available if g in self.game_whitelist]
        
        if self.game_blacklist:
            available = [g for g in available if g not in self.game_blacklist]
        
        if not available:
            logger.warning("No games available after applying whitelist/blacklist!")
            return list(AutoWorldRegister.world_types.keys())
        
        return available
    
    def get_difficulty_target(self, stage_num: int) -> float:
        """
        Calculate difficulty target for a stage based on progression curve.
        
        Args:
            stage_num: Stage number (0-indexed)
        
        Returns:
            Difficulty target (0.0 to 1.0)
        """
        progress = stage_num / max(self.num_stages - 1, 1)
        
        if self.difficulty_curve == 0:  # Linear
            return 0.2 + (progress * 0.6)  # Range: 0.2 to 0.8
        elif self.difficulty_curve == 1:  # Exponential
            return 0.2 + (progress ** 2 * 0.6)
        elif self.difficulty_curve == 2:  # Sigmoid
            # S-curve: slow start, fast middle, slow end
            x = (progress * 2) - 1  # Range: -1 to 1
            sigmoid = 1 / (1 + (2.718 ** (-x * 2)))  # Roughly e^(-2x)
            return 0.2 + (sigmoid * 0.6)
        else:
            return 0.5


def derive_stage_seed(base_seed: int, stage_num: int) -> int:
    """
    Derive a deterministic seed for a specific stage.
    
    Uses base seed + stage number to create unique but consistent seeds.
    
    Args:
        base_seed: Main multiworld seed
        stage_num: Stage number
    
    Returns:
        Derived seed for this stage
    """
    seed_str = f"{base_seed}MM-{stage_num}"
    hash_obj = hashlib.sha256(seed_str.encode())
    derived = int(hash_obj.hexdigest(), 16) % (2 ** 31)
    return derived


def select_games_for_stage(config: StageGenerationConfig, stage_num: int) -> List[str]:
    """
    Select games for a stage based on configuration.
    
    Args:
        config: Generation configuration
        stage_num: Stage number
    
    Returns:
        List of game names to use in this stage
    """
    available = config.get_available_games()
    
    # Determine number of players in this stage
    if config.is_multiplayer:
        num_players = random.randint(1, config.max_players_per_stage)
    else:
        num_players = 1
    
    selected = []
    
    if config.stage_composition == 0:  # Diverse
        # Prefer different games
        selected = random.sample(available, min(num_players, len(available)))
    elif config.stage_composition == 1:  # Duplicates
        # Allow same game multiple times
        selected = [random.choice(available) for _ in range(num_players)]
    elif config.stage_composition == 2:  # Themed
        # Group related games (games with common words or specific themes)
        # For now, just random selection (TODO: implement theme grouping)
        selected = random.sample(available, min(num_players, len(available)))
    
    return selected


def generate_single_stage(config: StageGenerationConfig, base_seed: int, stage_num: int,
                         difficulty_target: float) -> Optional[Tuple[MultiWorld, List[str]]]:
    """
    Generate a single mini-multiworld (stage).
    
    Args:
        config: Generation configuration
        base_seed: Main multiworld seed
        stage_num: Stage number
        difficulty_target: Target difficulty (0.0-1.0)
    
    Returns:
        (MultiWorld, games_used) on success, None on failure
    """
    stage_seed = derive_stage_seed(base_seed, stage_num)
    games = select_games_for_stage(config, stage_num)
    num_players = len(games)
    
    logger.info(f"Generating stage {stage_num}: {num_players} players with {games}, "
               f"difficulty target {difficulty_target:.2f}")
    
    try:
        # Create MultiWorld for this stage
        multiworld = MultiWorld(num_players)
        multiworld.game = {i + 1: game for i, game in enumerate(games)}
        multiworld.player_name = {i + 1: f"Player{i + 1}" for i in range(num_players)}
        multiworld.set_seed(stage_seed)
        
        # Create world instances with default options
        args = Namespace()
        for player, game in enumerate(games, 1):
            world_type = AutoWorldRegister.world_types[game]
            multiworld.worlds[player] = world_type(multiworld, player)
            
            # Set default options (TODO: could optimize based on difficulty_target)
            for key, option in world_type.options_dataclass.type_hints.items():
                if not hasattr(args, key):
                    setattr(args, key, {})
                getattr(args, key)[player] = option.from_any(option.default)
        
        multiworld.set_options(args)
        
        # Run generation steps
        multiworld.state = CollectionState(multiworld)
        
        call_all(multiworld, "generate_early")
        call_all(multiworld, "create_regions")
        call_all(multiworld, "create_items")
        call_all(multiworld, "set_rules")
        call_all(multiworld, "connect_entrances")
        call_all(multiworld, "generate_basic")
        
        # TODO: Add pre_fill and fill steps if needed
        
        # Validate solvability
        for player in multiworld.player_ids:
            metrics = measure_multiworld_complexity(multiworld, player)
            logger.debug(f"  Player {player} ({games[player-1]}): complexity={metrics.complexity_score:.2f}")
        
        return multiworld, games
    
    except Exception as e:
        logger.error(f"Failed to generate stage {stage_num}: {e}")
        return None


def generate_all_stages(multiworld, options) -> Tuple[List[StageData], bool]:
    """
    Generate all stages for a MultiRogue seed.
    
    Args:
        multiworld: The main MultiWorld
        options: MultiRogueOptions
    
    Returns:
        (List of StageData, success_flag)
    """
    config = StageGenerationConfig(options)
    config.is_multiplayer = multiworld.players > 1
    
    cache_manager = get_cache_manager()
    
    # Ensure all games are fuzzed if needed
    for game in config.get_available_games():
        if cache_manager.should_refuzz(game):
            logger.info(f"Fuzzing game {game}...")
            from .fuzzer import fuzz_game
            min_c, max_c, avg_c, count = fuzz_game(game, options.fuzz_iterations.value)
            if count > 0:
                cache_manager.update_profile(game, min_c, max_c, avg_c, count)
    
    # Generate stages
    stages = []
    base_seed = multiworld.seed
    
    for stage_num in range(config.num_stages):
        difficulty_target = config.get_difficulty_target(stage_num)
        
        # Retry loop
        generated_mw = None
        games_used = []
        for attempt in range(config.max_retries):
            result = generate_single_stage(config, base_seed, stage_num, difficulty_target)
            if result is not None:
                generated_mw, games_used = result
                break
            logger.warning(f"Stage {stage_num} attempt {attempt + 1}/{config.max_retries} failed, retrying...")
        
        if generated_mw is None:
            logger.error(f"Failed to generate stage {stage_num} after {config.max_retries} retries!")
            return stages, False
        
        # Create StageData
        stage_data = StageData(stage_num)
        stage_data.difficulty_target = difficulty_target
        stage_data.games_used = games_used
        # TODO: Serialize multidata and spoiler
        stages.append(stage_data)
    
    logger.info(f"Successfully generated {len(stages)}/{config.num_stages} stages")
    return stages, True
