"""
Fuzzer for MultiRogue World

Detects game complexity by generating test multiworlds with random options.
Used to calibrate difficulty curves and speed up stage generation.
"""

import logging
import random
from typing import Dict, Tuple, Optional
from argparse import Namespace

import Utils
from Generate import roll_settings, read_weights_yamls
from BaseClasses import MultiWorld, CollectionState
from worlds import AutoWorldRegister
from worlds.AutoWorld import call_all

logger = logging.getLogger("MultiRogue")


class ComplexityMetrics:
    """Metrics for a generated multiworld."""
    
    def __init__(self):
        self.progression_item_count = 0
        self.total_item_count = 0
        self.location_count = 0
        self.reachable_locations_from_start = 0
        self.complexity_score = 0.5  # 0.0 (trivial) to 1.0 (very complex)
    
    def calculate_complexity(self) -> float:
        """
        Calculate a composite complexity score (0.0 to 1.0).
        
        Factors:
        - Progression item density (higher = more complex)
        - Reachability ratio (lower early access = more complex)
        - Item pool diversity
        """
        if self.total_item_count == 0:
            return 0.5  # Default middle value
        
        # Progression density: 0.0-1.0
        prog_density = self.progression_item_count / max(self.total_item_count, 1)
        
        # Reachability ratio: invert so low early access = high complexity
        # If all locations are immediately reachable, complexity is low
        reach_ratio = self.reachable_locations_from_start / max(self.location_count, 1)
        reachability_factor = 1.0 - reach_ratio
        
        # Composite: weight towards reachability (gating logic is key to complexity)
        self.complexity_score = (prog_density * 0.3) + (reachability_factor * 0.7)
        return self.complexity_score


def measure_multiworld_complexity(multiworld: MultiWorld, player: int) -> ComplexityMetrics:
    """
    Measure complexity of a generated multiworld.
    
    Args:
        multiworld: Generated MultiWorld
        player: Player ID to analyze
    
    Returns:
        ComplexityMetrics with measured values
    """
    metrics = ComplexityMetrics()
    
    # Count items
    locations = list(multiworld.get_locations(player))
    items = [loc.item for loc in locations if loc.item]
    
    metrics.location_count = len(locations)
    metrics.total_item_count = len(items)
    metrics.progression_item_count = sum(1 for item in items if item and item.advancement)
    
    # Measure reachability from start
    initial_state = CollectionState(multiworld)
    reachable = multiworld.get_reachable_locations(initial_state, player)
    metrics.reachable_locations_from_start = len(reachable)
    
    metrics.calculate_complexity()
    return metrics


def fuzz_game(game: str, iterations: int = 20) -> Tuple[float, float, float, int]:
    """
    Run fuzz tests on a game to measure complexity.
    
    Generates multiple test MultiWorlds with random options and measures complexity.
    Handles generation failures gracefully.
    
    Args:
        game: Game name to fuzz
        iterations: Number of test generations to attempt
    
    Returns:
        (min_complexity, max_complexity, avg_complexity, success_count)
    """
    if game not in AutoWorldRegister.world_types:
        logger.error(f"Game {game} not found in AutoWorldRegister")
        return 0.5, 0.5, 0.5, 0
    
    complexities = []
    failures = 0
    
    for iteration in range(iterations):
        try:
            # Generate a test MultiWorld with this game
            # Use a deterministic but different seed for each iteration
            test_seed = hash(f"{game}_fuzz_{iteration}") % (2 ** 31)
            
            # Create minimal MultiWorld
            multiworld = MultiWorld(1)
            multiworld.game = {1: game}
            multiworld.player_name = {1: "FuzzTest"}
            multiworld.set_seed(test_seed)
            
            # Create world instance with default options
            world_type = AutoWorldRegister.world_types[game]
            multiworld.worlds[1] = world_type(multiworld, 1)
            
            # Set default options
            from argparse import Namespace
            args = Namespace()
            for key, option in world_type.options_dataclass.type_hints.items():
                setattr(args, key, {1: option.from_any(option.default)})
            multiworld.set_options(args)
            
            # Run generation steps
            from BaseClasses import CollectionState
            multiworld.state = CollectionState(multiworld)
            
            call_all(multiworld, "generate_early")
            call_all(multiworld, "create_regions")
            call_all(multiworld, "create_items")
            call_all(multiworld, "set_rules")
            call_all(multiworld, "connect_entrances")
            call_all(multiworld, "generate_basic")
            
            # Measure complexity
            metrics = measure_multiworld_complexity(multiworld, 1)
            complexities.append(metrics.complexity_score)
            
            logger.debug(f"  {game} iteration {iteration}: complexity={metrics.complexity_score:.2f}")
        
        except Exception as e:
            failures += 1
            logger.debug(f"  {game} iteration {iteration} failed: {e}")
    
    # Calculate statistics
    success_count = len(complexities)
    if success_count == 0:
        logger.warning(f"All fuzz iterations failed for {game}")
        return 0.5, 0.5, 0.5, 0
    
    min_complexity = min(complexities)
    max_complexity = max(complexities)
    avg_complexity = sum(complexities) / len(complexities)
    
    logger.info(f"Fuzzed {game}: {success_count}/{iterations} successes, "
               f"complexity [{min_complexity:.2f}, {max_complexity:.2f}] avg={avg_complexity:.2f}")
    
    return min_complexity, max_complexity, avg_complexity, success_count
