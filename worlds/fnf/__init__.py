from worlds.AutoWorld import World, WebWorld
from BaseClasses import Region, Item, ItemClassification, Entrance, Tutorial
from typing import List, ClassVar, Type
from math import floor
from Options import PerGameCommonOptions


class FNFWebWorld(WebWorld):
    theme = "partyTime"

    bug_report_page = "https://github.com/Yuta12342/Action-Engine/issues"
    setup_en = Tutorial(
        "Mod Setup and Use Guide",
        "A guide to setting up the Funkipelago on your computer.",
        "English",
        "setup_en.md",
        "setup/en",
        ["Yutamon"]
    )

    tutorials = [setup_en]

class FNFWorld(World):
    """Friday Night Funkin' is a Rhythm Game where you must sing to impress your Girlfriend
    and her Dad to get her love! Find every Item that there is to collect, and reach your
    final Song to win!"""

    # World Options
    game = "Friday Night Funkin"
    options_dataclass: ClassVar[Type[PerGameCommonOptions]] = FNFOptions
    options: FNFOptions

    web = FNFWebWorld()



    # Working Data
    victory_song_name: str = ""
    starting_songs: List[str]
    included_songs: List[str]
    needed_token_count: int

    def __init__(self, world: MultiWorld, player: Int):
        super(FNFWorld, self).__init__(world, player)
        self.song_list = [
            "Tutorial",
            "Bopeebo", 
            "Fresh", 
            "Dad Battle",
            "Spookeez", 
            "South", 
            "Monster",
            "Pico", 
            "Philly Nice", 
            "Blammed",
            "Satin Panties", 
            "High", 
            "Milf",
            "Cocoa", 
            "Eggnog", 
            "Winter Horrorland",
            "Senpai", 
            "Roses", 
            "Thorns",
            "Ugh", 
            "Guns", 
            "Stress"
            # whatever other songs
        ]
