from __future__ import annotations

from typing import TYPE_CHECKING, Dict

from BaseClasses import Item, ItemClassification

if TYPE_CHECKING:
    from . import Frickbears3ReWorld


# Location Access Items (Progression) - Unlock salvage areas
LOCATION_ACCESS_ITEMS: Dict[str, int] = {
    "Unlock Freddy Fazbear's Pizza": 3300001,
    "Unlock New Freddy Fazbear's Pizza": 3300002,
    "Unlock Fazbear's Fright": 3300003,
    "Unlock William's Woods": 3300004,
}

# Default Animatronics (Available from start, also collectible as items)
DEFAULT_ANIMATRONICS = {"Freddy", "Bonnie", "Chica", "Foxy", "Puppet"}
LUNATIC_MODE_DEFAULT = "Balloon Boy"

# Rescuable Animatronics
# Organized by game/salvage location
ANIMATRONIC_ITEMS: Dict[str, int] = {
    # FNaF 1 / Freddy Fazbear's Pizza
    "Freddy": 3300010,
    "Bonnie": 3300011,
    "Chica": 3300012,
    "Foxy": 3300013,
    "Puppet": 3300014,
    "Balloon Boy": 3300015, # FNAF 2, but for organization purposes, included here
    "Golden Freddy": 3300016,
    "Endoskeleton": 3300017,
    
    # FNaF 2 (Withered) / The New & Improved Freddy's Pizza
    "Old Freddy": 3300020,
    "Old Bonnie": 3300021,
    "Old Chica": 3300022,
    "Old Foxy": 3300023,
    
    # FNaF 2 (Toys)
    "Toy Freddy": 3300024,
    "Toy Bonnie": 3300025,
    "Toy Chica": 3300026,
    "Mangle": 3300027,
    
    # FNaF 2 (Phantoms)
    "Shadow Bonnie": 3300028,
    "Shadow Freddy": 3300029,
    "JJ": 3300030,
    
    # FNaF 3 / Fazbear's Fright
    "Springtrap": 3300040,
    "Phantom Animatronics": 3300041,
    
    # FNaF 4
    "Plush Trap": 3300050,
    "Nightmare Fredbear": 3300051,
    "Nightmare Balloon Boy": 3300052,
    "Nightmarionne": 3300053,
    
    # Sister Location / William's Woods
    "Circus Baby": 3300060,
    "Funtime Freddy": 3300061,
    "Funtime Foxy": 3300062,
    "Ballora": 3300063,
    "Ennard": 3300064,
    "Lolbit": 3300065,
    
    # Ultimate Custom Night / Five Nights at Freddy's: The Twisted Ones
    "Music Man": 3300070,
    "Mr. Hippo": 3300071,
    "Helpy": 3300072,
    "Lefty": 3300073,
    "Scrap Baby": 3300074,
    "Molten Freddy": 3300075,
    "Twisted Wolf": 3300076,
    
    # Ultimate Custom Night / Ultimate Version
    "Mulhair": 3300080,
    "Dreadbear": 3300081,
    
    # Freddy in Space 2
    "LOLZHAX": 3300082,
    
    # Guests
    "Rodney Redbird": 3300090,
    "Animdude": 3300091,
    "Coffee": 3300092,
    "Chipper": 3300093,
    "Candy": 3300094,
    "Popgos": 3300095,
    "Sparky": 3300096,
}

# Ending Items
ENDING_ITEMS: Dict[str, int] = {
    "Ultimate Ending": 3300200,
    "Good Ending": 3300201,
    "Money Ending": 3300202,
    "Bad Ending": 3300203,
}

# Mendo's Shop Items (Token shop)
MENDOS_SHOP_ITEMS: Dict[str, int] = {
    "Mimic Ball": 3300300,
    "King's Prize": 3300301,
    "Rewind Clock": 3300302,
    "Battery Pack": 3300303,
    "Snowcone": 3300304,
    "Golden Cupcake": 3300305,
    "AR Mask": 3300306,
    "Laser Doors": 3300307,
    "Beartrap": 3300308,
    "Deathcoin": 3300309,
    "Distortion Clock": 3300310,
    "Pickles": 3300311,
    "High-Quality Lumber": 3300312,
}

