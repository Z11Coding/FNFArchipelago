from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

from BaseClasses import Region

if TYPE_CHECKING:
    from . import Frickbears3ReWorld


# Location ID mapping for Archipelago
LOCATION_NAME_TO_ID: Dict[str, int] = {
    # Day 1 - Freddy Fazbear's Pizza
    "Freddy Fazbear's Pizza: Show Stage": 4300001,
    "Freddy Fazbear's Pizza: West Hall Supply Closet": 4300002,
    "Freddy Fazbear's Pizza: Women's Restroom": 4300003,
    "Freddy Fazbear's Pizza: Pirate's Cove": 4300004,
    "Freddy Fazbear's Pizza: Kitchen": 4300005,
    "Freddy Fazbear's Pizza: Backstage": 4300006,
    "Freddy Fazbear's Pizza: Safe Room": 4300007,
    "Freddy Fazbear's Pizza: Arcade Cabinet": 4300008,
    "Freddy Fazbear's Pizza: Puppet's Gift": 4300009,
    
    # Day 2 - The New & Improved Freddy's Pizza
    "The New & Improved Freddy's Pizza: Show Stage": 4300010,
    "The New & Improved Freddy's Pizza: Party Room 3": 4300011,
    "The New & Improved Freddy's Pizza: Party Room 4": 4300012,
    "The New & Improved Freddy's Pizza: Kid's Cove": 4300013,
    "The New & Improved Freddy's Pizza: Women's Restroom": 4300014,
    "The New & Improved Freddy's Pizza: Party Room 1": 4300015,
    "The New & Improved Freddy's Pizza: Parts & Service": 4300016,
    "The New & Improved Freddy's Pizza: Arcade Cabinet": 4300017,
    "The New & Improved Freddy's Pizza: Puppet's Gift": 4300018,
    
    # Day 3 - Fazbear's Fright
    "Fazbear's Fright: CAM 5": 4300020,
    "Fazbear's Fright: Office": 4300021,
    "Fazbear's Fright: CAM 8": 4300022,
    "Fazbear's Fright: CAM 2": 4300023,
    "Fazbear's Fright: CAM Hall 3-4": 4300024,
    "Fazbear's Fright: CAM 7": 4300025,
    "Fazbear's Fright: Alleyway": 4300026,
    "Fazbear's Fright: Arcade Cabinet": 4300027,
    "Fazbear's Fright: Puppet's Gift": 4300028,
    
    # Day 4 - William's Woods
    "William's Woods: Living Room": 4300030,
    "William's Woods: Dave's Bedroom": 4300031,
    "William's Woods: Hallway Upstairs": 4300032,
    "William's Woods: William's Bedroom": 4300033,
    "William's Woods: Behind Trees": 4300034,
    "William's Woods: Toolshed": 4300035,
    "William's Woods: Workshop Upstairs Bod": 4300036,
    "William's Woods: Arcade Cabinet": 4300037,
    "William's Woods: Puppet's Gift": 4300038,
    
    # Day 5 - Circus Baby's Entertainment & Rental
    "Circus Baby's Entertainment & Rental: Circus Gallery": 4300040,
    "Circus Baby's Entertainment & Rental: Ballora Gallery": 4300041,
    "Circus Baby's Entertainment & Rental: Breaker Room": 4300042,
    "Circus Baby's Entertainment & Rental: Funtime Auditorium": 4300043,
    "Circus Baby's Entertainment & Rental: Private Room": 4300044,
    "Circus Baby's Entertainment & Rental: Scooping Room": 4300045,
    "Circus Baby's Entertainment & Rental: Arcade Cabinet": 4300046,

    # Ending Requirements
    "Ultimate Ending": 4300050,
    "Good Ending": 4300051,
    "Money Ending": 4300052,
    "Bad Ending": 4300053,

    # Backdoor Trading
    "Backdoor Trading - Freddy Fazbear's Pizza: Dining Area": 4300060,
    "Backdoor Trading - Freddy Fazbear's Pizza: Pirate's Cove": 4300061,
    "Backdoor Trading - Freddy Fazbear's Pizza: Men's Restroom": 4300062,
    "Backdoor Trading - The New & Improved Freddy's Pizza: Game Area": 4300063,
    "Backdoor Trading - The New & Improved Freddy's Pizza: Party Room 3": 4300064,
    "Backdoor Trading - The New & Improved Freddy's Pizza: Party Room 2": 4300065,
    "Backdoor Trading - Fazbear's Fright: CAM 8": 4300066,
    "Backdoor Trading - Fazbear's Fright: Office Hall": 4300067,
    "Backdoor Trading - Fazbear's Fright: Office Corner": 4300068,
    "Backdoor Trading - William's Woods: Elizabeth's Bedroom": 4300069,
    "Backdoor Trading - William's Woods: Downstairs Bathroom": 4300070,
    "Backdoor Trading - William's Woods: Upstairs Bathroom": 4300071,
    "Backdoor Trading - Circus Baby's Entertainment & Rental: Ballora Gallery": 4300072,
    "Backdoor Trading - Circus Baby's Entertainment & Rental: Circus Gallery": 4300073,
    "Backdoor Trading - Circus Baby's Entertainment & Rental: Private Room": 4300074,
}

