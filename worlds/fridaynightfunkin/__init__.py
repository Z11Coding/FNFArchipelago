# Copyright (c) 2022 FelicitusNeko
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT
from BaseClasses import Region, Item, MultiWorld, Tutorial, ItemClassification
from typing import Dict, List, ClassVar, Type, Tuple
from worlds.AutoWorld import World, WebWorld
from math import floor
import random

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

    fnfUtil = FunkinUtils()
    filler_item_names = list(fnfUtil.filler_items.keys())
    filler_item_weights = list(fnfUtil.filler_item_weights.values())
    item_name_to_id = {name: code for name, code in fnfUtil.item_names_to_id.items()}
    location_name_to_id = {name: code for name, code in fnfUtil.location_names_to_id.items()}
    trap_items_weights: Dict[str, int] = {}

    def __init__(self, multiworld: MultiWorld, player: int):
        # print("Building FunkinWorld...")
        super(FunkinWorld, self).__init__(multiworld, player)
        # print("Building FunkinWorld...")
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

    def generate_early(self):
        # Basic Settings
        self.mods_enabled = self.options.mods_enabled.value
        self.starting_song = self.options.starting_song.value
        self.unlock_type = self.options.unlock_type.value
        self.unlock_method = self.options.unlock_method.value
        # Trap Settings
        self.trapAmount = self.options.trapAmount.value
        self.trap_items_weights['Blue Balls Curse'] = self.options.bbcWeight.value
        self.trap_items_weights['Ghost Chat'] = self.options.ghostChatWeight.value
        self.trap_items_weights['SvC Effect'] = self.options.svcWeight.value
        self.trap_items_weights['Tutorial Trap'] = self.options.tutorialWeight.value
        self.trap_items_weights['Fake Transition'] = self.options.fakeTransWeight.value
        self.trap_items_weights['Chart Modifier Trap'] = self.options.chart_modifier_change_chance.value
        self.ticket_percentage = self.options.ticket_percentage.value
        self.ticket_win_percentage = self.options.ticket_win_percentage.value
        self.graderequirement = self.options.graderequirement.value
        self.accrequirement = self.options.accrequirement.value
        self.checksPerSong = self.options.check_count.value
        #self.e_weight = self.options.trapAmount.value imma do this later
        while True:
            # In most cases this should only need to run once
            available_song_keys, song_ids = get_player_specific_ids(self.player_name, self.fnfUtil.song_items)
            # print(available_song_keys)

            # print(get_player_specific_ids(self.options.songList.value, self.fnfUtil.song_items))
            # Choose victory song from current available keys, so we can access the song id
            chosen_song_index = random.randrange(0, len(available_song_keys))
            self.victory_song_name = available_song_keys[chosen_song_index]
            self.victory_song_id = int(song_ids[chosen_song_index])
            del available_song_keys[chosen_song_index]

            available_song_keys = available_song_keys
            count_needed_for_start = max(0, 1)

            final_song_list = available_song_keys
            # print(final_song_list)
            self.create_song_pool(final_song_list)
            break

    def create_item(self, name: str) -> Item:
        if name == self.fnfUtil.SHOW_TICKET_NAME:
            return FunkinFixedItem(name, ItemClassification.progression_skip_balancing, self.fnfUtil.SHOW_TICKET_CODE, self.player)

        filler = self.fnfUtil.filler_items.get(name)
        if filler:
            return FunkinFixedItem(name, ItemClassification.filler, filler, self.player)

        trap = self.fnfUtil.trap_items.get(name)
        if trap:
            return FunkinFixedItem(name, ItemClassification.trap, trap, self.player)

        # print("Song list for " + self.player_name + " is " + str(self.options.songList.value))

        song = self.fnfUtil.song_items.get(name)
        # print(str(self.player_name) + ": " + str(song.songName))
        return FunkinItem(name, self.player, song)

    def create_event(self, event: str) -> Item:
        return FunkinItem(event, ItemClassification.filler, None, self.player)

    def _create_item_in_quantities(self, name: str, qty: int) -> [Item]:
        return [self.create_item(name) for _ in range(0, qty)]

    def get_filler_item_name(self) -> str:
        return self.random.choices(self.filler_item_names, self.filler_item_weights)[0]

    def create_filler_item(self) -> Item:
        return FunkinFixedItem(self.get_filler_item_name(), ItemClassification.filler, None, self.player)

    def get_available_traps(self) -> List[str]:
        full_trap_list = self.fnfUtil.trap_items.keys()
        return [trap for trap in full_trap_list if self.options.trapAmount.value > 0 and self.check_trap_weight(trap) > 0]

    def check_trap_weight(self, theTrap:str):
        if self.trap_items_weights.keys().__contains__(theTrap):
            return self.trap_items_weights[theTrap]

    def create_song_pool(self, available_song_keys: List[str]):
        if len(available_song_keys) > 0:
            startingSong = available_song_keys[self.random.randrange(0, len(available_song_keys))]
            if not startingSong == "Test": available_song_keys.remove(startingSong)
            self.multiworld.push_precollected(self.create_item(startingSong))
            self.songList = available_song_keys

            if self.options.starting_song.value != "":
                starting_song_count = 1
            else:
                starting_song_count = 0
            self.random.shuffle(available_song_keys)
            song_count = len(self.songList)
            # choose a random victory song from the available songs
            chosen_song = self.random.randrange(0, len(available_song_keys))
            if chosen_song < song_count:
                self.victory_song_name = self.songList[chosen_song]
                del self.songList[chosen_song]
            else:
                self.victory_song_name = available_song_keys[chosen_song - song_count]
                del available_song_keys[chosen_song - song_count]

            # Then attempt to fulfill any remaining songs for interim songs
            if len(self.songList) < song_count:
                for _ in range(0, len(self.songList)):
                    if len(available_song_keys) <= 0:
                        break
                    self.songList.append(available_song_keys.pop())

    def create_regions(self):
        menu_region = Region("Freeplay", self.player, self.multiworld)
        self.multiworld.regions += [menu_region]

        # print("Preparing for new locations from Song Lists...")


        all_selected_locations: List[str] = []
        for song_name, song_data in self.fnfUtil.song_items.items():
            if song_data.playerSongBelongsTo == self.player_name or self.player_name in song_data.playerList or not song_data.modded:
                all_selected_locations.append(song_name)
                '''print('Successfully gave ' + song_name + ' to ' + self.player_name + ' who is also ' + song_data.playerSongBelongsTo)
            else:
                print("This song doesn't belong to this player! Skipping it!\n Error: " + song_data.songName + " Belongs to " + song_data.playerSongBelongsTo + " and was attempted to be given to " + self.player_name)'''
        self.random.shuffle(all_selected_locations)
        # print(all_selected_locations)

        # Adds item locations per song to the menu region.
        for i in range(len(all_selected_locations)):
            name = all_selected_locations[i]
            # for j in range(self.checksPerSong):
            for j in range(2):
                loc_name = f"{name}"
                loc = FunkinLocation(self.player, loc_name + f"-{j}", self.fnfUtil.song_locations[loc_name + f"-{j}"], menu_region)
                loc.access_rule = lambda state, place=loc_name: state.has(place, self.player)
                menu_region.locations.append(loc)
        self.location_count = 2 * len(all_selected_locations)

    def create_items(self) -> None:
        song_keys_in_pool = self.fnfUtil.get_songs_map(self.player_name).copy()
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

            # At this point, if a player is using traps, it's possible that they have filled all locations
            items_left = self.location_count - item_count
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
    
            filler_count = items_left
            items_left -= filler_count
    
            for _ in range(0, filler_count):
                self.multiworld.itempool.append(self.create_item(self.get_filler_item_name()))

    def set_rules(self) -> None:
        self.multiworld.completion_condition[self.player] = \
            lambda state: state.has(self.fnfUtil.SHOW_TICKET_NAME, self.player, self.get_ticket_win_count())
        '''self.multiworld.completion_condition[self.player] = lambda state: \
            state.has(self.victory_song_name, self.player, 1)'''

    def get_trap_count(self) -> int:
        multiplier = self.options.trapAmount.value / 100.0
        trap_count = len(self.fnfUtil.get_songs_map(self.player_name))
        return max(0, floor(trap_count * multiplier))

    def get_ticket_count(self) -> int:
        multiplier = self.options.ticket_percentage.value / 100.0
        song_count = len(self.fnfUtil.get_songs_map(self.player_name))
        return max(1, floor(song_count * multiplier))

    def get_ticket_win_count(self) -> int:
        multiplier = self.options.ticket_win_percentage.value / 100.0
        ticket_count = self.get_ticket_count()
        return max(1, floor(ticket_count * multiplier))

    def fill_slot_data(self):
        if not self.victory_song_name == "":
            return {
                "deathLink": self.options.deathlink.value,
                "fullSongCount": len(self.fnfUtil.get_songs_map(self.player_name)),
                "victoryLocation": self.victory_song_name,
                "victoryID": self.victory_song_id,
                "ticketWinCount": self.get_ticket_win_count(),
                "gradeNeeded": self.options.graderequirement.value,
                "accuracyNeeded": self.options.accrequirement.value
            }