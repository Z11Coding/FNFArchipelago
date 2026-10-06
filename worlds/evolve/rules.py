from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import CollectionState
from worlds.generic.Rules import add_rule, set_rule

from .evolveData import techLocsPre

if TYPE_CHECKING:
    from .world import EvolveWorld


def set_all_rules(world: EvolveWorld) -> None:
    # In order for AP to generate an item layout that is actually possible for the player to complete,
    # we need to define rules for our Entrances and Locations.
    # Note: Regions do not have rules, the Entrances connecting them do!
    # We'll do entrances first, then locations, and then finally we set our victory condition.

    set_all_entrance_rules(world)
    set_all_location_rules(world)
    set_completion_condition(world)


def set_all_entrance_rules(world: EvolveWorld) -> None:
    pass
    # we dont have multiple regions, so no entrances!


def set_all_location_rules(world: EvolveWorld) -> None:

    # main=world.get_location("Main")
    for i in techLocsPre:
        loc=world.get_location(i)
        set_rule(loc,lambda state:(state.has_all(techLocsPre[i],world.player)))


def set_completion_condition(world: EvolveWorld) -> None:
    world.multiworld.completion_condition[world.player] = lambda state: state.has("Victory", world.player)