# Upgrade Cadet's Shop Items (Money shop)
CADET_SHOP_ITEMS: Dict[str, int] = {
    "Reroll": 3300400,
    "Fuzzy Dice": 3300401,
    "Upgrade Commander": 3300402,
    "Backdoor Trading": 3300403,
    "Mangle Cartridge": 3300404,
    "Animdude Cartridge": 3300405,
    "Cupcake Cartridge": 3300406,
    "Early Investment": 3300407,
    "Felix's Loan": 3300408,
    "Power AC": 3300409,
    "Superfan": 3300410,
    "All Ears": 3300411,
    "Overcharge": 3300412,
    "Cam Radar": 3300413,
    "Cool Glasses": 3300414,
    "Employee Discount": 3300415,
    "Bear Change": 3300416,
    "Mini Multiplier": 3300417,
    "Retina Burner": 3300418,
    "Head Start": 3300419,
    "Late Start": 3300420,
    "Power Hour": 3300421,
    "Overstock": 3300422,
    "Spawnkiller": 3300423,
    "Talbert's Files": 3300424,
}

# Salvagable Items (one per location - makes animatronics appear at that location)
SALVAGABLE_ITEMS: Dict[str, int] = {
    # Day 1 - Freddy Fazbear's Pizza
    "Salvagable at Freddy Fazbear's Pizza: Show Stage": 3300600,
    "Salvagable at Freddy Fazbear's Pizza: West Hall Supply Closet": 3300601,
    "Salvagable at Freddy Fazbear's Pizza: Women's Restroom": 3300602,
    "Salvagable at Freddy Fazbear's Pizza: Pirate's Cove": 3300603,
    "Salvagable at Freddy Fazbear's Pizza: Kitchen": 3300604,
    "Salvagable at Freddy Fazbear's Pizza: Backstage": 3300605,
    "Salvagable at Freddy Fazbear's Pizza: Safe Room": 3300606,
    
    # Day 2 - The New & Improved Freddy's Pizza
    "Salvagable at The New & Improved Freddy's Pizza: Show Stage": 3300610,
    "Salvagable at The New & Improved Freddy's Pizza: Party Room 3": 3300611,
    "Salvagable at The New & Improved Freddy's Pizza: Party Room 4": 3300612,
    "Salvagable at The New & Improved Freddy's Pizza: Kid's Cove": 3300613,
    "Salvagable at The New & Improved Freddy's Pizza: Women's Restroom": 3300614,
    "Salvagable at The New & Improved Freddy's Pizza: Party Room 1": 3300615,
    "Salvagable at The New & Improved Freddy's Pizza: Parts & Service": 3300616,
    
    # Day 3 - Fazbear's Fright
    "Salvagable at Fazbear's Fright: CAM 5": 3300620,
    "Salvagable at Fazbear's Fright: Office": 3300621,
    "Salvagable at Fazbear's Fright: CAM 8": 3300622,
    "Salvagable at Fazbear's Fright: CAM 2": 3300623,
    "Salvagable at Fazbear's Fright: CAM Hall 3-4": 3300624,
    "Salvagable at Fazbear's Fright: CAM 7": 3300625,
    "Salvagable at Fazbear's Fright: Alleyway": 3300626,
    
    # Day 4 - William's Woods
    "Salvagable at William's Woods: Living Room": 3300630,
    "Salvagable at William's Woods: Dave's Bedroom": 3300631,
    "Salvagable at William's Woods: Hallway Upstairs": 3300632,
    "Salvagable at William's Woods: William's Bedroom": 3300633,
    "Salvagable at William's Woods: Behind Trees": 3300634,
    "Salvagable at William's Woods: Toolshed": 3300635,
    "Salvagable at William's Woods: Workshop Upstairs": 3300636,
    
    # Day 5 - Circus Baby's Entertainment & Rental
    "Salvagable at Circus Baby's Entertainment & Rental: Circus Gallery": 3300640,
    "Salvagable at Circus Baby's Entertainment & Rental: Ballora Gallery": 3300641,
    "Salvagable at Circus Baby's Entertainment & Rental: Breaker Room": 3300642,
    "Salvagable at Circus Baby's Entertainment & Rental: Funtime Auditorium": 3300643,
    "Salvagable at Circus Baby's Entertainment & Rental: Private Room": 3300644,
    "Salvagable at Circus Baby's Entertainment & Rental: Scooping Room": 3300645,
    
    # Backdoor Trading Locations
    "Salvagable at Backdoor Trading - Freddy Fazbear's Pizza: Dining Area": 3300650,
    "Salvagable at Backdoor Trading - Freddy Fazbear's Pizza: Pirate's Cove": 3300651,
    "Salvagable at Backdoor Trading - Freddy Fazbear's Pizza: Men's Restroom": 3300652,
    "Salvagable at Backdoor Trading - The New & Improved Freddy's Pizza: Game Area": 3300653,
    "Salvagable at Backdoor Trading - The New & Improved Freddy's Pizza: Party Room 3": 3300654,
    "Salvagable at Backdoor Trading - The New & Improved Freddy's Pizza: Party Room 2": 3300655,
    "Salvagable at Backdoor Trading - Fazbear's Fright: CAM 8": 3300656,
    "Salvagable at Backdoor Trading - Fazbear's Fright: Office Hall": 3300657,
    "Salvagable at Backdoor Trading - Fazbear's Fright: Office Corner": 3300658,
    "Salvagable at Backdoor Trading - William's Woods: Elizabeth's Bedroom": 3300659,
    "Salvagable at Backdoor Trading - William's Woods: Downstairs Bathroom": 3300660,
    "Salvagable at Backdoor Trading - William's Woods: Upstairs Bathroom": 3300661,
    "Salvagable at Backdoor Trading - Circus Baby's Entertainment & Rental: Ballora Gallery": 3300662,
    "Salvagable at Backdoor Trading - Circus Baby's Entertainment & Rental: Circus Gallery": 3300663,
    "Salvagable at Backdoor Trading - Circus Baby's Entertainment & Rental: Private Room": 3300664,
}

