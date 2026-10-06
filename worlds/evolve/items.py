from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Item, ItemClassification

from .evolveData import techItems,crisprItems,fillerItems,trapItems

if TYPE_CHECKING:
    from .world import EvolveWorld

ITEM_NAME_TO_ID = {} | techItems | crisprItems | fillerItems | trapItems


DEFAULT_ITEM_CLASSIFICATIONS = {}
#add the different item types
for i in techItems:
    DEFAULT_ITEM_CLASSIFICATIONS[i]=ItemClassification.progression
for i in crisprItems:
    DEFAULT_ITEM_CLASSIFICATIONS[i]=ItemClassification.useful
for i in fillerItems:
    DEFAULT_ITEM_CLASSIFICATIONS[i]=ItemClassification.filler
for i in trapItems:
    DEFAULT_ITEM_CLASSIFICATIONS[i]=ItemClassification.trap


# Each Item instance must correctly report the "game" it belongs to.
# To make this simple, it is common practice to subclass the basic Item class and override the "game" field.
class EvolveItem(Item):
    game = "Evolve"

def randomChoice(world:EvolveWorld,*choices:list[str,int]):
    #get the denominator
    t=sum(map(lambda key:key[1],choices))
    #get the numerator
    rand=world.random.randint(1,t)
    #go though every choice
    for chce in choices:
        #if rand is less or equal to its chance of being chosen, it is chosen
        if rand<=chce[1]:return chce[0]
        #if not, subtract the chance
        rand-=chce[1]
    #if we dont return any (for unforseeable reasons), return a random one
    return choices[rand(0,len(choices)-1)][0]


def get_random_filler_item_name(world: EvolveWorld) -> str:
    #My special odds builder yay
    return randomChoice(world,
        ["item-filler:resources",4],
        ["item-filler:building",2],
        ["item-filler:power_bonus",1],
        ["item-filler:prod_bonus",1],
        ["item-filler:pop_bonus",1],
        [randomChoice(world,
            [randomChoice(world,
                ["item-filler:plasmid_1",7],
                ["item-filler:plasmid_2",4],
                ["item-filler:plasmid_3",2],
                ["item-filler:plasmid_4",1],
            ),5],
            [randomChoice(world,
                ["item-filler:phage_1",3],
                ["item-filler:phage_2",2],
                ["item-filler:phage_3",1],
            ),3],
            [randomChoice(world,
                ["item-filler:antiplasmid_1",3],
                ["item-filler:antiplasmid_2",1],
            ),2],
        ),2],
        [randomChoice(world,
            ["item-trap:resources",3],
            ["item-trap:power_malus",1],
            ["item-trap:prod_malus",1],
            ["item-trap:attack",2],
        ),1]
    )


def create_item_with_correct_classification(world: EvolveWorld, name: str) -> EvolveItem:
    classification = DEFAULT_ITEM_CLASSIFICATIONS[name]

    return EvolveItem(name, classification, ITEM_NAME_TO_ID[name], world.player)

# With those two helper functions defined, let's now get to actually creating and submitting our itempool.
def create_all_items(world: EvolveWorld) -> None:
    #Create all the items!

    itempool: list[Item] = []
    for i in ITEM_NAME_TO_ID:
        itempool.append(world.create_item(i))

    # make the item pool have enough items!
    #if the number of locations is less than the amount of items...
    number_of_items = len(itempool)
    number_of_unfilled_locations = len(world.multiworld.get_unfilled_locations(world.player))
    needed_number_of_filler_items = number_of_unfilled_locations - number_of_items
    #add enough items to have the same amount!
    itempool += [world.create_filler() for _ in range(needed_number_of_filler_items)]

    world.multiworld.itempool += itempool
    