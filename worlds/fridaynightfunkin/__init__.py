# Copyright (c) 2022 FelicitusNeko
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from BaseClasses import Region, Item, MultiWorld, Tutorial, ItemClassification
from .Items import FunkinItem, item_table, item_groups
from .Locations import location_table
from .Options import *
from .Locations import FunkinLocation
from worlds.AutoWorld import World, WebWorld


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

    item_name_to_id = item_table
    location_name_to_id = location_table
    item_name_groups = item_groups
    option_groups = option_groups
    required_client_version = (0, 5, 0)
    topology_present = False
    options: FunkinOptions
    options_dataclass = FunkinOptions

    origin_region_name = "Freeplay"

    def __init__(self, multiworld: MultiWorld, player: int):
        super(FunkinWorld, self).__init__(multiworld, player)
        self.allow_mods = AllowMods.default
        self.starting_songs = SongStarter.default
        self.chart_modifier_change_chance = ChartModChangeChance.default
        self.unlock_type = UnlockType.default
        self.unlock_method = UnlockMethod.default
        self.songList = songList.default
        self.trapAmount = trapAmount.default

    def create_item(self, name: str) -> Item:
        return FunkinItem(name, ItemClassification.filler, item_table[name], self.player)

    def create_event(self, event: str) -> Item:
        return FunkinItem(event, ItemClassification.filler, None, self.player)

    def _create_item_in_quantities(self, name: str, qty: int) -> [Item]:
        return [self.create_item(name) for _ in range(0, qty)]

    def _create_traps(self):
        trap_return = [0, 0, 0, 0, 0]

        for i in range(self.trapAmount):
            draw = self.multiworld.random.randrange(0, self.trapAmount)
            if draw < self.bbc_weight:
                trap_return[0] += 1
            elif draw < self.ghost_chat_weight:
                trap_return[1] += 1
            elif draw < self.svc_effect_weight:
                trap_return[2] += 1
            elif draw < self.tutorial_trap_weight:
                trap_return[3] += 1
            elif draw < self.fake_transition_weight:
                trap_return[4] += 1
            elif draw < self.e_weight: # soon
                trap_return[5] += 1

        return trap_return

    def get_filler_item_name(self) -> str:
        return "Nothing"

    def generate_early(self):
        # Basic Settings
        self.allow_mods = self.options.allow_mods.value
        self.starting_songs = self.options.starting_songs.value
        self.randomize_chart_modifier = self.options.randomize_chart_modifier.value
        self.chart_modifier_change_chance = self.options.chart_modifier_change_chance.value
        self.unlock_type = self.options.unlock_type.value
        self.unlock_method = self.options.unlock_method.value
        self.songList = self.options.songList.value
        # Trap Settings
        self.trapAmount = self.options.trapAmount.value
        self.trapAmount = self.options.trapAmount.value
        self.trapAmount = self.options.trapAmount.value
        self.trapAmount = self.options.trapAmount.value
        self.trapAmount = self.options.trapAmount.value
        self.trapAmount = self.options.trapAmount.value
        self.trapAmount = self.options.trapAmount.value

    def create_regions(self):
        menu_region = Region("Freeplay", self.player, self.multiworld)
        self.multiworld.regions += [menu_region]

        all_selected_locations = self.songList.copy()
        self.random.shuffle(all_selected_locations)

        # Adds 2 item locations per song/album to the menu region.
        for i in range(0, len(all_selected_locations)):
            name = all_selected_locations[i]
            loc1 = FunkinLocation(self.player, name, self.funkinUtil.song_locations[name], menu_region)
            loc1.access_rule = lambda state, place=name: state.has(place, self.player)
            menu_region.locations.append(loc1)

            loc2 = FunkinLocation(self.player, name + "-1", self.md_collection.song_locations[name + "-1"],
                                    menu_region)
            loc2.access_rule = lambda state, place=name: state.has(place, self.player)
            menu_region.locations.append(loc2)

    def create_items(self):
        frequencies = self._create_traps()
        item_pool = self.songList

        for i, name in enumerate(item_groups):
            if i < len(frequencies):
                item_pool += self._create_item_in_quantities(
                    name, frequencies[i])

        self.multiworld.itempool += item_pool

    def set_rules(self):
        self.multiworld.completion_condition[self.player] = lambda state: \
            state.has_all_counts({"Booster Bumper": 5, "Treasure Bumper": 32, "Hazard Bumper": 25}, self.player)

    def fill_slot_data(self):
        return {
            "deathLink": self.options.death_link.value,
            "fullSongCount": len(self.songList)
        }