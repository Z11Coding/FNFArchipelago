from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Entrance, Region

# from .evolveData import researchLevels

if TYPE_CHECKING:
    from .world import EvolveWorld


def create_and_connect_regions(world: EvolveWorld) -> None:
    create_all_regions(world)
    connect_regions(world)


def create_all_regions(world: EvolveWorld) -> None:
    #Nope not this one:
    # regions = [Region(i,world.player,world.multiworld) for i in researchLevels]

    #We just need one region!
    regions=[Region("Main",world.player,world.multiworld)]

    world.multiworld.regions += regions

def convertLocToItem(locs):return [i.replace("-loc","-item") for i in locs]
def connect_regions(world: EvolveWorld) -> None:
    # we dont need any connections
    pass