# Group locations by region for rule assignment
LOCATION_REGIONS: Dict[str, List[str]] = {
    "Freddy Fazbear's Pizza": [
        "Freddy Fazbear's Pizza: Show Stage",
        "Freddy Fazbear's Pizza: West Hall Supply Closet",
        "Freddy Fazbear's Pizza: Women's Restroom",
        "Freddy Fazbear's Pizza: Pirate's Cove",
        "Freddy Fazbear's Pizza: Kitchen",
        "Freddy Fazbear's Pizza: Backstage",
        "Freddy Fazbear's Pizza: Safe Room",
        "Freddy Fazbear's Pizza: Minigame Cabinet",
        "Backdoor Trading - Freddy Fazbear's Pizza: Dining Area",
        "Backdoor Trading - Freddy Fazbear's Pizza: Pirate's Cove",
        "Backdoor Trading - Freddy Fazbear's Pizza: Men's Restroom",
    ],
    "The New & Improved Freddy's Pizza": [
        "The New & Improved Freddy's Pizza: Show Stage",
        "The New & Improved Freddy's Pizza: Party Room 3",
        "The New & Improved Freddy's Pizza: Party Room 4",
        "The New & Improved Freddy's Pizza: Kid's Cove",
        "The New & Improved Freddy's Pizza: Women's Restroom",
        "The New & Improved Freddy's Pizza: Party Room 1",
        "The New & Improved Freddy's Pizza: Parts & Service",
        "The New & Improved Freddy's Pizza: Minigame Cabinet",
        "Backdoor Trading - The New & Improved Freddy's Pizza: Game Area",
        "Backdoor Trading - The New & Improved Freddy's Pizza: Party Room 3",
        "Backdoor Trading - The New & Improved Freddy's Pizza: Party Room 2",
    ],
    "Fazbear's Fright": [
        "Fazbear's Fright: CAM 5",
        "Fazbear's Fright: Office",
        "Fazbear's Fright: CAM 8",
        "Fazbear's Fright: CAM 2",
        "Fazbear's Fright: CAM Hall 3-4",
        "Fazbear's Fright: CAM 7",
        "Fazbear's Fright: Alleyway",
        "Fazbear's Fright: Minigame Cabinet",
        "Backdoor Trading - Fazbear's Fright: CAM 8",
        "Backdoor Trading - Fazbear's Fright: Office Hall",
        "Backdoor Trading - Fazbear's Fright: Office Corner",
    ],
    "William's Woods": [
        "William's Woods: Living Room",
        "William's Woods: Dave's Bedroom",
        "William's Woods: Hallway Upstairs",
        "William's Woods: William's Bedroom",
        "William's Woods: Behind Trees",
        "William's Woods: Toolshed",
        "William's Woods: Workshop Upstairs Box",
        "William's Woods: Minigame Cabinet",
        "Backdoor Trading - William's Woods: Elizabeth's Bedroom",
        "Backdoor Trading - William's Woods: Downstairs Bathroom",
        "Backdoor Trading - William's Woods: Upstairs Bathroom",
    ],
    "Circus Baby's Entertainment & Rental": [
        "Circus Baby's Entertainment & Rental: Circus Gallery",
        "Circus Baby's Entertainment & Rental: Ballora Gallery",
        "Circus Baby's Entertainment & Rental: Breaker Room",
        "Circus Baby's Entertainment & Rental: Funtime Auditorium",
        "Circus Baby's Entertainment & Rental: Private Room",
        "Circus Baby's Entertainment & Rental: Scooping Room",
        "Circus Baby's Entertainment & Rental: Minigame Cabinet",
        "Backdoor Trading - Circus Baby's Entertainment & Rental: Ballora Gallery",
        "Backdoor Trading - Circus Baby's Entertainment & Rental: Circus Gallery",
        "Backdoor Trading - Circus Baby's Entertainment & Rental: Private Room",
    ],
    "Ending Route": [
        "Ultimate Ending",
        "Good Ending",
        "Money Ending",
        "Bad Ending",
    ],
}


def create_all_locations(world: Frickbears3ReWorld) -> None:
    """Create all location checks and assign them to appropriate regions."""
    for region_name, location_names in LOCATION_REGIONS.items():
        region: Region = world.get_region(region_name)
        for location_name in location_names:
            location_id = LOCATION_NAME_TO_ID[location_name]
            location = world.create_location(location_name, location_id, region)
            region.locations.append(location)