# Filler Items
FILLER_ITEMS: Dict[str, int] = {
    "Token": 3300500,
    "Spare Parts": 3300502,
}

OTHER_ITEMS: Dict[str, int] = {
    "Salvage Contract": 3300700,
}

IN_LOCATION_ITEMS: Dict[str, int] = {
    "Axe": 3300800,
    "Parts & Service Key": 3300801,
    "Fire Exit Key": 3300802,
    "Padlock Key": 3300803,
}

MINIGAMES: Dict[str, int] = {
    "Fredsweeper": 3300900,
    "Air Adventure": 3300901,
    "Chomping With Chica": 3300902,
    "Puppet Patrol": 3300903,
    "Hare Pairs": 3300904,
    "Pirate Plunder": 3300905,
    "Circus Sorter": 3300906,
    "Mangle Tangle Mania": 3300907,
    "Scott's Slots": 3300908,
    "Cupcake Clicker": 3300909,
    "Golden Fredsweeper": 3300910,
}

# Arcade Cabinet Fix Items (Potential Sanity)
ARCADE_CABINET_FIX_ITEMS: Dict[str, int] = {
    "Fix Arcade Cabinet - Freddy Fazbear's Pizza": 3300911,
    "Fix Arcade Cabinet - The New & Improved Freddy's Pizza": 3300912,
    "Fix Arcade Cabinet - Fazbear's Fright": 3300913,
    "Fix Arcade Cabinet - William's Woods": 3300914,
    "Fix Arcade Cabinet - Circus Baby's Entertainment & Rental": 3300915,
}

MASKS: Dict[str, int] = {
    "Freddy Mask": 3301000,
    "Bonnie Mask": 3301001,
    "Chica Mask": 3301002,
    "Foxy Mask": 3301003,
}

PRESENTS: Dict[str, int] = {
    "Freddy Present": 3301100,
    "Bonnie Present": 3301101,
    "Chica Present": 3301102,
    "Foxy Present": 3301103,
    "Present": 3301104,
}

TRAPS: Dict[str, int] = {
    "Breaker Trap": 3301200,
    "Sound Trap": 3301201,
    "Light Out Trap": 3301202,
    "TV Trap": 3301203,
    "Time Trap": 3301204,
    "LOL Ttap": 3301205,
    "Nightmare Trap": 3301206
}

