from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import ItemClassification, Location, Region

from .evolveData import locationsData,buildingReqs,optionDependReqs, specials

from . import items

if TYPE_CHECKING:
    from .world import EvolveWorld


# if it is "loc-tech:*" then this is the items in the tech tree
# if it is "loc-build:*" then that is a building
LOCATION_NAME_TO_ID = locationsData
#some are dependent on an option, so only add those when we should!
specialReqs=set()#"loc-build:temple","loc-tech:wind_plant","loc-techagriculture:","loc-tech:farm_house","loc-tech:irrigation","loc-tech:copper_hoe","loc-tech:iron_hoe","loc-tech:steel_hoe","loc-tech:titanium_hoe","loc-tech:silo","loc-tech:mill","loc-tech:windmill","loc-tech:windturbine","loc-tech:magocracy","loc-tech:governor","loc-tech:theology","loc-tech:theocracy","loc-tech:last_rites","loc-tech:fanaticism","loc-tech:alt_fanaticism","loc-tech:anthropology","loc-tech:alt_anthropology","loc-tech:indoctrination","loc-tech:mythology","loc-tech:missionary","loc-tech:archaeology","loc-tech:","loc-tech:","loc-tech:","loc-tech:","loc-tech:","loc-tech:",]#"loc-tech:wooden_tools","loc-tech:bone_tools","loc-tech:republic","loc-tech:socialist","loc-tech:wagon","loc-tech:reclaimer","loc-tech:shovel","loc-tech:iron_shovel","loc-tech:steel_shovel","loc-tech:titanium_shovel","loc-tech:alloy_shovel",
for typ in specials:
    for i in specials[typ]:
        # print(typ+":"+nm for nm in i.locs)
        specialReqs.update(typ+":"+nm for nm in i.locs)
# print(specialReqs)
class EvolveLocation(Location):
    game = "Evolve"


def get_location_names_with_ids(location_names: list[str]) -> dict[str, int | None]:
    return {location_name: LOCATION_NAME_TO_ID[location_name] for location_name in location_names}


def create_all_locations(world: EvolveWorld) -> None:
    create_regular_locations(world)
    create_events(world)


def create_regular_locations(world: EvolveWorld) -> None:
    specialReqs=set()#"loc-build:temple","loc-tech:wind_plant","loc-techagriculture:","loc-tech:farm_house","loc-tech:irrigation","loc-tech:copper_hoe","loc-tech:iron_hoe","loc-tech:steel_hoe","loc-tech:titanium_hoe","loc-tech:silo","loc-tech:mill","loc-tech:windmill","loc-tech:windturbine","loc-tech:magocracy","loc-tech:governor","loc-tech:theology","loc-tech:theocracy","loc-tech:last_rites","loc-tech:fanaticism","loc-tech:alt_fanaticism","loc-tech:anthropology","loc-tech:alt_anthropology","loc-tech:indoctrination","loc-tech:mythology","loc-tech:missionary","loc-tech:archaeology","loc-tech:","loc-tech:","loc-tech:","loc-tech:","loc-tech:","loc-tech:",]#"loc-tech:wooden_tools","loc-tech:bone_tools","loc-tech:republic","loc-tech:socialist","loc-tech:wagon","loc-tech:reclaimer","loc-tech:shovel","loc-tech:iron_shovel","loc-tech:steel_shovel","loc-tech:titanium_shovel","loc-tech:alloy_shovel",
    for typ in specials:
        for i in specials[typ]:
            specialReqs.update(typ+":"+nm for nm in i.locs)

    #we only have one region 
    main = world.get_region("Main")

    # because its just one region we dont need to do anything to seperate the locations
    for i in world.location_name_to_id:
        if i in specialReqs or i in buildingReqs:continue
        main.locations.append(EvolveLocation(world.player,i,world.location_name_to_id[i],main))
    
    for i in specials["loc-tech"]:
        for j in i.evaluate(world):
            nm=f"loc-tech:{j}"
            if not nm in specialReqs:continue
            main.locations.append(EvolveLocation(world.player,nm,world.location_name_to_id[nm],main))
            specialReqs.remove(nm)
    
    for i in buildingReqs:
        try:
            world.get_location(buildingReqs[i])
            main.locations.append(EvolveLocation(world.player,nm,world.location_name_to_id[nm],main))
        except:
            pass
    
    for i in specials["loc-build"]:
        # tch=specials["loc-build"][i]
        for j in i.evaluate(world):
            nm=f"loc-build:{j}"
            main.locations.append(EvolveLocation(world.player,nm,world.location_name_to_id[nm],main))
    # for opt in optionDependReqs:
    #     reqs=optionDependReqs[opt]
    #     if world.options
    
    


def create_events(world: EvolveWorld) -> None:
    #just one! this is winning the game!
    main = world.get_region("Main")
    

    main.add_event(
        "Missles Launched", "Victory", location_type=EvolveLocation, item_type=items.EvolveItem
    )