from typing import NamedTuple, Optional, List
from BaseClasses import Item, ItemClassification


class SongData(NamedTuple):
    """Special data container to contain the metadata of each song to make filtering work."""

    code: Optional[int]
    songID: Optional[int]
    songName: str
    singers: List[str]
    DLC: bool
    modded: bool
    difficulty: Optional[str]
    difficultyRating: Optional[float]


class MegaMixSongItem(Item):
    game: str = "Hatsune Miku Project Diva Mega Mix+"

    def __init__(self, name: str, player: int, data: SongData) -> None:
        super().__init__(name, ItemClassification.progression, data.code, player)


class MegaMixFixedItem(Item):
    game: str = "Hatsune Miku Project Diva Mega Mix+"

    def __init__(self, name: str, classification: ItemClassification, code: Optional[int], player: int) -> None:
        super().__init__(name, classification, code, player)
