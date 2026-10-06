from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Entrance, Region

if TYPE_CHECKING:
    from . import Frickbears3ReWorld

from .locations import LOCATION_REGIONS


def create_and_connect_regions(world: Frickbears3ReWorld) -> None:
    """Create all regions and connect them with entrances."""
    create_all_regions(world)
    connect_regions(world)


def create_all_regions(world: Frickbears3ReWorld) -> None:
    """Create all regions for the world."""
    regions = [
        Region("Overworld", world.player, world.multiworld),
        Region("Day 1: Freddy's Pizza", world.player, world.multiworld),
        Region("Day 2: New Freddy's", world.player, world.multiworld),
        Region("Day 3: Fazbear's Fright", world.player, world.multiworld),
        Region("Day 4: William's Woods", world.player, world.multiworld),
        Region("Day 5: Final Night", world.player, world.multiworld),
        Region("Shop", world.player, world.multiworld),
        Region("Ending Route", world.player, world.multiworld),
    ]
    
    world.multiworld.regions += regions


def connect_regions(world: Frickbears3ReWorld) -> None:
    """Connect regions with entrances and access rules."""
    overworld = world.get_region("Overworld")
    day1 = world.get_region("Day 1: Freddy's Pizza")
    day2 = world.get_region("Day 2: New Freddy's")
    day3 = world.get_region("Day 3: Fazbear's Fright")
    day4 = world.get_region("Day 4: William's Woods")
    day5 = world.get_region("Day 5: Final Night")
    shop = world.get_region("Shop")
    ending_route = world.get_region("Ending Route")
    
    # Overworld connects to all major areas
    overworld.connect(day1, "Overworld to Day 1")
    overworld.connect(day2, "Overworld to Day 2", lambda state: state.has("Unlock New Freddy Fazbear's Pizza", world.player))
    overworld.connect(day3, "Overworld to Day 3", lambda state: state.has("Unlock Fazbear's Fright", world.player))
    overworld.connect(day4, "Overworld to Day 4", lambda state: state.has("Unlock William's Woods", world.player))
    overworld.connect(day5, "Overworld to Day 5")
    overworld.connect(shop, "Overworld to Shop")
    overworld.connect(ending_route, "Overworld to Ending Route")
    
    # Day progression chain
    day1.connect(day2, "Day 1 to Day 2")
    day2.connect(day3, "Day 2 to Day 3")
    day3.connect(day4, "Day 3 to Day 4")
    day4.connect(day5, "Day 4 to Day 5")
