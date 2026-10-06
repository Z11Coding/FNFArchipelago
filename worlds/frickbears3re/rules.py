"""Progression rules for Five Nights at Frickbear's 3 randomizer.

Defines the logic for which items are needed to access which locations
and how progression works through the game.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import Frickbears3ReWorld


def set_all_rules(world: Frickbears3ReWorld) -> None:
    """Set all progression rules for the world."""
    set_location_access_rules(world)
    set_completion_condition(world)


def set_location_access_rules(world: Frickbears3ReWorld) -> None:
    """Set access rules for each location based on required items."""
    # Day 2 requires Day 2 unlock
    day2_locations = [
        "Day 2 - Show Stage Salvage",
        "Day 2 - Party Room Salvage",
        "Day 2 - Game Area Salvage",
        "Day 2 - Cam Station Salvage"
    ]
    for location_name in day2_locations:
        location = world.get_location(location_name)
        location.access_rule = lambda state, item="Unlock New Freddy Fazbear's Pizza": \
            state.has(item, world.player)
    
    # Day 3 requires Day 3 unlock
    day3_locations = [
        "Day 3 - Entrance Hall Salvage",
        "Day 3 - Office Salvage",
        "Day 3 - Main Hall Salvage",
        "Day 3 - Lower Level Salvage"
    ]
    for location_name in day3_locations:
        location = world.get_location(location_name)
        location.access_rule = lambda state, item="Unlock Fazbear's Fright": \
            state.has(item, world.player)
    
    # Day 4 requires Day 4 unlock
    day4_locations = [
        "Day 4 - Forest Path Salvage",
        "Day 4 - Cabin Salvage",
        "Day 4 - Tree House Salvage",
        "Day 4 - Well Salvage"
    ]
    for location_name in day4_locations:
        location = world.get_location(location_name)
        location.access_rule = lambda state, item="Unlock William's Woods": \
            state.has(item, world.player)
    
    # Money Ending requires Talbert's Files
    money_ending = world.get_location("Money Ending")
    money_ending.access_rule = lambda state: state.has("Talbert's Files", world.player)


def set_completion_condition(world: Frickbears3ReWorld) -> None:
    """Set the completion condition (goal/victory condition) for the world."""
    # Players must complete their chosen ending
    # The multiworld system will set this based on configuration
    pass
