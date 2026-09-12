from collections import defaultdict
from typing import ClassVar, Type

from BaseClasses import Item, ItemClassification, MultiWorld
from Options import PerGameCommonOptions
from worlds.AutoWorld import World, WebWorld
from worlds.NoTouchy.options import NTOptions, no_touchy_option_groups

def create_fake_ID_list(ids:int) -> dict[str, int]:
    fake_ids = {}
    for i in range(1, ids + 1):
        fake_ids[f"dud_{i}"] = i
    return fake_ids


class UselessWebWorld(WebWorld):
    game: str = "No Touchy"
    base_url: str = "https://no-touchy.wow.com"
    description: str = "dumb"

class NoTouchyWorld(World):
    """NoTouchy World for Archipelago
    
    Makes it so some players can't get certain items from other players. Why? Who knows.
    """
    game: str = "NoTouchy"

    options: NTOptions
    options_dataclass: ClassVar[Type[PerGameCommonOptions]] = NTOptions

    web = UselessWebWorld()
    web.option_groups = no_touchy_option_groups

    item_name_to_id: ClassVar[dict[str, int]] = create_fake_ID_list(10)
    location_name_to_id: ClassVar[dict[str, int]] = create_fake_ID_list(10)

    def __init__(self, multiworld: MultiWorld, player: int) -> None:
        super().__init__(multiworld, player)

    def generate_early(self):
        pass

    @staticmethod
    def stage_pre_fill(multiworld: MultiWorld) -> None:
        no_touchy_worlds = [
            world for world in multiworld.worlds.values()
            if isinstance(world, NoTouchyWorld)
        ]
        if len(no_touchy_worlds) != 1:
            raise ValueError("NoTouchy requires exactly one NoTouchy player.")

        controller_player_id = next(
            player for player, world in multiworld.worlds.items()
            if world is no_touchy_worlds[0]
        )
        blocked_player_pairs = no_touchy_worlds[0].options.blocked_player_pairs.value
        if not blocked_player_pairs:
            return

        player_ids_by_name = {name: player for player, name in multiworld.player_name.items()}
        controller_player_name = multiworld.player_name[controller_player_id]
        player_names = set()
        for player_name, blocked_player_names in blocked_player_pairs.items():
            if not isinstance(player_name, str):
                raise ValueError("NoTouchy blocked_player_pairs keys must be player names.")
            if not isinstance(blocked_player_names, list):
                raise ValueError(
                    f"NoTouchy blocked_player_pairs[{player_name!r}] must be a list of player names."
                )
            if not all(isinstance(name, str) for name in blocked_player_names):
                raise ValueError(
                    f"NoTouchy blocked_player_pairs[{player_name!r}] must contain only player names."
                )
            player_names.add(player_name)
            player_names.update(blocked_player_names)

        unknown_player_names = player_names - player_ids_by_name.keys()
        if unknown_player_names:
            raise ValueError(
                "NoTouchy blocked_player_pairs contains unknown player name(s): "
                + ", ".join(sorted(unknown_player_names))
            )
        if controller_player_name in player_names:
            raise ValueError("NoTouchy cannot be included in blocked_player_pairs.")

        blocked_player_ids = defaultdict(set)


        act_as_whitelist = no_touchy_worlds[0].options.act_as_whitelist.value

        for player_name, blocked_player_names in blocked_player_pairs.items():
            player_id = player_ids_by_name[player_name]
            for blocked_player_name in blocked_player_names:
                blocked_player_id = player_ids_by_name[blocked_player_name]
                if player_id == blocked_player_id and not no_touchy_worlds[0].options.allow_forced_non_local.value:
                    raise ValueError("NoTouchy players cannot be blocked from themselves.")
                blocked_player_ids[player_id].add(blocked_player_id)
                if no_touchy_worlds[0].options.one_way_trade.value:
                    continue
                blocked_player_ids[blocked_player_id].add(player_id)

        for location in multiworld.get_locations():
            if location.player == controller_player_id or location.player not in blocked_player_ids:
                continue
            old_rule = location.item_rule
            location.item_rule = lambda item, old_rule=old_rule, location_player=location.player, whitelist=act_as_whitelist: (
                old_rule(item) and (item.player not in blocked_player_ids[location_player] if not whitelist else item.player in blocked_player_ids[location_player])
            )

    def create_regions(self):
        pass

    def set_rules(self):
        pass

    def generate_basic(self):
        pass

    def create_item(self, name: str) -> Item:
        return Item(name, ItemClassification.progression, None)