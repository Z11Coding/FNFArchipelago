import os
import sys
import ast
import Utils
from typing import Any, List

from worlds.fridaynightfunkin import FNFBaseList

def extract_mod_data() -> list[str]:
    """
    Extracts mod data from YAML files and converts it to a list of dictionaries.
    """
    players: int = 0

    user_path = Utils.user_path(Utils.get_settings()["generator"]["player_files_path"])
    folder_path = sys.argv[sys.argv.index("--player_files_path") + 1] if "--player_files_path" in sys.argv else user_path

    print(f"Checking YAMLs for songList at {folder_path}")

    if not os.path.isdir(folder_path):
        raise ValueError(f"The path {folder_path} is not a valid directory.")

    # Search text for the specific game
    search_text = "Friday Night Funkin"

    # Search text for the specific list
    search_list = "songList"

    # Regex pattern to capture the outermost braces content
    trueSongList: List[str]

    # Initialize an empty list to collect all inputs
    all_mod_data = []

    trueSongList = []
    uniqueSongList: List[str] = []
    dupeSongList: List[str] = []

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
                                songsList2ohboyherewego = item.split(':')
                                falseSongList = str(songsList2ohboyherewego[1][2:-1])

                                for song in falseSongList.split(','):
                                    if song.strip() not in uniqueSongList:
                                        uniqueSongList.append(song)
                                    else:
                                        dupeSongList.append(song)
                                        print(song)
                                player = players + 1
                                players = player
                                for song in uniqueSongList:
                                    trueSongList.append(song)
                                print(trueSongList)


    for i, song in enumerate(trueSongList):
        trueSongList[i] = song.replace('<cOpen>', '{').replace('<cClose>', '}').replace('<sOpen>', '[').replace('<sClose>', ']')

    total = len(trueSongList)
    print(f"Found {total} songs for {players} players.")
    print(f"Found {len(dupeSongList)} duplicate songs.")

    for song in trueSongList:
        FNFBaseList.localSongList.append(song)
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