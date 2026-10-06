from dataclasses import dataclass

from Options import OptionDict, OptionGroup, PerGameCommonOptions, Toggle


class BlockedPlayerPairs(OptionDict):
    """Maps each player to the players with whom they cannot exchange items."""

    display_name = "Blocked Player Pairs"
    default = {}

class ActAsWhitelist(Toggle):
    """Treat the blocked player pairs as a whitelist instead of a blacklist.
    
    May cause issues if players are not included in the whitelist, while also allowing non-local."""

    display_name = "Act As Whitelist"
    default = False


class AllowForcedNonLocal(Toggle):
    """Allow players to block themselves, forcing all of their items to be non-local.
    
    Might cause generation issues depending on their options."""

    display_name = "Allow Forced Non-Local"
    default = False

class OneWayTrade(Toggle):
    """Allow players to set up one-way trades, where items can only be sent in one direction."""

    display_name = "One-Way Trade"
    default = False


@dataclass
class NTOptions(PerGameCommonOptions):
    blocked_player_pairs: BlockedPlayerPairs
    allow_forced_non_local: AllowForcedNonLocal
    one_way_trade: OneWayTrade
    act_as_whitelist: ActAsWhitelist


no_touchy_option_groups = [
    OptionGroup("No Touchy", [BlockedPlayerPairs, AllowForcedNonLocal, OneWayTrade, ActAsWhitelist]),
]