BACKDOOR_TRADING_ITEMS: Dict[str, int] = {
    "Backdoor Trading - Freddy Fazbear's Pizza: Dining Area": 3301300,
    "Backdoor Trading - Freddy Fazbear's Pizza: Pirate's Cove": 3301301,
    "Backdoor Trading - Freddy Fazbear's Pizza: Men's Restroom": 3301302,
    "Backdoor Trading - The New & Improved Freddy's Pizza: Game Area": 3301303,
    "Backdoor Trading - The New & Improved Freddy's Pizza: Party Room 3": 3301304,
    "Backdoor Trading - The New & Improved Freddy's Pizza: Party Room 2": 3301305,
    "Backdoor Trading - Fazbear's Fright: CAM 8": 3301306,
    "Backdoor Trading - Fazbear's Fright: Office Hall": 3301307,
    "Backdoor Trading - Fazbear's Fright: Office Corner": 3301308,
    "Backdoor Trading - William's Woods: Elizabeth's Bedroom": 3301309,
    "Backdoor Trading - William's Woods: Downstairs Bathroom": 3301310,
    "Backdoor Trading - William's Woods: Upstairs Bathroom": 3301311,
    "Backdoor Trading - Circus Baby's Entertainment & Rental: Ballora Gallery": 3301312,
    "Backdoor Trading - Circus Baby's Entertainment & Rental: Circus Gallery": 3301313,
    "Backdoor Trading - Circus Baby's Entertainment & Rental: Private Room": 3301314,
    # Ambiguous.
    "Progressive Backdoor Trading": 3301315,
    # Location Progressive Backdoor Trading Items
    "Progressive Backdoor Trading - Freddy Fazbear's Pizza": 3301316,
    "Progressive Backdoor Trading - The New & Improved Freddy's Pizza": 3301317,
    "Progressive Backdoor Trading - Fazbear's Fright": 3301318,
    "Progressive Backdoor Trading - William's Woods": 3301319,
    "Progressive Backdoor Trading - Circus Baby's Entertainment & Rental": 3301320,
}

LOCATION_KEYS: Dict[str, int] = {
    "Freddy Fazbear's Pizza Key": 3301400,
    "The New & Improved Freddy's Pizza Key": 3301401,
    "Fazbear's Fright Key": 3301402,
    "William's Woods Key": 3301403,
    "Circus Baby's Entertainment & Rental Key": 3301404,
}

QUOTA_ITEMS: Dict[str, int] = {
    "Quota Upgrade - Freddy Fazbear's Pizza": 3301500,
    "Quota Upgrade - The New & Improved Freddy's Pizza": 3301501,
    "Quota Upgrade - Fazbear's Fright": 3301502,
    "Quota Upgrade - William's Woods": 3301503,
    "Quota Upgrade - Circus Baby's Entertainment & Rental": 3301504,
    "Progressive Quota Upgrade": 3301505,
}





# Item ID Master Dictionary
ITEM_NAME_TO_ID: Dict[str, int] = {
    **LOCATION_ACCESS_ITEMS,
    **ANIMATRONIC_ITEMS,
    **ENDING_ITEMS,
    **MENDOS_SHOP_ITEMS,
    **CADET_SHOP_ITEMS,
    **SALVAGABLE_ITEMS,
    **FILLER_ITEMS,
    **OTHER_ITEMS,
    **IN_LOCATION_ITEMS,
    **MINIGAMES,
    **ARCADE_CABINET_FIX_ITEMS,
    **MASKS,
    **PRESENTS,
    **TRAPS,
    **BACKDOOR_TRADING_ITEMS,
    **LOCATION_KEYS,
    **QUOTA_ITEMS,
}

# Item Classifications (progression/useful/filler/trap)
DEFAULT_ITEM_CLASSIFICATIONS: Dict[str, ItemClassification] = {}

# Location Access Items are progression (required to access new areas)
for item_name in LOCATION_ACCESS_ITEMS:
    DEFAULT_ITEM_CLASSIFICATIONS[item_name] = ItemClassification.progression

# Ending Items
DEFAULT_ITEM_CLASSIFICATIONS["Unknown Ending"] = ItemClassification.progression
DEFAULT_ITEM_CLASSIFICATIONS["Good Ending"] = ItemClassification.progression
DEFAULT_ITEM_CLASSIFICATIONS["Money Ending"] = ItemClassification.progression
DEFAULT_ITEM_CLASSIFICATIONS["Bad Ending"] = ItemClassification.progression
DEFAULT_ITEM_CLASSIFICATIONS["Salvage Contract"] = ItemClassification.progression


