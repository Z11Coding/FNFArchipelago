from collections import ChainMap
from typing import Dict, List, Set, Optional, NamedTuple
from .Options import FunkinOptions
class SongData(NamedTuple):
    """Special data container to contain the metadata of each song to make filtering work.
        yes i stole this from muse dash. leave me alone im trying ;_;
    """
    code: Optional[int]

class FunkinUtils:
    STARTING_CODE = 6900000

    SHOW_TICKET_NAME: str = "Tickets"
    SHOW_TICKET_CODE: int = STARTING_CODE

    song_items: Dict[str, SongData] = {}
    song_locations: Dict[str, int] = {}

    trap_items: Dict[str, int] = {
        "Blue Balls Curse": STARTING_CODE + 1,
        "Ghost Chat": STARTING_CODE + 2,
        "SvC Effect": STARTING_CODE + 3,
        "Tutorial Trap": STARTING_CODE + 4,
        "Fake Transition": STARTING_CODE + 5,
    }

    filler_items: Dict[str, int] = {
        "Shield": STARTING_CODE + 30,
        "Max HP Up": STARTING_CODE + 31
    }

    filler_item_weights: Dict[str, int] = {
        "Shield": 10,
        "Max HP Up": 3
    }

    item_names_to_id: ChainMap = ChainMap({}, filler_items, trap_items)
    location_names_to_id: song_locations

    def __init__(self) -> None:
        self.item_names_to_id[self.SHOW_TICKET_NAME] = self.SHOW_TICKET_CODE

        item_id_index = self.STARTING_CODE + 50
        for song in FunkinOptions.songList:
            song_name = song
            self.song_items[song_name] = SongData(item_id_index)
            item_id_index += 1

        self.item_names_to_id.update({name: data.code for name, data in self.song_items.items()})

        location_id_index = self.STARTING_CODE
        for name in self.song_items.keys():
            self.song_locations[f"{name}"] = location_id_index
            location_id_index += 1