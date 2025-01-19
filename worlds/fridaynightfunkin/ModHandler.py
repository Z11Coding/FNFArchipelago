import os
import sys
import ast
import Utils
from typing import Any, List, Dict
from worlds.fridaynightfunkin import FNFBaseList, FunkinUtils

curPlayer: int = 0


def extract_mod_data(player: int) -> Dict[int, List[str]]:
    """
    Extracts mod data from YAML files and converts it to a list of dictionaries.
    """

    user_path = Utils.user_path(Utils.get_settings()["generator"]["player_files_path"])
    folder_path = sys.argv[
        sys.argv.index("--player_files_path") + 1] if "--player_files_path" in sys.argv else user_path

    print(f"Checking YAMLs for songList at {folder_path}")

    if not os.path.isdir(folder_path):
        raise ValueError(f"The path {folder_path} is not a valid directory.")

    # Search text for the specific game
    search_text = "Friday Night Funkin"

    # Search text for the specific list
    search_list = "songList"

    # Regex pattern to capture the outermost braces content
    trueSongList: List[str] = []

    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)

        if os.path.isfile(item_path):
            with open(item_path, 'r', encoding='utf-8') as file:  # Open the file in read mode
                file_content = file.read()

                # Check if the search text (game title) is found in the file
                if search_text in file_content:
                    if search_list in file_content:
                        # Search for all occurrences of 'songList:' and the block within []
                        tempSongList: List[str]
                        tempSongList = file_content.split('\n')
                        for item in tempSongList:
                            if search_list in item:
                                curPlayer = player
                                songsList2ohboyherewego = item.split(':')
                                falseSongList = str(songsList2ohboyherewego[1][2:-1])
                                trueSongList.append(falseSongList)
                                if curPlayer not in FNFBaseList.localSongList:
                                    FNFBaseList.localSongList[curPlayer] = []
                                FNFBaseList.localSongList[curPlayer].append(falseSongList)
                                print(trueSongList)
                                print('Songs for player ' + str(curPlayer) + ": " + str(trueSongList))

    total = len(trueSongList)
    print(f"Found {total} songs")
    return FNFBaseList.localSongList


def get_dict(mod_data, client):
    if client:
        trimmed_data = str(mod_data[8:-1])  # Slicing to remove first and last character
        if trimmed_data == "":
            return None
    else:
        # Remove the first 2 and last 2 characters
        trimmed_data = str(mod_data[2:-2])  # Slicing to remove first and last character
        if trimmed_data == "":
            return ""

    try:
        data_dict = ast.literal_eval(trimmed_data)
    except (ValueError, SyntaxError) as e:
        print(f"Error parsing data: {e}")
        data_dict = {}

    return data_dict
