from collections import ChainMap
from typing import Dict, List, ClassVar, Type, Tuple

from .Items import FNFBaseList, SongData
from .Options import *
from ..AutoWorld import World


from .Yutautil import YutaUtil, yutautil_CatagorizedMap, yutautil_CollectionUtils, yutautil_ChanceSelector

class FunkinUtils:
    STARTING_CODE = 6900000

    SHOW_TICKET_NAME: str = "Ticket"
    SHOW_TICKET_CODE: int = STARTING_CODE

    song_items: dict[str, Dict[str, SongData]] = {}
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
    def __init__(self, current_mod_data) -> None:
        item_id_index = self.STARTING_CODE + (len(FNFBaseList.localSongList) + 100)
        self.item_names_to_id = ChainMap({self.SHOW_TICKET_NAME: self.SHOW_TICKET_CODE}, self.filler_items, self.trap_items, self.song_items)
        self.location_names_to_id = ChainMap(self.song_locations)

        self.mapthing = yutautil_CatagorizedMap()

        self.haxeThing = YutaUtil.runHaxeFunction("""
        trace(context);
        function() { return context; }
        """, self)

        from . import extract_mod_data

        mod_data = extract_mod_data()

        # convert dict to CatagorizedMap.
        for player in mod_data:
            self.mapthing.add(player, mod_data[player])

        print(self.mapthing.toString())

        iterableMapping = self.mapthing.map.h

        print(iterableMapping)

        for player in iterableMapping:
            # self.song_items[player] = []
            for songs in iterableMapping[player]:
                for song in songs:
                    print("Player: " + str(player))
                    print("Song: " + str(song))
                    song_name = song
                    self.song_items.update({player: {song_name: SongData(item_id_index, not song_name in FNFBaseList.baseSongList, song_name)}})
                    item_id_index += 1

        for player, songs in self.song_items.items():
            for song_name, data in songs.items():
                self.item_names_to_id.update({song_name: data.code})
        print(self.item_names_to_id)
        print(yutautil_CollectionUtils.toArray(self.mapthing))
        print("Done with getting songs")

        location_id_index = self.STARTING_CODE
        for name in self.song_items[player].keys():
            self.song_locations[f"{name}"] = location_id_index
            location_id_index += 1

        # It doesn't work without this?????? why?????
        for name in self.song_items[player].keys():
            print("Player: " + str(player))
            print("Song: " + str(name))
            self.song_locations[f"{name}"] = location_id_index
            location_id_index += 1
        print(self.song_items)
        print(self.song_locations)
    def get_songs_with_settings(self, mods: bool, mod_ids: List[int]) -> Tuple[List[str], List[int]]:
        """Gets a list of all songs that match the filter settings. Difficulty thresholds are inclusive."""
        filtered_list = []
        id_list = []
        song_groups = {}

        for songName, data in self.song_items.items():
            song_id = data.code

            # Skip modded song if not intended for this player
            if mods and data.modded and song_id not in mod_ids:
                continue

            # Check if a group for this songID already exists
            if song_id in song_groups:
                # Append the current songData object to the existing group
                song_groups[song_id].append(data)
            else:
                # Create a new group with the current songData object
                song_groups[song_id] = [data]

            for song_id, group in song_groups.items():
                # Find the song_item that matches the selected difficulty
                for song_item in group:
                    # Append the song name to the selected_songs list
                    filtered_list.append(song_item.songName)
                    id_list.append(song_item.code)
                    break  # Stop searching once a match is found

        return filtered_list, id_list

    def get_songs_map(self) -> List[str]:
        """Literally just shoves the songs into a list."""
        filtered_list = []

        for songKey in self.song_items.keys():
            filtered_list.append(songKey)
            #print(songKey)

        return filtered_list
