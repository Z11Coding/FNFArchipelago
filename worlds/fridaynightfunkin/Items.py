from typing import List, NamedTuple, Optional, Union
from BaseClasses import Item, ItemClassification

class SongData(NamedTuple):
    code: Optional[int]
    modded: bool
    songName: str
    playerSongBelongsTo: str
    playerList: Optional[List[str]]

class UNOMinigameColor:
    def __init__(self, name: str, color_code: str | int):
        self.name = name
        self.color_code = color_code

class FNFBaseList:
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
        "Darnell (BF Mix)", "Lit Up (BF Mix)",
        'Bopeebo Erect', 'Fresh Erect', 'Dad Battle Erect',
        'Spookeez Erect', 'South Erect',
        'Pico Erect', 'Philly Nice Erect', 'Blammed Erect',
        'Satin Panties Erect', 'High Erect',
        'Cocoa Erect', 'Eggnog Erect',
        'Senpai Erect', 'Roses Erect', 'Thorns Erect',
        'Ugh Erect',
        'Darnell Erect',
		'Bopeebo (Pico Mix)', 'Fresh (Pico mix)', 'Dad Battle (Pico mix)',
		'Spookeez (Pico mix)', 'South (Pico mix)',
		'Pico (Pico mix)', 'Philly Nice (Pico mix)', 'Blammed (Pico mix)',
		'Eggnog (Pico Mix)', 'Cocoa (Pico Mix)',
		'Senpai (Pico mix)', 'Roses (Pico mix)',
		'Ugh (Pico mix)', 'Guns (Pico mix)', 'Stress (Pico Mix)',
        'Test'
        'Small Argument',
        'Beat Battle',
        'Beat Battle 2'
    ]

    # Because it's not allowed to be empty ig
    emptySongList: List[str] = [
        "nosongsavalible",
        "Tutorial",
    ]

    # This is gonna drive me insane
    localSongList: List[str] = []

class FunkinItem(Item):
    game: str = "Friday Night Funkin"

    def __init__(self, name: str, player: int, data: Union[SongData]) -> None:
        super().__init__(name, ItemClassification.progression, data.code, player)

class FunkinUNOMinigameItem(Item):
    game: str = "Friday Night Funkin"

    def __init__(self, name: str, code: Optional[int], player: int, color: UNOMinigameColor) -> None:
        super().__init__(name, ItemClassification.useful, code, player)
        self.color = color


class FunkinFixedItem(Item):
    game: str = "Friday Night Funkin"

    def __init__(self, name: str, classification: ItemClassification, code: Optional[int], player: int) -> None:
        super().__init__(name, classification, code, player)