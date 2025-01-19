from typing import List, NamedTuple, Optional, Union, Dict
from BaseClasses import Item, ItemClassification

class SongData(NamedTuple):
    code: Optional[int]
    modded: bool
    songName: str

class FNFBaseList:
    items: List[str] = [
        "Shield", "Max HP Up",
        "Note Checks", "Song Checks",
        "Blue Balls Curse", "Ghost Chat", "SvC Effect", "Tutorial Trap", "Fake Transition"
    ]

    item_groups = {
        "Helpers": ["Shield", "Max HP Up"],
        "Targets": ["Note Checks", "Song Checks"],
        "Traps": ["Blue Balls Curse", "Ghost Chat", "SvC Effect", "Tutorial Trap", "Fake Transition"]
    }

    # This is gonna drive me insane
    baseSongList: List[str] = [
        "Tutorial",
        "Bopeebo", "Fresh", "Dad Battle",
        "Spookeez", "South", "Monster",
        "Pico", "Philly Nice", "Blammed",
        "Satin Panties", "High", "Milf",
        "Cocoa", "Eggnog", "Winter Horrorland",
        "Senpai", "Roses", "Thorns",
        "Ugh", "Guns", "Stress",
        "Darnell", "Lit Up", "2Hot", "Blazin",
        "Darnell (BF Mix)",
        'Bopeebo Erect', 'Fresh Erect', 'Dad Battle Erect',
        'Spookeez Erect', 'South Erect',
        'Pico Erect', 'Philly Nice Erect', 'Blammed Erect',
        'Satin Panties Erect', 'High Erect',
        'Cocoa Erect', 'Eggnog Erect',
        'Senpai Erect', 'Roses Erect', 'Thorns Erect',
        'Ugh Erect',
        'Bopeebo (Pico mix)', 'Fresh (Pico mix)', 'Dad Battle (Pico mix)',
        'Spookeez (Pico mix)', 'South (Pico mix)',
        'Pico (Pico mix)', 'Philly Nice (Pico mix)', 'Blammed (Pico mix)',
        'Eggnog (Pico mix)',
        'Ugh (Pico mix)', 'Guns (Pico mix)',
        'Small Argument',
        'Beat Battle',
        'Beat Battle 2'
    ]
    # This is gonna drive me insane
    localSongList: Dict[int, List[str]] = {}

class FunkinItem(Item):
    game: str = "Friday Night Funkin"

    def __init__(self, name: str, player: int, data: Union[SongData]) -> None:
        super().__init__(name, ItemClassification.progression, data.code, player)


class FunkinFixedItem(Item):
    game: str = "Friday Night Funkin"

    def __init__(self, name: str, classification: ItemClassification, code: Optional[int], player: int) -> None:
        super().__init__(name, classification, code, player)