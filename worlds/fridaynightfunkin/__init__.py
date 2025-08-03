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
from .Items import FNFBaseList, SongData

from .ModHandler import (
    get_player_specific_ids,
    extract_mod_data,
)
from .Items import FunkinItem, FunkinFixedItem
from .Locations import FunkinLocation
from .Options import *
from .FunkinUtils import FunkinUtils


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

        # Initialize class-level data
        song_items = {}
        song_locations = {}
        item_name_to_id = {}
        location_name_to_id = {}
        item_id_index = fnfUtil.STARTING_CODE + 100

        # Process all songs from all players
        all_songs = set()

        # Collect all unique songs from all players
        for yaml_data in all_yamls:
            if yaml_data.getSongList():
                for song in yaml_data.getSongList():
                    # Clean the song name
                    cleaned_song = song.strip().replace('<cOpen>', '{').replace('<cClose>', '}').replace('<sOpen>',
                                                                                                         '[').replace(
                        '<sClose>', ']').strip()
                    all_songs.add(cleaned_song)

        # Add fallback songs if no custom songs found
        if not all_songs:
            all_songs.update(FNFBaseList.emptySongList)

        print(f"Found {len(all_songs)} unique songs across all players: {list(all_songs)}")

        # Create SongData for all songs
        for song in all_songs:
            cur_song_name = song
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
            item_id_index += 1

        # Create all possible locations for all songs
        for song_name, song_data in song_items.items():
            # Song completion locations
            for j in range(2):
                song_locations[f"{song_name}-{j}"] = (song_data.code + 1000 * j)

            # Note check locations
            for j in range(3):
                song_locations[f"Note {j}: {song_name}"] = (song_data.code + 1000 * j + 10000)


        # Build final name-to-ID mappings
        item_name_to_id = dict(ChainMap(
            {fnfUtil.SHOW_TICKET_NAME: fnfUtil.SHOW_TICKET_CODE},
            fnfUtil.filler_items,
            fnfUtil.normal_items,
            fnfUtil.trap_items,
            {name: data.code for name, data in song_items.items()}
        ))

        location_name_to_id = dict(ChainMap(song_locations))

        # Store YAML data for instances to use
        _all_yamls = all_yamls
        _class_data_initialized = True

        print(f"Initialized {len(item_name_to_id)} items and {len(location_name_to_id)} locations")

        return {"items": item_name_to_id, "locations": location_name_to_id}
    
    # These will be populated during class creation in __new__
    song_items: Dict[str, SongData] = {}
    song_locations: Dict[str, int] = {}
    yaml_data = stuff()
    item_name_to_id = yaml_data["items"]
    location_name_to_id = yaml_data["locations"]
    
    # Temporary storage for setup
    items_in_general: dict[str, int] = {}
    trap_items_weights: dict[str, int] = {}
    items_weights: dict[str, int] = {}
    songLimit: int
    item_id_index: int = 0
    songlistforthe83rdtime: list[str] = []




    @classmethod
    def _setup_class_data(cls, multiworld: MultiWorld):
        """Setup all item and location IDs for all players during class creation"""
        if hasattr(cls, '_class_data_initialized'):
            return  # Already initialized

        import Utils
        from .Yutautil import yutautil_APYaml
        import sys
        import os

        # Get all player YAML files
        user_path = Utils.user_path(Utils.get_settings()["generator"]["player_files_path"])
        folder_path = sys.argv[sys.argv.index("--player_files_path") - 1] if "--player_files_path" in sys.argv else user_path

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

        # Initialize class-level data
        cls.song_items = {}
        cls.song_locations = {}
        item_name_to_id = {}
        location_name_to_id = {}
        cls.item_id_index = cls.fnfUtil.STARTING_CODE + 100

        # Process all songs from all players
        all_songs = set()

        # Collect all unique songs from all players
        for yaml_data in all_yamls:
            if yaml_data.getSongList():
                for song in yaml_data.getSongList():
                    # Clean the song name
                    cleaned_song = song.strip().replace('<cOpen>', '{').replace('<cClose>', '}').replace('<sOpen>', '[').replace('<sClose>', ']').strip()
                    all_songs.add(cleaned_song)

        # Add fallback songs if no custom songs found
        if not all_songs:
            all_songs.update(FNFBaseList.emptySongList)

        # Remove single quotes around song names if they exist
        cleaned_songs = set()
        for song in all_songs:
            cleaned_song = song[1:-1] if song.startswith("'") and song.endswith("'") and len(song) >= 2 else song
            cleaned_songs.add(cleaned_song)
        all_songs = cleaned_songs

        print(f"Found {len(all_songs)} unique songs across all players: {list(all_songs)}")

        # Create SongData for all songs
        for song in all_songs:
            cur_song_name = song
            item_id = cls.item_id_index
            # isModded = cur_song_name.capitalize().replace("-", " ") not in FNFBaseList.baseSongList
            isModded = True

            if not isModded:
                continue

            # Create song data - we'll assign players later
            cls.song_items[cur_song_name] = SongData(
                item_id,
                isModded,
                cur_song_name,
                "", # Will be set per-instance
                []  # Will be populated per-instance
            )
            cls.item_id_index += 1

        # Create all possible locations for all songs
        for song_name, song_data in cls.song_items.items():
            # Song completion locations
            for j in range(2):
                cls.song_locations[f"{song_name}-{j}"] = (song_data.code + 1000 * j)

            # Note check locations
            for j in range(3):
                cls.song_locations[f"Note {j}: {song_name}"] = (song_data.code + 1000 * j + 10000)

        # Build final name-to-ID mappings
        item_name_to_id = dict(ChainMap(
            {cls.fnfUtil.SHOW_TICKET_NAME: cls.fnfUtil.SHOW_TICKET_CODE},
            cls.fnfUtil.filler_items,
            cls.fnfUtil.normal_items,
            cls.fnfUtil.trap_items,
            {name: data.code for name, data in cls.song_items.items()}
        ))

        location_name_to_id = dict(ChainMap(cls.song_locations))

        # Store YAML data for instances to use
        cls._all_yamls = all_yamls
        cls._class_data_initialized = True

        print(f"Initialized {len(cls.item_name_to_id)} items and {len(cls.location_name_to_id)} locations")

        return {"items": item_name_to_id, "locations": location_name_to_id}

    def __new__(cls, multiworld: MultiWorld, player: int):
        # Setup class data if not already done
        cls.data = cls._setup_class_data(multiworld)

        print(cls.data)

        instance = super(FunkinWorld, cls).__new__(cls)


        # Find this player's YAML
        player_name = multiworld.player_name[player]
        player_yaml = None

        for yaml_data in cls._all_yamls:
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
                        'songList': FNFBaseList.emptySongList.copy(),
                        'song_limit': 5
                    })()
                def getSongList(self):
                    return self.settings.songList
            player_yaml = DefaultYAML()

        instance.thisYaml = player_yaml
        instance.yamlList = cls._all_yamls
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
        self.items_in_general = {}
        self.songLimit = 5

    def generate_early(self):
        # Basic Settings
        self.mods_enabled = self.options.mods_enabled.value
        self.starting_song = self.options.starting_song.value
        self.unlock_type = self.options.unlock_type.value.pop()
        self.unlock_method = self.options.unlock_method.value.pop()

        # Trap Settings
        self.trapAmount = self.options.trapAmount.value
        self.trap_items_weights['Blue Balls Curse'] = self.options.bbcWeight.value
        self.trap_items_weights['Ghost Chat'] = self.options.ghostChatWeight.value
        self.trap_items_weights['SvC Effect'] = self.options.svcWeight.value
        self.trap_items_weights['Tutorial Trap'] = self.options.tutorialWeight.value
        self.trap_items_weights['Fake Transition'] = self.options.fakeTransWeight.value
        self.trap_items_weights['Chart Modifier Trap'] = self.options.chart_modifier_change_chance.value
        self.items_in_general['Shield'] = self.options.shieldWeight.value
        self.items_in_general['Max HP Up'] = self.options.MHPWeight.value

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

        # If no songs in YAML, use fallback
        if not raw_song_list:
            raw_song_list = FNFBaseList.emptySongList.copy()
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
        for song in FNFBaseList.baseSongList:
            if song in self.song_items and song not in available_songs:
                available_songs.append(song)

        if not available_songs:
            # Emergency fallback - use any song from class data
            available_songs = remove_YAML_formatting(list(self.song_items.keys())[:5])
            print(f"Emergency fallback: Using first 5 songs from class data for {self.player_name}")

        # Randomize the song list
        self.random.shuffle(available_songs)

        # Apply song limit
        song_limit = max(1, getattr(self.thisYaml.settings, 'song_limit', self.songLimit) or 5)
        limited_song_list = available_songs if getattr(self.multiworld, 'gen_is_fake', False) else available_songs[:song_limit]

        print(f"Processing {len(limited_song_list)} songs for player {self.player_name}: {limited_song_list}")

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
    def _generate_song_locations(self):
        """Location mappings are already generated at class level, just reference them"""
        # Locations are already created in _setup_class_data, so just log what we have
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

        # Choose victory song randomly
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

        item = self.fnfUtil.normal_items.get(name)
        if item:
            return FunkinFixedItem(name, ItemClassification.useful, item, self.player)

        trap = self.fnfUtil.trap_items.get(name)
        if trap:
            return FunkinFixedItem(name, ItemClassification.trap, trap, self.player)

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
        full_trap_list = self.fnfUtil.trap_items.keys()
        return [trap for trap in full_trap_list if self.options.trapAmount.value > 0 and self.check_trap_weight(trap) > 0]

    def get_available_items(self) -> List[str]:
        full_item_list = self.fnfUtil.normal_items.keys()
        return [item for item in full_item_list if self.check_item_weight(item) > 0]

    def check_trap_weight(self, theTrap:str):
        if self.trap_items_weights.keys().__contains__(theTrap):
            return self.trap_items_weights[theTrap]

    def check_item_weight(self, theItem:str):
        if self.items_in_general.keys().__contains__(theItem):
            return self.items_in_general[theItem]

    def create_song_pool(self, available_song_keys: List[str]):
        """Create the song pool and give the player a starting song"""
        if not available_song_keys:
            self.songList = []
            return

        # Choose and give starting song (precollected)
        starting_song_index = self.random.randrange(0, len(available_song_keys))
        starting_song = available_song_keys[starting_song_index]

        # Remove Test songs from normal processing
        if starting_song != "Test":
            available_song_keys.remove(starting_song)

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

            print(self.location_name_to_id)
        print('-- FNF LOCATION GEN FINISHED --')


    def create_items(self) -> None:
        song_keys_in_pool = self.get_songs_map(self.player_name).copy()
        if len(song_keys_in_pool) > 0:
            item_count = self.get_ticket_count()

            # I'll figure this out eventually
            # First add all goal song tokens
            for _ in range(0, item_count):
                self.multiworld.itempool.append(self.create_item(self.fnfUtil.SHOW_TICKET_NAME))

            # Then add 1 copy of every song
            item_count += len(song_keys_in_pool)
            for song in song_keys_in_pool:
                self.multiworld.itempool.append(self.create_item(song))

            # Then add all traps, making sure we don't over fill
            trap_count = min(self.location_count - item_count, self.get_trap_count())
            trap_list = self.get_available_traps()
            if len(trap_list) > 0 and trap_count > 0:
                for _ in range(0, trap_count):
                    index = self.random.randrange(0, len(trap_list))
                    self.multiworld.itempool.append(self.create_item(trap_list[index]))

                item_count += trap_count

            #Next, add all of their items
            items_left = self.location_count - item_count
            item_count = min(items_left, self.get_item_count())
            item_list = self.get_available_items()
            if len(item_list) > 0 and item_count > 0:
                for _ in range(0, item_count):
                    index = self.random.randrange(0, len(item_list))
                    self.multiworld.itempool.append(self.create_item(item_list[index]))


            # At this point, if a player is using traps, it's possible that they have filled all locations
            if items_left <= 0:
                return

            # Fill given percentage of remaining slots as Useful/non-progression dupes.
            dupe_count = floor(items_left * (20 / 100))
            items_left -= dupe_count

            # This is for the extraordinary case of needing to fill a lot of items.
            while dupe_count > len(song_keys_in_pool):
                for key in song_keys_in_pool:
                    item = self.create_item(key)
                    item.classification = ItemClassification.useful
                    self.multiworld.itempool.append(item)

                dupe_count -= len(song_keys_in_pool)
                continue

            self.random.shuffle(song_keys_in_pool)
            for i in range(0, dupe_count):
                item = self.create_item(song_keys_in_pool[i])
                item.classification = ItemClassification.useful
                self.multiworld.itempool.append(item)

            # subtracting this by 10 fixed the items larger than locations problem
            # istg imma explode
            filler_count = items_left
            items_left -= filler_count

            for _ in range(0, filler_count):
                self.multiworld.itempool.append(self.create_item(self.get_filler_item_name()))

    def set_rules(self) -> None:
        self.multiworld.completion_condition[self.player] = \
            lambda state: state.has(self.fnfUtil.SHOW_TICKET_NAME, self.player, self.get_ticket_win_count()) and \
                  state.has(self.victory_song_name, self.player, 1)

    def get_trap_count(self) -> int:
        return self.options.trapAmount.value

    def get_item_count(self) -> int:
        return self.items_in_general['Shield'] + self.items_in_general['Max HP Up']

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
    

    def fill_slot_data(self):
        if not self.victory_song_name == "":
            # Get the songs that belong to this player
            player_songs = self.get_songs_map(self.player_name)
            song_details = self.get_player_song_details(self.player_name)
            
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
                "songData": song_details  # Detailed song metadata for the client
            }