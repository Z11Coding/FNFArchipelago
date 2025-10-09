# Copyright (c) 2022 FelicitusNeko
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT
from BaseClasses import Region, Item, MultiWorld, Tutorial, ItemClassification
from typing import Dict, List, ClassVar, Type, Tuple, TextIO
from Utils import user_path
from worlds.AutoWorld import World, WebWorld
from math import floor
import random
from collections import ChainMap
from .Items import FNFBaseList, SongData, UNOMinigameColor

from .ModHandler import (
    get_player_specific_ids,
    extract_mod_data,
)
from .Items import FunkinItem, FunkinFixedItem
from .Locations import FunkinLocation
from .Options import *
from .FunkinUtils import FunkinUtils

# Custom location data class similar to SongData
class LocationData:
    def __init__(self, code: int, location_name: str, player_owner: str, player_list: List[str],
                 origin_song: str = "", origin_mod: str = "", access_rule_func=None):
        self.code = code
        self.locationName = location_name
        self.playerLocationBelongsTo = player_owner
        self.playerList = player_list.copy() if player_list else []
        self.originSong = origin_song
        self.originMod = origin_mod
        self.accessRuleFunc = access_rule_func


class FunkinWeb(WebWorld):
    tutorials = [Tutorial(
        "Friday Night Funkin Setup Guide",
        "A guide to setting up the Friday Night Funkin Archipelago software on your computer.",
        "English",
        "setup_en.md",
        "setup/en",
        ["Z11Gaming and Yutamon"]
    )]
    theme = "partyTime"
    bug_report_page = "https://github.com/Z11Coding/Mixtape-Engine/issues"
    option_groups = fnf_option_groups