for item_name in ANIMATRONIC_ITEMS:
    DEFAULT_ITEM_CLASSIFICATIONS[item_name] = ItemClassification.progression_deprioritized

# Shop items - Mix of useful and filler based on importance
# Talbert's Files is needed for Money Ending progression
DEFAULT_ITEM_CLASSIFICATIONS["Talbert's Files"] = ItemClassification.progression

# Mendo's Shop items - Mostly filler with some useful
for item_name in MENDOS_SHOP_ITEMS:
    DEFAULT_ITEM_CLASSIFICATIONS[item_name] = ItemClassification.filler

# Cadet's Shop items - Utility boosts
for item_name in CADET_SHOP_ITEMS:
    if item_name == "Talbert's Files":
        DEFAULT_ITEM_CLASSIFICATIONS[item_name] = ItemClassification.progression
    else:
        DEFAULT_ITEM_CLASSIFICATIONS[item_name] = ItemClassification.useful

# Salvagable items - Location specifiers (filler - determine where animatronics appear)
for item_name in SALVAGABLE_ITEMS:
    DEFAULT_ITEM_CLASSIFICATIONS[item_name] = ItemClassification.filler

# Filler/Token items
for item_name in FILLER_ITEMS:
    DEFAULT_ITEM_CLASSIFICATIONS[item_name] = ItemClassification.filler

# Minigames - Useful for earning tokens in-game
for item_name in MINIGAMES:
    DEFAULT_ITEM_CLASSIFICATIONS[item_name] = ItemClassification.useful

# Arcade Cabinet Fix Items (Cartridges) - Useful for unlocking bonus minigames
for item_name in ARCADE_CABINET_FIX_ITEMS:
    DEFAULT_ITEM_CLASSIFICATIONS[item_name] = ItemClassification.progression


class Frickbears3ReItem(Item):
    """Five Nights at Frickbear's 3 Randomizer Item"""
    game: str = "Five Nights at Frickbear's 3"

    def __init__(self, name: str, classification: ItemClassification, item_id: int, player: int) -> None:
        super().__init__(name, classification, item_id, player)
    def __init__(self, name: str, player: int) -> None:
        super().__init__(name, DEFAULT_ITEM_CLASSIFICATIONS.get(name, ItemClassification.filler), ITEM_NAME_TO_ID[name], player)


def create_item_with_correct_classification(
    world: Frickbears3ReWorld, name: str
) -> Frickbears3ReItem:
    """Create an item with correct classification."""
    item_classification = DEFAULT_ITEM_CLASSIFICATIONS.get(
        name, ItemClassification.filler
    )
    return Frickbears3ReItem(name, item_classification, ITEM_NAME_TO_ID[name], world.player)


def create_all_items(world: Frickbears3ReWorld) -> None:
    """Create and place all items into the world's item pool."""
    # Location Access Items - Always progression
    for name in LOCATION_ACCESS_ITEMS:
        world.itempool.append(create_item_with_correct_classification(world, name))
    
    # Ending Items - One of each
    for name in ENDING_ITEMS:
        world.itempool.append(create_item_with_correct_classification(world, name))
    
    # Animatronics - Add all animatronics to the item pool
    animatronics_to_add = list(ANIMATRONIC_ITEMS.keys())
    
    for name in animatronics_to_add:
        world.itempool.append(create_item_with_correct_classification(world, name))
    
    # Shop Items - Mendo's and Cadet's
    for name in MENDOS_SHOP_ITEMS:
        world.itempool.append(create_item_with_correct_classification(world, name))
    
    for name in CADET_SHOP_ITEMS:
        world.itempool.append(create_item_with_correct_classification(world, name))
    
    # Salvagable Items - Location indicators (one for each salvage location)
    for name in SALVAGABLE_ITEMS:
        world.itempool.append(create_item_with_correct_classification(world, name))
    
    # Calculate remaining slots to fill with filler
    num_locations = len(world.multiworld.get_locations(world.player))
    num_filler_needed = num_locations - len(world.itempool)
    
    for _ in range(max(0, num_filler_needed)):
        filler_name = get_random_filler_item_name(world)
        world.itempool.append(create_item_with_correct_classification(world, filler_name))


def get_random_filler_item_name(world: Frickbears3ReWorld) -> str:
    """Return a filler item name. Currently returns Token for infinite supply."""
    return world.random.choice(list(FILLER_ITEMS.keys()))
