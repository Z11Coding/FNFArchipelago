from collections import ChainMap
from typing import Dict, List, ClassVar, Type
from .Items import FNFBaseList, SongData
from .Options import *
from .ModHandler import (
    extract_mod_data,
)

class FunkinUtils:
    STARTING_CODE = 6900000

    SHOW_TICKET_NAME: str = "Ticket"
    SHOW_TICKET_CODE: int = STARTING_CODE

    song_items: Dict[str, SongData] = {}
    song_locations: Dict[str, int] = {}
    loc_id_by_index: List[int] = []

    songList: List[str] = []

    trap_items: Dict[str, int] = {
        "Blue Balls Curse": STARTING_CODE + 1,
        "Ghost Chat": STARTING_CODE + 2,
        "SvC Effect": STARTING_CODE + 3,
        "Tutorial Trap": STARTING_CODE + 4,
        "Fake Transition": STARTING_CODE + 5,
    }

    trap_items_but_as_an_array_because_python_thats_why: List[str] = {
        "Blue Balls Curse",
        "Ghost Chat",
        "SvC Effect",
        "Tutorial Trap",
        "Fake Transition"
    }

    filler_items: Dict[str, int] = {
        "Shield": STARTING_CODE + 30,
        "Max HP Up": STARTING_CODE + 31
    }

    filler_item_weights: Dict[str, int] = {
        "Shield": 10,
        "Max HP Up": 3
    }

    item_names_to_id = ChainMap({SHOW_TICKET_NAME: SHOW_TICKET_CODE}, filler_items, trap_items, song_items)
    location_names_to_id = ChainMap(song_locations)
    def __init__(self) -> None:
        item_id_index = self.STARTING_CODE + (len(FNFBaseList.localSongList) + 100)
        self.item_names_to_id = ChainMap({self.SHOW_TICKET_NAME: self.SHOW_TICKET_CODE}, self.filler_items, self.trap_items, self.song_items)
        self.location_names_to_id = ChainMap(self.song_locations)

        mod_data = extract_mod_data()

        for song in mod_data:
            song_name = song
            self.song_items[song_name] = SongData(item_id_index, False, song_name)
            item_id_index += 1

        self.item_names_to_id.update({name: data.code for name, data in self.song_items.items()})

        location_id_index = self.STARTING_CODE
        for name in self.song_items.keys():
            self.song_locations[f"{name}"] = location_id_index
            location_id_index += 1

        # It doesn't work without this?????? why?????
        for name in self.song_items.keys():
            self.song_locations[f"{name}"] = location_id_index
            location_id_index += 1
        print(self.song_items)

    def get_songs_map(self) -> List[str]:
        """Literally just shoves the songs into a list."""
        filtered_list = []

        for songKey in self.song_items.keys():
            filtered_list.append(songKey)
            print(songKey)

        return filtered_list