class FunkinWorld(World):
    """
        Friday Night Funkin' is a rhythm game in which
        the player controls a character called Boyfriend,
        who must defeat a series of opponents to continue dating
        his significant other, Girlfriend. Now infused with the chaotic world
        of Archipelago.
    """

    game = "Friday Night Funkin"
    web = FunkinWeb()

    required_client_version = (0, 5, 0)
    topology_present = False
    options: FunkinOptions
    options_dataclass: ClassVar[Type[PerGameCommonOptions]] = FunkinOptions
    origin_region_name = "Freeplay"

    victory_song_name: str = ""
    victory_song_id: int
    location_count: int
    songList: List[str]
    excludedSongs: List[str]

    unlock_type:str
    unlock_method:str

    fnfUtil = FunkinUtils()
    filler_item_names = list(fnfUtil.filler_items.keys())
    filler_item_weights = list(fnfUtil.filler_item_weights.values())

    available_uno_colors: List[UNOMinigameColor] = [
        UNOMinigameColor("Red", "FF0000"),
        UNOMinigameColor("Green", "00FF00"),
        UNOMinigameColor("Blue", "0000FF"),
        UNOMinigameColor("Yellow", "FFFF00"),
        # Non-standard colors
        UNOMinigameColor("Pink", "FFC0CB"),
        UNOMinigameColor("Purple", "800080"),
        UNOMinigameColor("Orange", "FFA500"),
        UNOMinigameColor("Cyan", "00FFFF"),
        UNOMinigameColor("Magenta", "FF00FF"),
        UNOMinigameColor("Lime", "00FF7F"),
        UNOMinigameColor("Brown", "A52A2A"),
    ]

    used_uno_colors: List[UNOMinigameColor] = []

    @staticmethod
    def stuff():
        """Setup all item and location IDs for all players during class creation"""

        import Utils
        from .Yutautil import yutautil_APYaml
        import sys
        import os
        fnfUtil = FunkinUtils()

        # Get all player YAML files
        user_path = Utils.user_path(Utils.get_settings()["generator"]["player_files_path"])
        folder_path = sys.argv[
            sys.argv.index("--player_files_path") - 1] if "--player_files_path" in sys.argv else user_path

        if not os.path.isdir(folder_path):
            raise ValueError(f"The path {folder_path} is not a valid directory.")

        # Load all FNF YAML files
        all_yamls = []
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            if os.path.isfile(item_path):
                try:
                    with open(item_path, 'r', encoding='utf-8') as file:
                        file_content = file.read()
                        yaml = yutautil_APYaml(file_content)
                        if yaml.game == "Friday Night Funkin":
                            all_yamls.append(yaml)
                except Exception as e:
                    print(f"Error reading YAML file {item}: {e}")
                    continue

        if not all_yamls:
            print("No FNF YAML files found, using default songs")
            # Create a default YAML for fallback
            all_yamls = []

        # Load custom logic files and execute them
        custom_items = []
        custom_trap_items = []
        custom_locations = {}
        custom_access_rules = {}
        custom_location_data = {}
        custom_song_additions = []  # Track songs added by scripts
        custom_song_exclusions = []  # Track songs excluded by scripts
        vip_exclusive_song_additions:dict[str, list[str]] = {}

        print("Loading custom AP logic files...")

        # First, collect all player names from YAML files
        player_names = set()
        for yaml_data in all_yamls:
            if hasattr(yaml_data, 'name'):
                player_names.add(yaml_data.name)

        # Check if fnfModData folder exists and use it if available
        folder_path = f"{folder_path}\\fnfModData" if os.path.exists(f"{folder_path}\\fnfModData") and os.path.isdir(f"{folder_path}\\fnfModData") else folder_path

        # First, process modData from YAML files (embedded compressed Python code)
        print("Processing modData from YAML files...")
        import base64
        for yaml_data in all_yamls:
            if hasattr(yaml_data, 'modData') and yaml_data.modData:
                player_name = getattr(yaml_data, 'name', 'Unknown Player')
                try:
                    print(f"Processing embedded modData for player '{player_name}'")

                    # Decode Base64 compressed Python script
                    compressed_script = yaml_data.modData
                    custom_script = base64.b64decode(compressed_script).decode('utf-8')

                    # Create execution environment
                    exec_globals = {}
                    exec_locals = {}

                    # Execute the custom script
                    exec(custom_script, exec_globals, exec_locals)

                    # Get the custom data - check for new class-based approach first
                    custom_data = None
                    if 'INSTANCE' in exec_locals:
                        # New class-based approach
                        instance = exec_locals['INSTANCE']
                        if hasattr(instance, 'get_custom_data_for_class'):
                            custom_data = instance.get_custom_data_for_class()
                    elif 'get_custom_data_for_class' in exec_locals:
                        # Legacy function-based approach
                        custom_data = exec_locals['get_custom_data_for_class']()

                    if custom_data:
                        # Store player-specific data WITHOUT prefixes
                        player_items = custom_data.get('items', [])
                        player_locations = custom_data.get('locations', {})  # Now contains location objects with rules

                        # Add items without player prefix - ownership will be tracked in LocationData
                        for item_name in player_items:
                            if item_name not in custom_items:  # Avoid duplicates
                                custom_items.append(item_name)

                        # Add trap items without player prefix - ownership will be tracked in LocationData
                        player_trap_items = custom_data.get('trap_items', [])
                        for trap_name in player_trap_items:
                            if trap_name not in custom_trap_items:  # Avoid duplicates
                                custom_trap_items.append(trap_name)

                        # Track song additions and exclusions from scripts
                        player_song_additions = custom_data.get('song_additions', [])
                        player_song_exclusions = custom_data.get('song_exclusions', [])
                        custom_song_additions.extend(player_song_additions)
                        custom_song_exclusions.extend(player_song_exclusions)
                        vip_exclusive_song_additions[player_name] = player_song_additions

                        for yaml in all_yamls:
                            if yaml.name == player_name:
                                for song in player_song_additions:
                                    yaml.settings.songList.append(song['name'])

                        # Store location data with ownership tracking (no prefixes)
                        for location_name, location_obj in player_locations.items():
                            # Add player info to location data
                            location_info_with_player = location_obj.copy()
                            location_info_with_player['player'] = player_name
                            custom_location_data[location_name] = location_info_with_player

                        print(f"Loaded from embedded modData: {len(player_items)} custom items and {len(player_locations)} custom locations for player '{player_name}'")

                except Exception as e:
                    print(f"Error processing embedded modData for player '{player_name}': {e}")
                    continue

        # Look for player-specific custom data files
        for item in os.listdir(folder_path):
            if item.endswith("_customFNFData.py"):
                # Extract player name from filename
                player_name = item[:-len("_customFNFData.py")]

                # Only load if this player has a YAML file or if it's a general file
                if player_name in player_names or not player_names:
                    custom_file_path = os.path.join(folder_path, item)
                    try:
                        print(f"Loading custom logic for player '{player_name}' from: {item}")
                        with open(custom_file_path, 'r', encoding='utf-8') as file:
                            custom_script = file.read()

                        # Create execution environment
                        exec_globals = {}
                        exec_locals = {}

                        # Execute the custom script
                        exec(custom_script, exec_globals, exec_locals)

                        # Get the custom data - check for new class-based approach first
                        custom_data = None
                        if 'INSTANCE' in exec_locals:
                            # New class-based approach
                            instance = exec_locals['INSTANCE']
                            if hasattr(instance, 'get_custom_data_for_class'):
                                custom_data = instance.get_custom_data_for_class()
                        elif 'get_custom_data_for_class' in exec_locals:
                            # Legacy function-based approach
                            custom_data = exec_locals['get_custom_data_for_class']()

                        if custom_data:

                            # Store player-specific data WITHOUT prefixes
                            player_items = custom_data.get('items', [])
                            player_locations = custom_data.get('locations', {})  # Now contains location objects with rules

                            # Add items without player prefix - ownership will be tracked in LocationData
                            for item_name in player_items:
                                if item_name not in custom_items:  # Avoid duplicates
                                    custom_items.append(item_name)

                            # Add trap items without player prefix - ownership will be tracked in LocationData
                            player_trap_items = custom_data.get('trap_items', [])
                            for trap_name in player_trap_items:
                                if trap_name not in custom_trap_items:  # Avoid duplicates
                                    custom_trap_items.append(trap_name)

                            # Track song additions and exclusions from scripts
                            player_song_additions = custom_data.get('song_additions', [])
                            player_song_exclusions = custom_data.get('song_exclusions', [])
                            custom_song_additions.extend(player_song_additions)
                            custom_song_exclusions.extend(player_song_exclusions)
                            vip_exclusive_song_additions[player_name] = player_song_additions

                            for yaml in all_yamls:
                                if yaml.name == player_name:
                                    for song in player_song_additions:
                                        yaml.settings.songList.append(song['name'])

                            # Store location data with ownership tracking (no prefixes)
                            for location_name, location_obj in player_locations.items():
                                # Add player info to location data
                                location_info_with_player = location_obj.copy()
                                location_info_with_player['player'] = player_name
                                custom_location_data[location_name] = location_info_with_player

                            print(f"Loaded {len(player_items)} custom items and {len(player_locations)} custom locations for player '{player_name}'")

                    except Exception as e:
                        print(f"Error loading custom logic from {item}: {e}")
                        continue

        # Initialize class-level data
        song_items = {}
        song_locations = {}
        custom_location_items = {}  # New: store LocationData objects
        item_name_to_id = {}
        location_name_to_id = {}
        item_id_index = fnfUtil.STARTING_CODE + 100

        # Process all songs from all players
        all_songs = set()

        # Collect all unique songs from all players
        for yaml_data in all_yamls:
            # Check if the YAML has a valid song list
            song_list = yaml_data.getSongList() if hasattr(yaml_data, 'getSongList') else None
            player_name = getattr(yaml_data, 'name', 'Unknown Player')

            if not song_list or len(song_list) == 0:
                # Check if this is an automated generation (Universal Tracker)
                is_automated = getattr(self.multiworld, 'gen_is_fake', False)
                
                if is_automated:
                    # Automatically use base game songs for Universal Tracker
                    print(f"Auto-fixing: Player '{player_name}' has no song list, automatically adding base game songs (Universal Tracker mode)")
                    choice = "1"  # Automatically choose option 1
                else:
                    print(f"\nWarning: Player '{player_name}' has no song list or an empty song list in their YAML file.")
                    print("Options:")
                    print("1. Continue generation with base game songs")
                    print("2. Skip this player (will cancel generation)")
                    choice = None

                while True:
                    if is_automated:
                        choice = "1"  # Auto-select for automated generation
                        break
                    else:
                        choice = input(f"What would you like to do for player '{player_name}'? (1/2): ").strip()
                    
                    if choice == "1":
                        print(f"Continuing generation for '{player_name}' with base game songs.")
                        # Add base game songs to the YAML's song list
                        if hasattr(yaml_data, 'settings') and hasattr(yaml_data.settings, 'songList'):
                            if not yaml_data.settings.songList:
                                yaml_data.settings.songList = FNFBaseList.omegaList.copy()
                            else:
                                yaml_data.settings.songList.extend(FNFBaseList.omegaList)
                        else:
                            # Create settings and songList if they don't exist
                            if not hasattr(yaml_data, 'settings'):
                                yaml_data.settings = type('Settings', (), {})()  
                            yaml_data.settings.songList = FNFBaseList.omegaList.copy()

                        # Now get the updated song list
                        song_list = yaml_data.getSongList()
                        break
                    elif choice == "2":
                        raise ValueError(f"Player '{player_name}' has an empty or invalid song list in their YAML file. Generation cannot continue.")
                    else:
                        print("Invalid choice. Please enter 1 or 2.")
                        
            if song_list:
                for song in song_list:
                    # Clean the song name
                    cleaned_song = song.strip().replace('<cOpen>', '{').replace('<cClose>', '}').replace('<sOpen>', '[').replace('<sClose>', ']').strip()

                    all_songs.add(cleaned_song)

        # Add fallback songs if no custom songs found
        if not all_songs:
            all_songs.update(FNFBaseList.omegaList)

        print(f"Found {len(all_songs)} unique songs across all players: {list(all_songs)}")

        # Track all used item IDs to prevent overlaps
        used_item_ids = set()
        
        # Add existing item IDs to the tracking set
        used_item_ids.add(fnfUtil.SHOW_TICKET_CODE)
        used_item_ids.update(fnfUtil.filler_items.values())
        used_item_ids.update(fnfUtil.normal_items.values())
        used_item_ids.update(fnfUtil.one_time_items.values())
        used_item_ids.update(fnfUtil.trap_items.values())
        
        # Create SongData for all songs
        for song in all_songs:
            cur_song_name = song
            # Ensure song item ID doesn't conflict with existing items
            while item_id_index in used_item_ids:
                item_id_index += 1
                
            item_id = item_id_index
            # isModded = cur_song_name.capitalize().replace("-", " ") not in FNFBaseList.baseSongList
            isModded = True

            if not isModded:
                continue

            # Create song data - we'll assign players later
            song_items[cur_song_name] = SongData(
                item_id,
                isModded,
                cur_song_name,
                "",  # Will be set per-instance
                []  # Will be populated per-instance
            )
            used_item_ids.add(item_id)
            item_id_index += 1

        # Create all possible locations for all songs
        # Use a reasonable starting point and sequential allocation to prevent overlaps
        used_location_ids = set()  # Track all used location IDs to prevent duplicates
        location_id_counter = item_id_index + 1  # Start location IDs after item IDs
        
        for song_name, song_data in song_items.items():
            # Song completion locations
            for j in range(2):
                while location_id_counter in used_location_ids:
                    location_id_counter += 1
                location_id = location_id_counter
                song_locations[f"{song_name}-{j}"] = location_id
                used_location_ids.add(location_id)
                location_id_counter += 1

            # Note check locations
            for j in range(3):
                while location_id_counter in used_location_ids:
                    location_id_counter += 1
                location_id = location_id_counter
                song_locations[f"Note {j}: {song_name}"] = location_id
                used_location_ids.add(location_id)
                location_id_counter += 1

        # Create custom locations using LocationData objects - start after song locations
        current_custom_id = location_id_counter + 100  # Small gap after song locations

        # Group custom locations by location name to track ownership
        location_ownership = {}
        for location_name, location_info in custom_location_data.items():
            player_owner = location_info.get('player', '')

            if location_name not in location_ownership:
                # Ensure this custom location ID is unique
                while current_custom_id in used_location_ids:
                    current_custom_id += 1
                    
                location_ownership[location_name] = {
                    'id': current_custom_id,
                    'players': [],
                    'origin_song': location_info.get('origin_song', ''),
                    'origin_mod': location_info.get('origin_mod', ''),
                    'access_rule': location_info.get('access_rule')  # Rule is now part of location object
                }
                used_location_ids.add(current_custom_id)
                current_custom_id += 1

            # Add player to ownership list
            if player_owner and player_owner not in location_ownership[location_name]['players']:
                location_ownership[location_name]['players'].append(player_owner)

        # Create LocationData objects for custom locations with validation
        for location_name, ownership_info in location_ownership.items():
            # Validate location - skip if name or origin song is null/empty
            if not location_name or not location_name.strip():
                print(f"Skipping invalid location: empty name")
                continue

            origin_song = ownership_info['origin_song']
            if not origin_song or not origin_song.strip():
                print(f"Skipping invalid location '{location_name}': empty origin song")
                continue

            # Check for duplicate location names and resolve conflicts
            duplicate_suffix = 1
            original_location_name = location_name
            while location_name in custom_location_items:
                location_name = f"{original_location_name}_{duplicate_suffix}"
                duplicate_suffix += 1
                print(f"Resolved duplicate location name: {original_location_name} -> {location_name}")

            custom_location_items[location_name] = LocationData(
                ownership_info['id'],
                location_name,
                ownership_info['players'][0] if ownership_info['players'] else "",  # Primary owner
                ownership_info['players'],  # All players who can access
                ownership_info['origin_song'],
                ownership_info['origin_mod'],
                ownership_info['access_rule']
            )
            # Add to location name-to-id mapping
            custom_locations[location_name] = ownership_info['id']

        # Add custom items with their own IDs - ensure no conflicts with existing items
        custom_item_ids = {}
        # Start custom item IDs after the current highest item ID with a small gap
        current_item_id = max(used_item_ids) + 100 if used_item_ids else item_id_index + 100
        
        for item_name in custom_items:
            # Ensure this custom item ID doesn't conflict with any existing item
            while current_item_id in used_item_ids:
                current_item_id += 1
            custom_item_ids[item_name] = current_item_id
            used_item_ids.add(current_item_id)
            current_item_id += 1

        # Add custom trap items with their own IDs - start after custom items
        custom_trap_item_ids = {}
        for item_name in custom_trap_items:
            # Ensure this custom trap item ID doesn't conflict with any existing item
            while current_item_id in used_item_ids:
                current_item_id += 1
            custom_trap_item_ids[item_name] = current_item_id
            used_item_ids.add(current_item_id)
            current_item_id += 1

        # Build final name-to-ID mappings
        item_name_to_id = dict(ChainMap(
            {fnfUtil.SHOW_TICKET_NAME: fnfUtil.SHOW_TICKET_CODE},
            fnfUtil.filler_items,
            fnfUtil.normal_items,
            fnfUtil.one_time_items,
            fnfUtil.trap_items,
            fnfUtil.trap_filler_items,
            {name: data.code for name, data in song_items.items()},
            custom_item_ids,  # Add custom items
            custom_trap_item_ids  # Add custom trap items
        ))

        # Validate that all item IDs are unique
        all_item_ids = list(item_name_to_id.values())
        unique_item_ids = set(all_item_ids)
        if len(all_item_ids) != len(unique_item_ids):
            print(f"ERROR: Found {len(all_item_ids) - len(unique_item_ids)} duplicate item IDs!")
            # Find and report duplicates
            seen_ids = set()
            duplicates = set()
            for item_name, item_id in item_name_to_id.items():
                if item_id in seen_ids:
                    duplicates.add(item_id)
                    print(f"Duplicate item ID {item_id} used by item: {item_name}")
                seen_ids.add(item_id)
            if duplicates:
                raise ValueError(f"Found duplicate item IDs: {duplicates}")
        
        print(f"All item IDs are unique: {len(unique_item_ids)} unique item IDs")
        print(item_name_to_id)

        location_name_to_id = dict(ChainMap(
            song_locations,
            custom_locations  # Add custom locations
        ))

        # Validate that all location IDs are unique
        all_location_ids = list(location_name_to_id.values())
        unique_location_ids = set(all_location_ids)
        if len(all_location_ids) != len(unique_location_ids):
            print(f"ERROR: Found {len(all_location_ids) - len(unique_location_ids)} duplicate location IDs!")
            # Find and report duplicates
            seen_ids = set()
            duplicates = set()
            for loc_name, loc_id in location_name_to_id.items():
                if loc_id in seen_ids:
                    duplicates.add(loc_id)
                    print(f"Duplicate ID {loc_id} used by location: {loc_name}")
                seen_ids.add(loc_id)
            if duplicates:
                raise ValueError(f"Found duplicate location IDs: {duplicates}")

        # Store YAML data for instances to use
        _all_yamls = all_yamls
        _class_data_initialized = True

        print(f"Initialized {len(item_name_to_id)} items and {len(location_name_to_id)} locations")
        print(f"All item IDs are unique: {len(unique_item_ids)} unique item IDs")
        print(f"All location IDs are unique: {len(unique_location_ids)} unique location IDs")
        print(f"Custom data: {len(custom_items)} items, {len(custom_trap_items)} trap items, {len(custom_locations)} locations")

        return {
            "items": item_name_to_id,
            "locations": location_name_to_id,
            "custom_access_rules": custom_access_rules,  # Legacy, will be removed
            "custom_location_data": custom_location_data,  # Legacy, will be removed
            "custom_items": custom_items,
            "custom_trap_items": custom_trap_items,  # New: custom trap items
            "custom_location_items": custom_location_items,  # New LocationData objects
            "custom_song_additions": custom_song_additions,  # Songs added by scripts
            "custom_song_exclusions": custom_song_exclusions,  # Songs excluded by scripts
            "song_items": song_items,
            "song_locations": song_locations,
            "all_yamls": _all_yamls,
            "vip_songs": vip_exclusive_song_additions
        }

    # These will be populated during class creation in __new__
    yaml_data = stuff()
    item_name_to_id = yaml_data["items"]
    location_name_to_id = yaml_data["locations"]
    song_items: dict[str, SongData] = yaml_data.get("song_items", {})
    song_locations: dict[str, int] = yaml_data.get("song_locations", {})
    all_yamls = yaml_data["all_yamls"]
    player_song_additions:dict[str, list[str]] = yaml_data["vip_songs"]

    # Custom data from loaded scripts
    custom_access_rules = yaml_data.get("custom_access_rules", {})  # Legacy - will be removed
    custom_location_data = yaml_data.get("custom_location_data", {})  # Legacy - will be removed
    custom_items_list = yaml_data.get("custom_items", [])
    custom_trap_items_list = yaml_data.get("custom_trap_items", [])  # New: custom trap items
    custom_location_items: Dict[str, LocationData] = yaml_data.get("custom_location_items", {})
    custom_song_additions = yaml_data.get("custom_song_additions", [])  # Songs added by scripts
    custom_song_exclusions = yaml_data.get("custom_song_exclusions", [])  # Songs excluded by scripts

    # Temporary storage for setup
    items_in_general: dict[str, int] = {}
    trap_items_weights: dict[str, int] = {}
    filter_items_weights: dict[str, int] = {}
    items_weights: dict[str, int] = {}
    songLimit: int
    item_id_index: int = 0
    songlistforthe83rdtime: list[str] = []


    def __new__(cls, multiworld: MultiWorld, player: int):
        # Setup class data if not already done
        instance = super(FunkinWorld, cls).__new__(cls)

        player_name = ''
        # Find this player's YAML
        try:
            player_name = multiworld.player_name[player]
        except:
            player_name = cls.all_yamls[player].name

        player_yaml = None

        for yaml_data in cls.all_yamls:
            if yaml_data.name == player_name:
                player_yaml = yaml_data
                break

        if not player_yaml:
            print(f"No YAML found for player {player_name}, using defaults")
            # Create a minimal YAML with defaults
            class DefaultYAML:
                def __init__(self):
                    self.name = player_name
                    self.game = "Friday Night Funkin"
                    self.settings = type('Settings', (), {
                        'songList': FNFBaseList.omegaList.copy(),
                        'song_limit': 5
                    })()
                def getSongList(self):
                    return self.settings.songList
            player_yaml = DefaultYAML()

        instance.thisYaml = player_yaml
        instance.yamlList = cls.all_yamls
        instance.original_song_list = player_yaml.getSongList() or []

        print(f"Created FunkinWorld instance for player {player_name} with {len(instance.original_song_list)} songs")

        return instance

    def __init__(self, multiworld: MultiWorld, player: int):
        # print("Building FunkinWorld...")
        super(FunkinWorld, self).__init__(multiworld, player)
        # print("Building FunkinWorld...")

        # Initialize core attributes
        self.playable_songs = []
        self.mods_enabled = AllowMods.default
        self.starting_song = SongStarter.default
        self.unlock_type = UnlockType.default
        self.unlock_method = UnlockMethod.default
        self.trapAmount = trapAmount.default
        self.bbc_weight = bbcWeight.default
        self.ghost_chat_weight = ghostChatWeight.default
        self.svc_effect_weight = svcWeight.default
        self.tutorial_trap_weight = tutorialWeight.default
        self.fake_transition_weight = fakeTransWeight.default
        self.chart_modifier_change_chance = chartModWeight.default
        self.ticket_percentage = TicketPercentage.default
        self.ticket_win_percentage = TicketWinPercentage.default
        self.graderequirement = gradeNeeded.default
        self.accrequirement = accuracyNeeded.default
        self.checksPerSong = CheckCount.default

        # Initialize instance-specific tracking (don't overwrite class data)
        self.trap_items_weights = {}
        self.filter_items_weights = {}
        self.items_in_general = {}
        self.songLimit = 5

        # Initialize custom song modification tracking
        self._custom_song_additions = self.custom_song_additions.copy()
        self._custom_song_exclusions = self.custom_song_exclusions.copy()

        # Check if songList is empty and use thisYaml's songList if so
        if not hasattr(self, 'songList') or not self.songList:
            yaml_song_list = getattr(self, 'original_song_list', [])
            if yaml_song_list:
                self.songList = yaml_song_list.copy()
            else:
                self.songList = []

    def generate_early(self):
        # Basic Settings
        self.mods_enabled = self.options.mods_enabled.value
        self.starting_song = self.options.starting_song.value
        self.unlock_type = self.options.unlock_type.value.copy().pop()
        self.unlock_method = self.options.unlock_method.value.copy().pop()

        # Trap Settings
        self.trapAmount = self.options.trapAmount.value
        self.trap_items_weights['Blue Balls Curse'] = self.options.bbcWeight.value
        self.trap_items_weights['Ghost Chat'] = self.options.ghostChatWeight.value
        self.trap_items_weights['SvC Effect'] = self.options.svcWeight.value
        self.trap_items_weights['Tutorial Trap'] = self.options.tutorialWeight.value
        self.trap_items_weights['Song Switch Trap'] = self.options.songSwitchWeight.value
        self.trap_items_weights['Opponent Mode Trap'] = self.options.opponentWeight.value
        self.trap_items_weights['Both Play Trap'] = self.options.bothWeight.value
        self.trap_items_weights['Ultimate Confusion Trap'] = self.options.ultconfusion.value
        self.trap_items_weights['Fake Transition'] = self.options.fakeTransWeight.value
        self.trap_items_weights['Chart Modifier Trap'] = self.options.chart_modifier_change_chance.value
        self.trap_items_weights['Resistance Trap'] = self.options.resistanceWeight.value
        self.trap_items_weights['UNO Challenge'] = self.options.unoWeight.value
        self.trap_items_weights['Pong CHALLENGE'] = self.options.pongWeight.value

        self.items_in_general['Shield'] = self.options.shieldWeight.value
        self.items_in_general['Max HP Up'] = self.options.MHPWeight.value
        self.items_in_general['Max HP Down'] = self.options.MHPDWeight.value
        self.items_in_general['Extra Life'] = self.options.extralifeWeight.value

        self.filter_items_weights['Nothing'] = self.fnfUtil.filler_item_weights['Nothing']
        self.filter_items_weights['PONG Dash Mechanic'] = self.fnfUtil.trap_filler_item_weights['PONG Dash Mechanic']

        # Other Settings
        self.ticket_percentage = self.options.ticket_percentage.value
        self.ticket_win_percentage = self.options.ticket_win_percentage.value
        self.graderequirement = self.options.graderequirement.value
        self.accrequirement = self.options.accrequirement.value
        self.checksPerSong = self.options.check_count.value
        self.songLimit = self.options.song_limit.value

        # Process song list with proper randomization and limiting
        self._process_song_list()

        # Generate locations for the finalized song list
        self._generate_song_locations()

        # Choose victory song and create song pool
        self._setup_victory_song_and_pool()



    def _process_song_list(self):
        """Process the song list with randomization and limiting using pre-initialized class data"""
        # Get the original song list from YAML
        raw_song_list = getattr(self, 'original_song_list', [])
        for song in self.yaml_data['custom_song_additions']:
            raw_song_list.append(song['name'])
        # If no songs in YAML, use fallback
        if not raw_song_list:
            raw_song_list = FNFBaseList.omegaList.copy()
            print(f"No songs found for player {self.player_name}, using fallback songs")

        # Clean the song names
        def remove_YAML_formatting(song_list: List[str]) -> List[str]:
            """Remove YAML formatting from the song list"""
            if not song_list:
                return []

            cleaned_list = []
            for song in song_list:
                cleaned_song = song.strip().replace('<cOpen>', '{').replace('<cClose>', '}').replace('<sOpen>', '[').replace('<sClose>', ']').strip()
                cleaned_list.append(cleaned_song)

            return cleaned_list

        cleaned_song_list = remove_YAML_formatting(raw_song_list)

        # Filter to only include songs that exist in our class-level song_items
        available_songs = [song for song in cleaned_song_list if song in self.song_items]

        # Add any missing base songs that should be available to all players
        for song in FNFBaseList.omegaList:
            if song in self.song_items and song not in available_songs:
                available_songs.append(song)

        if not available_songs:
            # Emergency fallback - use any song from class data
            available_songs = remove_YAML_formatting(list(self.song_items.keys())[:5])
            print(f"Emergency fallback: Using first 5 songs from class data for {self.player_name}")

        # Randomize the song list
        self.random.shuffle(available_songs)

        print(available_songs)

        songcheck: list[str] = []
        if getattr(self.thisYaml.settings, 'starting_song', ''):
            songcheck.append(self.thisYaml.settings.starting_song)

        if getattr(self.thisYaml.settings, 'victory_song', ''):
            songcheck.append(self.thisYaml.settings.victory_song)

        # Apply song limit
        song_limit = max(1, getattr(self.thisYaml.settings, 'song_limit', self.songLimit) or 5)
        limited_song_list = available_songs if getattr(self.multiworld, 'gen_is_fake', False) else available_songs[:song_limit-songcheck.__len__()]

        print(f"Processing {len(limited_song_list)} songs for player {self.player_name}: {limited_song_list}")

        for song in songcheck:
            if limited_song_list and song not in limited_song_list:
                limited_song_list.append(song)

        if len(limited_song_list) < song_limit:
            # Fill up to song_limit with random songs not already in the list
            missing_count = song_limit - len(limited_song_list)
            candidates = [s for s in available_songs if s not in limited_song_list]
            self.random.shuffle(candidates)
            for song in candidates:
                if len(limited_song_list) >= song_limit:
                    break
            limited_song_list.append(song)

        # Update the song ownership in the existing SongData objects
        for song_name in limited_song_list:
            if song_name in self.song_items:
                song_data = self.song_items[song_name]
                # Update the player ownership
                if self.player_name not in song_data.playerList:
                    song_data.playerList.append(self.player_name)
                # Set primary owner if not set
                if not song_data.playerSongBelongsTo:
                    # Create a new SongData with updated ownership
                    self.song_items[song_name] = SongData(
                        song_data.code,
                        song_data.modded,
                        song_data.songName,
                        self.player_name,
                        song_data.playerList.copy()
                    )

        print(f"Updated song ownership for {len(limited_song_list)} songs")

        # Validate custom locations against song limit
        self._validate_custom_locations_against_song_limit(limited_song_list)

    def _validate_custom_locations_against_song_limit(self, available_songs: List[str]):
        """Validate that custom locations don't reference songs that were cut by song limit"""
        # Keep track of invalid locations but DON'T remove them from mappings
        # This maintains ID stability while preventing location creation
        self.invalid_custom_locations = getattr(self, 'invalid_custom_locations', set())

        for location_name, location_data in self.custom_location_items.items():
            origin_song = location_data.originSong

            # Check if this location belongs to this player
            if (location_data.playerLocationBelongsTo == self.player_name or
                self.player_name in location_data.playerList):

                # Check if the origin song is still available after song limit
                if origin_song and origin_song not in available_songs:
                    self.invalid_custom_locations.add(location_name)
                    print(f"Warning: Custom location '{location_name}' references song '{origin_song}' "
                          f"which was removed by song limit for player {self.player_name}. "
                          f"Location will be skipped but ID mapping preserved.")
                elif location_name in self.invalid_custom_locations:
                    # Remove from invalid set if it becomes valid again
                    self.invalid_custom_locations.discard(location_name)

    def _generate_song_locations(self):
        """Location mappings are already generated at class level, just reference them"""
        # Locations are already created during class initialization, so just log what we have
        available_locations = []
        for song_name in self.song_items.keys():
            if self.unlock_method in ["Song Completion", "Both"]:
                for j in range(2):
                    loc_name = f"{song_name}-{j}"
                    if loc_name in self.song_locations:
                        available_locations.append(loc_name)

            if self.unlock_method in ["Note Checks", "Both"]:
                for j in range(3):
                    loc_name = f"Note {j}: {song_name}"
                    if loc_name in self.song_locations:
                        available_locations.append(loc_name)

        print(f"Available locations for {self.player_name}: {len(available_locations)} locations")

    def format_song_list(self, song_list: List[str]) -> str:
        """Format the song list for display"""
        if not song_list:
            return "No songs available"

        formatted_list = []
        for song in song_list:
            if song in self.song_items:
                song_data = self.song_items[song]
                formatted_list.append(f"{song} (ID: {song_data.code}, Modded: {song_data.modded})")
            else:
                formatted_list.append(f"{song} (Unknown ID)")

        return "\n".join(formatted_list)



    def _setup_victory_song_and_pool(self):
        """Choose victory song and set up the song pool"""
        # Get songs available to this player
        available_song_keys, song_ids = get_player_specific_ids(self.player_name, self.song_items)

        if not available_song_keys:
            raise ValueError(f"No songs available for player {self.player_name}")

        print(f"Available songs for {self.player_name}: {available_song_keys}")

        # Choose victory song randomly or from settings
        # Try to use the victory_song from YAML if it exists and is in available songs
        chosen_song_index = None
        victory_song = getattr(self.thisYaml.settings, "victory_song", None)
        
        # Check if victory song from YAML is valid
        if victory_song and victory_song not in available_song_keys:
            # Check if this is automated generation (Universal Tracker)
            is_automated = getattr(self.multiworld, 'gen_is_fake', False)
            
            if is_automated:
                # Automatically use random victory song for Universal Tracker
                print(f"Auto-fixing: Victory song '{victory_song}' not available for player '{self.player_name}', using random victory song (Universal Tracker mode)")
                victory_song = None  # Will be set randomly below
            else:
                print(f"\nWarning: Victory song '{victory_song}' specified in YAML for player '{self.player_name}' is not available in their song list.")
                print("Options:")
                print("1. Continue generation with a random victory song")
                print("2. Cancel generation")
                
                while True:
                    # Check if this is automated generation (Universal Tracker)
                    is_automated = getattr(self.multiworld, 'gen_is_fake', False)
                    
                    if is_automated:
                        choice = "1"  # Auto-select for automated generation
                        print(f"Auto-continuing generation for '{self.player_name}' with a random victory song (Universal Tracker mode).")
                        victory_song = None  # Will be set randomly below
                        break
                    else:
                        choice = input(f"What would you like to do for player '{self.player_name}'? (1/2): ").strip()
                    
                    if choice == "1":
                        print(f"Continuing generation for '{self.player_name}' with a random victory song.")
                        victory_song = None  # Will be set randomly below
                        break
                    elif choice == "2":
                        raise ValueError(f"Player '{self.player_name}' has an invalid victory song '{victory_song}' in their YAML file. Generation cancelled.")
                    else:
                        print("Invalid choice. Please enter 1 or 2.")
        
        if victory_song and victory_song in available_song_keys:
            chosen_song_index = available_song_keys.index(victory_song)
        else:
            chosen_song_index = self.random.randrange(0, len(available_song_keys))
        self.victory_song_name = available_song_keys[chosen_song_index]
        self.victory_song_id = int(song_ids[chosen_song_index])

        # Remove victory song from available pool
        remaining_songs = available_song_keys.copy()
        del remaining_songs[chosen_song_index]

        # Create song pool and give starting song
        self.create_song_pool(remaining_songs)

    def create_item(self, name: str) -> Item:
        if name == self.fnfUtil.SHOW_TICKET_NAME:
            return FunkinFixedItem(name, ItemClassification.progression_skip_balancing, self.fnfUtil.SHOW_TICKET_CODE, self.player)

        filler = self.fnfUtil.filler_items.get(name)
        if filler:
            return FunkinFixedItem(name, ItemClassification.filler, filler, self.player)

        alsoFiller = self.fnfUtil.trap_filler_items.get(name)
        if alsoFiller:
            return FunkinFixedItem(name, ItemClassification.filler, alsoFiller, self.player)

        item = self.fnfUtil.normal_items.get(name)
        if item:
            return FunkinFixedItem(name, ItemClassification.useful, item, self.player)

        onetimeitem = self.fnfUtil.one_time_items.get(name)
        if onetimeitem:
            return FunkinFixedItem(name, ItemClassification.useful, onetimeitem, self.player)

        trap = self.fnfUtil.trap_items.get(name)
        if trap:
            return FunkinFixedItem(name, ItemClassification.trap, trap, self.player)

        # Check for custom trap items
        if name in self.custom_trap_items_list:
            # Get the custom trap item ID from the mapping
            custom_trap_id = self.item_name_to_id.get(name)
            if custom_trap_id:
                return FunkinFixedItem(name, ItemClassification.trap, custom_trap_id, self.player)

        # Check for custom items (no longer using player prefixes)
        if name in self.custom_items_list:
            # Get the custom item ID from the mapping
            custom_item_id = self.item_name_to_id.get(name)
            if custom_item_id:
                return FunkinFixedItem(name, ItemClassification.useful, custom_item_id, self.player)

        # print("Song list for " + self.player_name + " is " + str(self.options.songList.value))

        song = self.song_items.get(name)
        # print(str(self.player_name) + ": " + str(song))
        return FunkinItem(name, self.player, song)

    def create_event(self, event: str) -> Item:
        return FunkinItem(event, ItemClassification.filler, None, self.player)

    def _create_item_in_quantities(self, name: str, qty: int) -> List[Item]:
        return [self.create_item(name) for _ in range(0, qty)]

    def get_filler_item_name(self) -> str:
        return self.random.choices(self.filler_item_names, self.filler_item_weights)[0]

    def create_filler_item(self) -> Item:
        return FunkinFixedItem(self.get_filler_item_name(), ItemClassification.filler, None, self.player)

    def get_available_traps(self) -> List[str]:
        full_trap_list = list(self.fnfUtil.trap_items.keys())

        # Add custom trap items for this player
        player_custom_traps = []
        for trap_name in self.custom_trap_items_list:
            # Custom trap items are available if this player has custom locations
            player_has_custom_locations = any(
                loc_data.playerLocationBelongsTo == self.player_name or
                self.player_name in loc_data.playerList
                for loc_data in self.custom_location_items.values()
            )

            if player_has_custom_locations:
                player_custom_traps.append(trap_name)

        full_trap_list.extend(player_custom_traps)

        return [trap for trap in full_trap_list if self.options.trapAmount.value > 0 and self.check_trap_weight(trap) > 0]

    def get_available_filler(self) -> List[str]:
        full_filler_list = list(self.fnfUtil.filler_items.keys())

        return [filler for filler in full_filler_list]

    def get_available_filler_traps(self) -> List[str]:
        full_filler_trap_list = list(self.fnfUtil.trap_filler_item_weights.keys())

        return [filler for filler in full_filler_trap_list if self.options.trapAmount.value > 0 and self.check_filler_trap_weight(filler) > 0]

    def get_available_items(self) -> List[str]:
        full_item_list = self.fnfUtil.normal_items.keys()
        return [item for item in full_item_list if self.check_item_weight(item) > 0]

    def check_trap_weight(self, theTrap:str):
        if theTrap in self.trap_items_weights.keys():
            return self.trap_items_weights[theTrap]

        # Custom trap items default to weight 1 if not specified
        if theTrap in self.custom_trap_items_list:
            return 1

        return 0 # if the trap doesn't exist/can't be found, don't try to add it

    def check_filler_trap_weight(self, theFiller:str):
        if self.filter_items_weights.keys().__contains__(theFiller):
            return self.filter_items_weights[theFiller]

        # Custom trap items default to weight 1 if not specified
        if theFiller in self.custom_trap_items_list:
            return 1

    def check_item_weight(self, theItem:str):
        if self.items_in_general.keys().__contains__(theItem):
            return self.items_in_general[theItem]

        return 0

    def create_song_pool(self, available_song_keys: List[str]):
        """Create the song pool and give the player a starting song"""
        if not available_song_keys:
            self.songList = []
            return

        # Choose and give starting song (precollected)
        # Try to use the starting_song from YAML if it exists and is in available songs or matches victory song
        starting_song = getattr(self.thisYaml.settings, "starting_song", None)
        starting_song_from_yaml = starting_song  # Keep original for validation
        
        # Check if starting song from YAML is invalid (not in available songs AND not the victory song)
        if (starting_song and 
            starting_song not in available_song_keys and 
            starting_song != self.victory_song_name):
            
            # Check if this is automated generation (Universal Tracker)
            is_automated = getattr(self.multiworld, 'gen_is_fake', False)
            
            if is_automated:
                # Automatically use random starting song for Universal Tracker
                print(f"Auto-fixing: Starting song '{starting_song}' not available for player '{self.player_name}', using random starting song (Universal Tracker mode)")
                starting_song = None  # Will be set randomly below
            else:
                print(f"\nWarning: Starting song '{starting_song}' specified in YAML for player '{self.player_name}' is not available in their song list.")
                print("Options:")
                print("1. Continue generation with a random starting song")
                print("2. Cancel generation")
                
                while True:
                    # Check if this is automated generation (Universal Tracker)
                    is_automated = getattr(self.multiworld, 'gen_is_fake', False)
                    
                    if is_automated:
                        choice = "1"  # Auto-select for automated generation
                        print(f"Auto-continuing generation for '{self.player_name}' with a random starting song (Universal Tracker mode).")
                        starting_song = None  # Will be set randomly below
                        break
                    else:
                        choice = input(f"What would you like to do for player '{self.player_name}'? (1/2): ").strip()
                    
                    if choice == "1":
                        print(f"Continuing generation for '{self.player_name}' with a random starting song.")
                        starting_song = None  # Will be set randomly below
                        break
                    elif choice == "2":
                        raise ValueError(f"Player '{self.player_name}' has an invalid starting song '{starting_song}' in their YAML file. Generation cancelled.")
                    else:
                        print("Invalid choice. Please enter 1 or 2.")

        # Check if starting song and victory song are the same
        if starting_song and starting_song == self.victory_song_name:
            # Check if this is automated generation (Universal Tracker)
            is_automated = getattr(self.multiworld, 'gen_is_fake', False)
            
            if is_automated:
                # Automatically use random starting song for Universal Tracker to avoid instant win
                print(f"Auto-fixing: Player '{self.player_name}' has same starting and victory song, using random starting song (Universal Tracker mode)")
                starting_song = None  # Will be set randomly below
            else:
                print(f"\nWarning: Player '{self.player_name}' has the same song '{starting_song}' set as both starting and victory song.")
                print("This will instantly BK the game and prevent progression at the beginning.")
                print("Options:")
                print("1. Continue generation anyway (game will be instantly won)")
                print("2. Use a random starting song instead")
                print("3. Cancel generation")
                
                while True:
                    # Check if this is automated generation (Universal Tracker)
                    is_automated = getattr(self.multiworld, 'gen_is_fake', False)
                    
                    if is_automated:
                        choice = "2"  # Auto-select option 2 to prevent instant win
                        print(f"Auto-selecting random starting song for '{self.player_name}' to prevent instant win (Universal Tracker mode).")
                        starting_song = None  # Will be set randomly below
                        break
                    else:
                        choice = input(f"What would you like to do for player '{self.player_name}'? (1/2/3): ").strip()
                    
                    if choice == "1":
                        print(f"Continuing generation for '{self.player_name}' with same starting and victory song (instant win).")
                        # Keep starting_song as victory_song
                        break
                    elif choice == "2":
                        print(f"Using a random starting song for '{self.player_name}' instead.")
                        starting_song = None  # Will be set randomly below
                        break
                    elif choice == "3":
                        raise ValueError(f"Player '{self.player_name}' has the same song for starting and victory. Generation cancelled.")
                    else:
                        print("Invalid choice. Please enter 1, 2, or 3.")

        if starting_song and starting_song == self.victory_song_name:
            # If starting song matches victory song, use the victory song directly
            starting_song = self.victory_song_name
            print(f'USING VICTORY SONG AS STARTING SONG: {starting_song}')
            # Don't remove anything from available_song_keys since victory song isn't in there
        elif starting_song and starting_song in available_song_keys:
            # Starting song is in available songs, remove it from the pool
            available_song_keys.remove(starting_song)
            print(f'USING CUSTOM STARTING SONG: {starting_song}')
        else:
            # No specific starting song or it's not available, pick randomly
            if not available_song_keys:
                # If no songs available, use victory song as fallback
                starting_song = self.victory_song_name
                print(f"COULDN'T FIND ANY SONGS! USING {starting_song} AS FALLBACK!")
            else:
                starting_song_index = self.random.randrange(0, len(available_song_keys))
                starting_song = available_song_keys[starting_song_index]
                # Remove Test songs and selected starting song from normal processing
                if starting_song != "Test":
                    available_song_keys.remove(starting_song)
                print(f'RANDOMLY SELECTED STARTING SONG: {starting_song}')

        print(f"Starting song for {self.player_name}: {starting_song}")
        self.multiworld.push_precollected(self.create_item(starting_song))

        # The remaining songs become the item pool
        self.songList = available_song_keys.copy()
        self.random.shuffle(self.songList)

    def create_regions(self):
        menu_region = Region("Freeplay", self.player, self.multiworld)
        self.multiworld.regions += [menu_region]

        # print("Preparing for new locations from Song Lists...")

        all_selected_locations: List[str] = []
        for song_name, song_data in self.song_items.items():
            if song_data.playerSongBelongsTo == self.player_name or self.player_name in song_data.playerList or not song_data.modded:
                all_selected_locations.append(song_name)
                '''print('Successfully gave ' + song_name + ' to ' + self.player_name + ' who is also ' + song_data.playerSongBelongsTo)
            else:
                print("This song doesn't belong to this player! Skipping it!\n Error: " + song_data.songName + " Belongs to " + song_data.playerSongBelongsTo + " and was attempted to be given to " + self.player_name)'''
        self.random.shuffle(all_selected_locations)
        # print(all_selected_locations)

        # Adds item locations per song to the menu region based on unlock method.
        for i in range(len(all_selected_locations)):
            name = all_selected_locations[i]
            # for j in range(self.checksPerSong):
            if self.unlock_method == "Song Completion":
                for j in range(2):
                    loc_name = f"{name}"
                    loc = FunkinLocation(self.player, loc_name + f"-{j}", self.song_locations[loc_name + f"-{j}"], menu_region)
                    loc.access_rule = lambda state, place=loc_name: state.has(place, self.player) and \
                        (place != self.victory_song_name or state.has(self.fnfUtil.SHOW_TICKET_NAME, self.player, self.get_ticket_win_count()))
                    menu_region.locations.append(loc)
            elif self.unlock_method == "Note Checks":
                for j in range(3):
                    # print("Note.")
                    loc_name = f"Note {j}: {name}"
                    loc = FunkinLocation(self.player, loc_name, self.song_locations[loc_name], menu_region)
                    loc.access_rule = lambda state, place=f"{name}": state.has(place, self.player) and \
                        (place != self.victory_song_name or state.has(self.fnfUtil.SHOW_TICKET_NAME, self.player, self.get_ticket_win_count()))
                    menu_region.locations.append(loc)
            elif self.unlock_method == "Both":
                for j in range(2):
                    # print("SONG")
                    loc_name = f"{name}"
                    loc = FunkinLocation(self.player, loc_name + f"-{j}", self.song_locations[loc_name + f"-{j}"], menu_region)
                    loc.access_rule = lambda state, place=loc_name: state.has(place, self.player) and \
                        (place != self.victory_song_name or state.has(self.fnfUtil.SHOW_TICKET_NAME, self.player, self.get_ticket_win_count()))
                    menu_region.locations.append(loc)
                for j in range(3):
                    # print("NOTE.")
                    loc_name = f"Note {j}: {name}"
                    loc = FunkinLocation(self.player, loc_name, self.song_locations[loc_name], menu_region)
                    loc.access_rule = lambda state, place=f"{name}": state.has(place, self.player) and \
                        (place != self.victory_song_name or state.has(self.fnfUtil.SHOW_TICKET_NAME, self.player, self.get_ticket_win_count()))
                    menu_region.locations.append(loc)
            self.location_count = len(menu_region.locations)

            self.location_name_to_id.update({loc.name: loc.address for loc in menu_region.locations if loc.name not in self.location_name_to_id})

            # print(self.location_name_to_id)

        # Add custom locations using the new LocationData system
        print("Adding custom locations...")
        for location_name, location_data in self.custom_location_items.items():
            # Check if this location belongs to this player
            if (location_data.playerLocationBelongsTo == self.player_name or
                self.player_name in location_data.playerList):

                # Skip invalid locations (but preserve their ID mappings)
                if hasattr(self, 'invalid_custom_locations') and location_name in self.invalid_custom_locations:
                    print(f"Skipping invalid custom location: {location_name} (origin song not available)")
                    continue

                # Create the custom location (no player prefix in name)
                location_id = location_data.code
                custom_loc = FunkinLocation(self.player, location_name, location_id, menu_region)

                # Apply custom access rule if available
                if location_data.accessRuleFunc:
                    custom_loc.access_rule = lambda state, rule=location_data.accessRuleFunc: rule(state, self.player)
                    print(f"Applied custom access rule to: {location_name}")
                else:
                    # Default access rule - require origin song with mod formatting if specified
                    origin_song = location_data.originSong
                    origin_mod = location_data.originMod

                    if origin_song:
                        # Format song name with mod in parentheses if mod is provided
                        if origin_mod and origin_mod.strip():
                            formatted_song_name = f"{origin_song} ({origin_mod})"
                        else:
                            formatted_song_name = origin_song

                        custom_loc.access_rule = lambda state, song=formatted_song_name: state.has(song, self.player)
                        print(f"Applied origin song access rule ({formatted_song_name}) to: {location_name}")

                menu_region.locations.append(custom_loc)
                print(f"Added custom location for {self.player_name}: {location_name}")

        # Update location count
        self.location_count = len(menu_region.locations)

        print('-- FNF LOCATION GEN FINISHED --')

    # def create_uno_filler(self) -> None:
    #     # Add UNO Color Filler items to the pool if UNO trap is enabled
    #     if self.check_trap_weight('UNO CHALLENGE') > 0:
    #         uno_filler_count = max(1, floor(self.location_count * 0.10))  # 10% of total locations
    #         for _ in range(uno_filler_count):
    #             # Get a random UNO color, unless none are left.
    #             if self.fnfUtil.UNO_COLORS:
    #                 color = self.random.choice(self.fnfUtil.UNO_COLORS)
    #                 self.fnfUtil.UNO_COLORS.remove(color)
    #             else:
    #                 color = None
    #             from .Items import FunkinUNOMinigameItem
    #             if color:
    #                 self.multiworld.itempool.append(FunkinUNOMinigameItem(f'UNO Color Filler', 0, self.player, color))
    #                 self.used_uno_colors.append(color)


    def create_items(self) -> None:
        song_keys_in_pool = self.get_songs_map(self.player_name).copy()
        if len(song_keys_in_pool) > 0:
            item_count = 0  # Track total items added
            
            # First add all goal song tokens
            ticket_count = self.get_ticket_count()
            for _ in range(ticket_count):
                self.multiworld.itempool.append(self.create_item(self.fnfUtil.SHOW_TICKET_NAME))
                item_count += 1

            # Then add 1 copy of every song
            for song in song_keys_in_pool:
                if item_count >= self.location_count:
                    break
                self.multiworld.itempool.append(self.create_item(song))
                item_count += 1

            # Add one-time items (mandatory items that cannot be turned off)
            remaining_slots = self.location_count - item_count
            one_time_items_to_add = min(remaining_slots, len(self.fnfUtil.one_time_items))
            if one_time_items_to_add > 0:
                one_time_items_list = list(self.fnfUtil.one_time_items.keys())
                for i in range(one_time_items_to_add):
                    self.multiworld.itempool.append(self.create_item(one_time_items_list[i]))
                    item_count += 1

            # Add UNO color fillers if UNO Challenge trap is enabled
            remaining_slots = self.location_count - item_count
            if self.check_trap_weight('UNO Challenge') > 0 and remaining_slots > 0:
                # Calculate UNO filler count as 10% of total locations, but cap it to remaining slots
                uno_filler_count = min(remaining_slots, max(1, floor(self.location_count * 0.10)))
                uno_colors_added = 0
                for _ in range(uno_filler_count):
                    if self.available_uno_colors and uno_colors_added < uno_filler_count:
                        color = self.random.choice(self.available_uno_colors)
                        self.available_uno_colors.remove(color)
                        from .Items import FunkinUNOMinigameItem
                        self.multiworld.itempool.append(
                            FunkinUNOMinigameItem(f'UNO Color Filler', self.fnfUtil.STARTING_CODE + 19, self.player, color))
                        self.used_uno_colors.append(color)
                        item_count += 1
                        uno_colors_added += 1

            # Add traps (making sure we don't overfill)
            remaining_slots = self.location_count - item_count
            trap_count = min(remaining_slots, self.get_trap_count())
            trap_list = self.get_available_traps()
            if len(trap_list) > 0 and trap_count > 0:
                for _ in range(trap_count):
                    index = self.random.randrange(0, len(trap_list))
                    self.multiworld.itempool.append(self.create_item(trap_list[index]))
                    item_count += 1

            # Add useful items
            remaining_slots = self.location_count - item_count
            useful_item_count = min(remaining_slots, self.get_item_count())
            item_list = self.get_available_items()
            if len(item_list) > 0 and useful_item_count > 0:
                for _ in range(useful_item_count):
                    index = self.random.randrange(0, len(item_list))
                    self.multiworld.itempool.append(self.create_item(item_list[index]))
                    item_count += 1

            # Add filler trap items
            remaining_slots = self.location_count - item_count
            filler_trap_count = min(remaining_slots, self.get_filler_trap_count())
            filler_list = self.get_available_filler_traps()
            if len(filler_list) > 0 and filler_trap_count > 0:
                for item in filler_list:
                    for trapitem in range(self.filter_items_weights[item]):
                        self.multiworld.itempool.append(self.create_item(filler_list[trapitem]))
                        item_count += 1

            # Add custom items
            remaining_slots = self.location_count - item_count
            if remaining_slots > 0:
                # Filter custom items for this player
                player_custom_items = []
                for item_name in self.custom_items_list:
                    player_has_custom_locations = any(
                        loc_data.playerLocationBelongsTo == self.player_name or
                        self.player_name in loc_data.playerList
                        for loc_data in self.custom_location_items.values()
                    )
                    if player_has_custom_locations:
                        player_custom_items.append(item_name)

                custom_item_count = min(remaining_slots, len(player_custom_items))
                if custom_item_count > 0:
                    print(f"Adding {custom_item_count} custom items to pool for {self.player_name}")
                    for i in range(custom_item_count):
                        custom_item_name = player_custom_items[i % len(player_custom_items)]
                        self.multiworld.itempool.append(self.create_item(custom_item_name))
                        item_count += 1

            # Add custom trap items (only if traps are enabled)
            remaining_slots = self.location_count - item_count
            if self.options.trapAmount.value > 0 and remaining_slots > 0:
                # Filter custom trap items for this player
                player_custom_traps = []
                for trap_name in self.custom_trap_items_list:
                    player_has_custom_locations = any(
                        loc_data.playerLocationBelongsTo == self.player_name or
                        self.player_name in loc_data.playerList
                        for loc_data in self.custom_location_items.values()
                    )
                    if player_has_custom_locations:
                        player_custom_traps.append(trap_name)

                custom_trap_count = min(remaining_slots, len(player_custom_traps))
                if custom_trap_count > 0:
                    print(f"Adding {custom_trap_count} custom trap items to pool for {self.player_name}")
                    for i in range(custom_trap_count):
                        custom_trap_name = player_custom_traps[i % len(player_custom_traps)]
                        self.multiworld.itempool.append(self.create_item(custom_trap_name))
                        item_count += 1

            # Fill remaining slots with song duplicates and filler
            remaining_slots = self.location_count - item_count
            if remaining_slots > 0:
                # Fill 20% of remaining slots with useful song duplicates
                dupe_count = min(remaining_slots, floor(remaining_slots * 0.20))
                
                # Add song duplicates if we have songs to duplicate
                if len(song_keys_in_pool) > 0 and dupe_count > 0:
                    for i in range(dupe_count):
                        song_index = i % len(song_keys_in_pool)
                        item = self.create_item(song_keys_in_pool[song_index])
                        item.classification = ItemClassification.useful
                        self.multiworld.itempool.append(item)
                        item_count += 1

                # Fill all remaining slots with filler items
                remaining_slots = self.location_count - item_count
                for _ in range(remaining_slots):
                    self.multiworld.itempool.append(self.create_item(self.get_filler_item_name()))
                    item_count += 1

            # Validate that we have exactly the right number of items
            if item_count != self.location_count:
                print(f"ERROR: Item count ({item_count}) doesn't match location count ({self.location_count}) for player {self.player_name}")
                raise ValueError(f"Item/location count mismatch: {item_count} items vs {self.location_count} locations")
            
            print(f"Successfully created {item_count} items for {self.location_count} locations for player {self.player_name}")

    def set_rules(self) -> None:
        self.multiworld.completion_condition[self.player] = \
            lambda state: state.has(self.fnfUtil.SHOW_TICKET_NAME, self.player, self.get_ticket_win_count()) and \
                  state.has(self.victory_song_name, self.player, 1)

    def get_trap_count(self) -> int:
        return self.options.trapAmount.value

    def get_item_count(self) -> int:
        return self.items_in_general['Shield'] + self.items_in_general['Max HP Up']

    def get_filler_trap_count(self) -> int:
        total = 0
        for item in self.filter_items_weights.keys():
            total += 1
        return total

    def get_ticket_count(self) -> int:
        multiplier = self.options.ticket_percentage.value / 100.0
        song_count = len(self.get_songs_map(self.player_name))
        return max(1, floor(song_count * multiplier))

    def get_ticket_win_count(self) -> int:
        multiplier = self.options.ticket_win_percentage.value / 100.0
        ticket_count = self.get_ticket_count()
        return max(1, floor(ticket_count * multiplier))


    def write_spoiler(self, spoiler_handle: TextIO) -> None:
        spoiler_handle.write("\n\n")
        spoiler_handle.write(f"--- FNF SPOILER INFO FOR [{self.player_name}] ---\n")
        spoiler_handle.write(f"Victory Song: {self.victory_song_name}\n")
        spoiler_handle.write(f"Ticket Win Count: {self.get_ticket_win_count()}\n")
        spoiler_handle.write(f"Total Ticket Count: {self.get_ticket_count()}\n")
        spoiler_handle.write(f"Total Song Count: {len(self.get_songs_map(self.player_name))}\n")
        spoiler_handle.write(f"Songs selected: {self.get_songs_map(self.player_name)}\n")

    # def extend_hint_information(self, hint_data):
    #     return super().extend_hint_information(hint_data)

    # def collect(self, state, item):
    #     return super().collect(state, item)

    def get_songs_map(self, player_name:str) -> List[str]:
        """Literally just shoves the songs into a list."""
        filtered_list = []

        for songKey, songData in self.song_items.items():
            if songData.playerSongBelongsTo == player_name or player_name in songData.playerList: #Make sure the right player gets the right songs
                filtered_list.append(songKey)
                #print(songKey)

        return filtered_list

    def get_player_song_details(self, player_name: str) -> Dict[str, Dict]:
        """Get detailed information about songs for a specific player"""
        song_details = {}

        for song_name, song_data in self.song_items.items():
            if (song_data.playerSongBelongsTo == player_name or
                player_name in song_data.playerList or
                not song_data.modded):

                song_details[song_name] = {
                    "id": song_data.code,
                    "modded": song_data.modded,
                    "playerOwner": song_data.playerSongBelongsTo,
                    "sharedWith": song_data.playerList,
                    "songName": song_data.songName
                }

        return song_details

    def get_player_location_details(self, player_name: str) -> Dict[str, Dict]:
        """Get detailed information about locations for a specific player"""
        location_details = {}

        # Add song-based locations
        for song_name, song_data in self.song_items.items():
            if (song_data.playerSongBelongsTo == player_name or
                player_name in song_data.playerList or
                not song_data.modded):
                    # Helper to extract mod name from song name (last parentheses)
                    def extract_mod_from_song(song_name: str) -> str:
                        # Match the last pair of parentheses at the end of the string
                        import re
                        match = re.search(r'\(([^()]*)\)\s*$', song_name)
                        if match:
                            return match.group(1).strip()
                        return ""

                    # Song completion locations
                    if self.unlock_method in ["Song Completion", "Both"]:
                        for j in range(2):
                            loc_name = f"{song_name}-{j}"
                            if loc_name in self.song_locations:
                                location_details[loc_name] = {
                                    "id": self.song_locations[loc_name],
                                    "type": "song_completion",
                                    "originSong": song_name,
                                    "originMod": extract_mod_from_song(song_name),
                                    "playerOwner": song_data.playerSongBelongsTo,
                                    "sharedWith": song_data.playerList
                                }

                    # Note check locations
                    if self.unlock_method in ["Note Checks", "Both"]:
                        for j in range(3):
                            loc_name = f"Note {j}: {song_name}"
                            if loc_name in self.song_locations:
                                location_details[loc_name] = {
                                    "id": self.song_locations[loc_name],
                                    "type": "note_check",
                                    "originSong": song_name,
                                    "originMod": extract_mod_from_song(song_name),
                                    "playerOwner": song_data.playerSongBelongsTo,
                                    "sharedWith": song_data.playerList
                                }

        # Add custom locations
        for location_name, location_data in self.custom_location_items.items():
            if (location_data.playerLocationBelongsTo == player_name or
                player_name in location_data.playerList):

                # Skip invalid locations from slot data (but preserve their ID mappings)
                if hasattr(self, 'invalid_custom_locations') and location_name in self.invalid_custom_locations:
                    continue

                location_details[location_name] = {
                    "id": location_data.code,
                    "type": "custom",
                    "originSong": location_data.originSong,
                    "originMod": location_data.originMod,
                    "playerOwner": location_data.playerLocationBelongsTo,
                    "sharedWith": location_data.playerList
                }

        return location_details


    def fill_slot_data(self):
        if not self.victory_song_name == "":
            # Get the songs that belong to this player
            player_songs = self.get_songs_map(self.player_name)
            song_details = self.get_player_song_details(self.player_name)
            location_details = self.get_player_location_details(self.player_name)

            # Get all UNO Minigame colors by looking in the multiworld.

            # Collect custom week data for songs added by scripts
            custom_weeks_data = self._get_custom_weeks_data()

            # Safely get player-specific song additions, or None if not present
            player_song_additions = None
            if hasattr(self, "player_song_additions") and isinstance(self.player_song_additions, dict):
                player_song_additions = self.player_song_additions.get(self.player_name, None)

            return {
                "deathLink": self.options.deathlink.value,
                "fullSongCount": len(player_songs),
                "victoryLocation": self.victory_song_name,
                "victoryID": self.victory_song_id,
                "ticketWinCount": self.get_ticket_win_count(),
                "gradeNeeded": self.options.graderequirement.value,
                "accuracyNeeded": self.options.accrequirement.value,
                "locationType": self.unlock_method,
                "locationMethod": self.unlock_type,
                "selectedSongs": player_songs,  # List of songs selected for this player
                "songData": song_details,  # Detailed song metadata for the client
                "locationData": location_details,  # Detailed location metadata for the client
                "customWeeks": custom_weeks_data,  # Custom week generation data for APGameState
                "song_modifications": {
                    'song_additions': player_song_additions,
                    'song_exclusions': None  # Placeholder, update as needed
                },
                "unoColorsUsed": [
                    {
                        "name": color.name,
                        "color_code": color.color_code
                    }
                    for color in self.used_uno_colors if color is not None
                ]
            }
    def _get_custom_weeks_data(self):
        """Generate custom week data for songs added by AP scripts"""
        custom_weeks = {}

        # Group added songs by target mod
        songs_by_mod = {}
        for song_info in self._custom_song_additions:
            song_name = song_info.get('name', '')
            target_mod = song_info.get('targetMod', '') or 'base'

            if target_mod not in songs_by_mod:
                songs_by_mod[target_mod] = []

            # Only add if song doesn't already exist in that mod's weeks
            if not self._song_exists_in_mod_weeks(song_name, target_mod):
                songs_by_mod[target_mod].append(song_name)

        # Create week data for each mod that needs custom songs
        for mod_name, songs in songs_by_mod.items():
            if songs:  # Only create week if there are songs to add
                week_name = f"ap_custom_{mod_name}" if mod_name != 'base' else "ap_custom_base"
                custom_weeks[week_name] = {
                    "targetMod": mod_name,
                    "weekName": week_name,
                    "songs": songs,
                    "weekTitle": f"AP Custom ({mod_name.title() if mod_name != 'base' else 'Base Game'})",
                    "difficulties": ["easy", "normal", "hard"]  # Default difficulties
                }

        return custom_weeks

    def _song_exists_in_mod_weeks(self, song_name: str, target_mod: str):
        """Check if a song already exists in any week file for the target mod"""
        # This would check existing week files to prevent duplicates
        # Implementation would depend on how week data is accessed
        # For now, return False to allow addition (can be refined later)
        return False
