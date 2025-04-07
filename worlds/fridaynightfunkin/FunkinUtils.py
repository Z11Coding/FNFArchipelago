from collections import ChainMap
from typing import Dict, List, ClassVar, Type, Tuple
from .SymbolFixer import fix_song_name

from .Items import FNFBaseList, SongData
from .Options import *
from ..AutoWorld import World


from .Yutautil import YutaUtil, yutautil_CatagorizedMap, yutautil_CollectionUtils, yutautil_ChanceSelector

class FunkinUtils:
    STARTING_CODE = 6900000

    SHOW_TICKET_NAME: str = "Ticket"
    SHOW_TICKET_CODE: int = STARTING_CODE

    song_items: Dict[str, SongData] = {}
    song_things: Dict[str, Dict[str, SongData]] = {}
    song_locations: Dict[str, int] = {}
    loc_id_by_index: List[int] = []


    songList: List[str] = []

    trap_items: Dict[str, int] = {
        "Blue Balls Curse": STARTING_CODE + 1,
        "Ghost Chat": STARTING_CODE + 2,
        "SvC Effect": STARTING_CODE + 3,
        "Tutorial Trap": STARTING_CODE + 4,
        "Fake Transition": STARTING_CODE + 5,
        "Chart Modifier Trap": STARTING_CODE + 6,
    }

    filler_items: Dict[str, int] = {
        "Shield": STARTING_CODE + 30,
        "Max HP Up": STARTING_CODE + 31
    }

    filler_item_weights: Dict[str, int] = {
        "Shield": 10,
        "Max HP Up": 3
    }

    mapthing:Dict[str, List[str]] = {}
    mod_data: Dict[str, List[str]] = {}
    playerNames:List[str] = []

    def __init__(self) -> None:
        item_id_index = self.STARTING_CODE + (len(FNFBaseList.localSongList) + 100)
        self.item_names_to_id = ChainMap({self.SHOW_TICKET_NAME: self.SHOW_TICKET_CODE}, self.filler_items, self.trap_items, self.song_items)
        self.location_names_to_id = ChainMap(self.song_locations)

        from . import extract_mod_data
        mod_data = extract_mod_data()
        playerNames = []

        if mod_data:
            print('Players Detected')
            for name in mod_data.keys():
                playerNames.append(name)
            for name, list in mod_data.items():
                print("Listing Songs for " + name + "\n" + str(list))
                for song in list:
                    cur_song_name = song
                    item_id = item_id_index
                    isModded = cur_song_name.capitalize().replace("-", " ") not in FNFBaseList.baseSongList
                    if cur_song_name in self.song_items.keys():
                        self.song_items[cur_song_name].playerList.append(name)
                    else:
                        self.song_items[cur_song_name] = SongData(item_id, isModded, cur_song_name, name, [])
                        self.song_items[cur_song_name].playerList.append(name)
                        item_id_index += 1
                        print(str(self.song_items[cur_song_name]) + " is Modded: " + str(isModded))
        else:
            playerNames.append("blank")
            for song in FNFBaseList.emptySongList:
                print("No one's playing FNF! Placing Test!")
                cur_song_name = song
                item_id = item_id_index
                isModded = cur_song_name.capitalize().replace("-", " ") not in FNFBaseList.baseSongList
                if cur_song_name in self.song_items.keys():
                    self.song_items[cur_song_name].playerList.append('blank')
                else:
                    self.song_items[cur_song_name] = SongData(item_id, isModded, cur_song_name, 'blank', [])
                    self.song_items[cur_song_name].playerList.append('blank')
                    item_id_index += 1
                    print(str(self.song_items[cur_song_name]) + " is Modded: " + str(isModded))

        self.item_names_to_id.update({name: data.code for name, data in self.song_items.items()})

        for song_name, song_data in self.song_items.items():
            for j in range(2):
                self.song_locations[f"{song_name}-{j}"] = (song_data.code + 1000 * j)


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

    def get_songs_map(self, player_name:str) -> List[str]:
        """Literally just shoves the songs into a list."""
        filtered_list = []

        for songKey, songData in self.song_items.items():
            if songData.playerSongBelongsTo == player_name or player_name in songData.playerList or not songData.modded: #Make sure the right player gets the right songs
                filtered_list.append(songKey)
                #print(songKey)

        return filtered_list
