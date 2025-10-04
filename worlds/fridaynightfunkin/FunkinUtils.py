from collections import ChainMap
from typing import Dict, List, ClassVar, Type, Tuple, Any
from .SymbolFixer import fix_song_name
import os
from .Items import FNFBaseList, SongData
from .Options import *
import random
from ..AutoWorld import World
from .Yutautil import yutautil_APYaml
import sys
import ast
import Utils

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
        "Resistance Trap": STARTING_CODE + 7,
        "UNO Challenge": STARTING_CODE + 8,
        "Pong Challenge": STARTING_CODE + 9,
        "Song Switch Trap": STARTING_CODE + 10,
        "Opponent Mode Trap": STARTING_CODE + 11,
        "Both Play Trap": STARTING_CODE + 12,
        "Ultimate Confusion Trap": STARTING_CODE + 13,
    }

    normal_items: Dict[str, int] = {
        "Shield": STARTING_CODE + 14,
        "Max HP Up": STARTING_CODE + 15,
        "Max HP Down": STARTING_CODE + 16,
        "Extra Life": STARTING_CODE + 17,
    }

    one_time_items: Dict[str, int] = {
        "Pocket Lens": STARTING_CODE + 18,
    }

    filler_items: Dict[str, int] = {
        "Nothing": STARTING_CODE + 19,
    }

    filler_item_weights: Dict[str, int] = {
        "Nothing": 1
    }

    trap_filler_items: Dict[str, int] = {
        "UNO Color Filler": STARTING_CODE + 20,
        "PONG Dash Mechanic": STARTING_CODE + 21,
    }

    trap_filler_item_weights: Dict[str, int] = {
        "PONG Dash Mechanic": 1
    }

    mapthing:Dict[str, List[str]] = {}
    mod_data: Dict[str, List[str]] = {}
    playerNames:List[str] = []
    songLimits:dict[str, int] = {}

    user_path = Utils.user_path(Utils.get_settings()["generator"]["player_files_path"])
    folder_path = sys.argv[sys.argv.index("--player_files_path") - 1] if "--player_files_path" in sys.argv else user_path

    def extract_song_list(self) -> dict[str, Any]:
        YUtil: yutautil_APYaml
        songlistings: dict[str, list[str]] = {}

        for item in os.listdir(self.folder_path)[::-1]:
            item_path = os.path.join(self.folder_path, item)

            if os.path.isfile(item_path):
                with open(item_path, 'r', encoding='utf-8') as file:  # Open the file in read mode
                    file_content = file.read()

                    # YUtil = yutautil_APYaml(file_content)

                    # print(YUtil.name)
                    # print(YUtil.settings)
                    # songlistings[YUtil.name] = YUtil.getSongList()
                    # self.songLimits[YUtil.name] = YUtil.settings.song_limit

        return songlistings

    def __init__(self) -> None:
        # Don't initialize song-related data here anymore - it's handled at the World class level
        # Just setup the basic item mappings without songs
        self.item_names_to_id = ChainMap(
            {self.SHOW_TICKET_NAME: self.SHOW_TICKET_CODE}, 
            self.filler_items, 
            self.normal_items,
            self.one_time_items,
            self.trap_items
            # Songs will be added by the World class
        )
        self.location_names_to_id = ChainMap()  # Will be populated by World class

        # for song_name, song_data in self.song_items.items():
        #     for j in range(2):
        #         self.song_locations[f"{song_name}-{j}"] = (song_data.code + 1000 * j)
        #     for j in range(3):
        #         self.song_locations[f"Note {j}: {song_name}"] = (song_data.code + 1000 * j + 10000)


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
