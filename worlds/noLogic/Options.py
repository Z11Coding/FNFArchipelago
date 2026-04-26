# Copyright (c) 2024
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from dataclasses import dataclass
import logging
from Options import Toggle, Choice, Range, PerGameCommonOptions, OptionGroup, OptionSet



class AddProgressionItem(Toggle):
    """
    Whether to add a special progression item that links to all required progression items
    from each world in the multiworld. This item grants immediate access to everything.
    (Requires the No Logic Client to be connected, to receive the items.)
    """
    display_name = "Add Progression Item"
    default = False


class ProgressionItemType(Choice):
    """
    How the progression item should be distributed:
    - Per World: One item per world that contains that world's required progression items
    - Global: A single item that links to ALL worlds' progression items
    (Not currently fully implemented. Might work, not tested.)
    """
    display_name = "Progression Item Distribution"
    option_per_world = 0
    option_global = 1
    default = 1


class ProgressionItemLocality(Choice):
    """
    Where progression items from other worlds can be placed:
    - local: Each player's progression item can ONLY be placed in that player's own world (or No Logic)
    - non_local: Each player's progression item CANNOT be placed in that player's own world (must go elsewhere)
    - one_per_world: Non-local variant where only ONE progression item is allowed per world total
    - anywhere: No restrictions, items can be placed anywhere in the multiworld
    """
    display_name = "Progression Item Locality"
    option_local = 0
    option_non_local = 1
    option_one_per_world = 2
    option_anywhere = 3
    default = 3


class RemoveEntranceLogic(Toggle):
    """
    Whether to remove access rules from entrances (region connections).
    When enabled, all entrance requirements will also be ignored, meaning the seed could be even more impossible than it already is.
    Disable this if you want to keep entrance logic intact while still
    removing location access rules.
    """
    display_name = "Remove Entrance Logic"
    default = True


class RespectEarlyLocations(Toggle):
    """
    Whether to respect early location placement when removing logic.
    When enabled (True), logic removal happens at stage_pre_fill, which runs after
    early location placement has already occurred.
    When disabled (False), logic removal happens at stage_connect_entrances, which
    runs earlier and ignores early location considerations.
    """
    display_name = "Respect Early Locations"
    default = True


class NoProgressionMaze(Choice):
    """
    RISKY: When enabled, removes the original progression items from the pool and only provides
    the linked progression item. This can make the game unwinnable more often than not.
    Leave disabled for safer gameplay.
    Special Mode: Logical - Disables the no logic aspect of this APWorld in favor of a different unique check-hunting experience. (Made by request.)
    (Requires Progression Shards - In Percentage mode, for this option to work.)
    """
    display_name = "No Progression Maze"
    option_disabled = 0
    option_enabled = 1
    option_logical_mode = 2


class IncludeLesserProgression(Toggle):
    """
    When enabled, progression item collections will also include items classified as:
    - progression_skip_balancing
    - progression_deprioritized
    - progression_deprioritized_skip_balancing
    """
    display_name = "Include Lesser Progression Items"
    default = False

class IncludeUsefulProgressionItems(Toggle):
    """
    When enabled, progression item collections will also include items classified as:
    - useful progression. (Progression | Useful)
    """
    display_name = "Include Useful Progression Items"
    default = False

class IncludeUnusualProgressionItems(Toggle):
    """
    When enabled, progression item collections will also include items classified as:
    - progression items that don't fit into the above categories for whatever reason. (Anything with "progression" in the classification that isn't already included by the other options.)
    """
    display_name = "Include Unusual Progression Items"
    default = False

class ProgressionItemMode(Choice):
    """
    How progression items should be delivered:
    - Normal: The collected progression item is provided as-is (single item)
    - Shards - All: The progression item is split into shards; you must collect all shards to get all items
    - Shards - Percentage: As you collect shards, you progressively unlock items based on percentage collected
    - Shards - Percentage of Items: Shard count is calculated as a percentage of the number of progression items
    """
    display_name = "Progression Item Mode"
    option_normal = 0
    option_shards_all = 1
    option_shards_percentage = 2
    option_shards_percentage_of_items = 3
    default = 0

class FlexibleRange(Range):
    """
    A Range that allows out-of-bounds values with warnings instead of hard errors.
    Set allow_below_range and allow_above_range to control whether values outside bounds are permitted.
    When allowed, a warning is logged and verify() will prompt for confirmation.
    """
    allow_below_range: bool = False
    allow_above_range: bool = False
    
    def __init__(self, value: int):
        # Check bounds but allow if configured to do so
        if value < self.range_start:
            if not self.allow_below_range:
                raise Exception(f"{value} is lower than minimum {self.range_start} for option {self.__class__.__name__}")
            else:
                # Value is below range but allowed - store with warning
                logging.warning(f"{self.__class__.__name__}: {value} is below recommended minimum of {self.range_start}")
        elif value > self.range_end:
            if not self.allow_above_range:
                raise Exception(f"{value} is higher than maximum {self.range_end} for option {self.__class__.__name__}")
            else:
                # Value is above range but allowed - store with warning
                logging.warning(f"{self.__class__.__name__}: {value} is above recommended maximum of {self.range_end}")
        self.value = value
    
    def verify(self, world, player_name: str, plando_options) -> None:
        """Verify method called during world generation to warn about out-of-bounds values and request confirmation."""
        display_name = getattr(self, 'display_name', self.__class__.__name__)
        
        if self.value < self.range_start and self.allow_below_range:
            warning_msg = (
                f"Player {player_name}: {display_name} is set to {self.value}, which is below the recommended "
                f"minimum of {self.range_start}. This may cause unexpected behavior. Proceed? (y/n): "
            )
            response = input(warning_msg).strip().lower()
            if response != "y":
                raise Exception(f"Generation cancelled for player {player_name}. {display_name} out-of-bounds value was not confirmed.")
        elif self.value > self.range_end and self.allow_above_range:
            warning_msg = (
                f"Player {player_name}: {display_name} is set to {self.value}, which is above the recommended "
                f"maximum of {self.range_end}. This may cause unexpected behavior. Proceed? (y/n): "
            )
            response = input(warning_msg).strip().lower()
            if response != "y":
                raise Exception(f"Generation cancelled for player {player_name}. {display_name} out-of-bounds value was not confirmed.")

class ProgressionShardCount(FlexibleRange):
    """
    How many shards to split progression items into (only applies when using Shards mode).
    Recommended range: 5-200 shards. Values above 200 are allowed but may impact performance or make things much more difficult.
    (This option can be set above the maximum, but it's not recommended.)
    """
    display_name = "Progression Shard Count"
    range_start = 5
    range_end = 200
    default = 15
    allow_below_range = False
    allow_above_range = True

class ProgressionShardPercentage(FlexibleRange):
    """
    When using Shards - Percentage of Items mode, sets the shard count as a percentage of 
    the number of progression items. For example, if there are 10 progression items and this 
    is set to 200%, there will be 20 shards total. Recommended range: 10-1000%. 
    Values above 1000% are allowed but may impact performance, or make things much more difficult.
    (WARNING: This may cause fill errors at a high percentage! If you encounter fill errors, reduce this percentage or switch to a fixed shard count.)
    (This option can be set above the maximum, but it's not recommended.)
    """
    display_name = "Progression Shard Percentage"
    range_start = 10
    range_end = 1000
    default = 100
    allow_below_range = False
    allow_above_range = True

class AutoHintProgressionItems(Toggle):
    """
    When enabled, progression item locations will be automatically hinted when the game generates.
    This makes it easier to track which world each progression item comes from.
    """
    display_name = "Auto-Hint Progression Items"
    default = False


class FunnyFillers(Toggle):
    """
    When enabled, filler items will have random funny names instead of just "Filler".
    Purely cosmetic and doesn't affect gameplay.
    """
    display_name = "Funny Fillers"
    default = False


class ProgressionTrapWeight(Range):
    """
    Percentage chance (0-100%) that each filler item becomes a trap item instead.
    For example, 50% means approximately half of the filler items will be traps.
    Default: 0 (no traps).
    """
    display_name = "Progression Trap Weight"
    range_start = 0
    range_end = 100
    default = 0


class ProgressionTrapMode(Choice):
    """
    How traps are distributed across the multiworld:
    - Disabled: No traps are created
    - Global: Traps are shared randomly among all players
    - World-Specific: Each player gets their own trap(s) based on weight
    - Finders-Keepers: Trap goes to whoever finds it during normal fill
    """
    display_name = "Progression Trap Mode"
    option_disabled = 0
    option_global = 1
    option_world_specific = 2
    option_finders_keepers = 3
    default = 0


class ProgressionTrapLocality(Choice):
    """
    Where traps can be placed (only applies to World-Specific mode):
    - Anywhere: No restrictions
    - Local: Traps stay within their target world
    - Non-Local: Traps cannot be in their target world
    """
    display_name = "Progression Trap Locality"
    option_anywhere = 0
    option_local = 1
    option_non_local = 2
    default = 0


class GlobalShardsBehavior(Choice):
    """
    How claim_dict is organized when using global progression items with percentage-based shards:
    - Shared Pool: All locations stored under the shard item ID (classic behavior)
    - Per-Player: Locations organized by player ID instead of item ID
    (This option only affects global progression items with percentage modes.)
    """
    display_name = "Global Shards Behavior"
    option_shared_pool = 0
    option_per_player = 1
    default = 0


class MetaForceProgressionItems(OptionSet):
    """
    [No Logic Integration]
    Item names in this game that should be force-treated as Progression in a No Logic
    multiworld, regardless of their actual item classification.
    Useful for including Shards or other items not normally classified as Progression.
    List item names exactly as they appear in-game, comma-separated.
    """
    display_name = "Force Items as Progression (No Logic)"
    default = frozenset()


class MetaExcludeProgressionItems(OptionSet):
    """
    [No Logic Integration]
    Item names in this game that should be excluded from Progression collection in a No
    Logic multiworld, even if they would otherwise qualify by classification.
    List item names exactly as they appear in-game, comma-separated.
    """
    display_name = "Exclude Items from Progression (No Logic)"
    default = frozenset()


@dataclass
class NoLogicOptions(PerGameCommonOptions):
    add_progression_item: AddProgressionItem
    progression_item_type: ProgressionItemType
    progression_item_locality: ProgressionItemLocality
    remove_entrance_logic: RemoveEntranceLogic
    respect_early_locations: RespectEarlyLocations
    no_progression_maze: NoProgressionMaze
    include_lesser_progression: IncludeLesserProgression
    include_useful_progression_items: IncludeUsefulProgressionItems
    include_unusual_progression_items: IncludeUnusualProgressionItems
    progression_item_mode: ProgressionItemMode
    progression_shard_count: ProgressionShardCount
    progression_shard_percentage: ProgressionShardPercentage
    global_shards_behavior: GlobalShardsBehavior
    auto_hint_progression_items: AutoHintProgressionItems
    funny_fillers: FunnyFillers
    progression_trap_weight: ProgressionTrapWeight
    progression_trap_mode: ProgressionTrapMode
    progression_trap_locality: ProgressionTrapLocality
    nl_force_progression_items: MetaForceProgressionItems
    nl_exclude_progression_items: MetaExcludeProgressionItems


no_logic_option_groups = [
    OptionGroup("No Logic Options", [
        AddProgressionItem,
        ProgressionItemType,
        ProgressionItemLocality,
        RemoveEntranceLogic,
        RespectEarlyLocations,
        NoProgressionMaze,
        IncludeLesserProgression,
        IncludeUsefulProgressionItems,
        IncludeUnusualProgressionItems,
        ProgressionItemMode,
        ProgressionShardCount,
        ProgressionShardPercentage,
        GlobalShardsBehavior,
        AutoHintProgressionItems,
        FunnyFillers,
    ]),
    OptionGroup("Progression Traps", [
        ProgressionTrapWeight,
        ProgressionTrapMode,
        ProgressionTrapLocality,
    ]),
    OptionGroup("No Logic Meta Options", [
        MetaForceProgressionItems,
        MetaExcludeProgressionItems,
    ], start_collapsed=True),
]


# =============================================================================
# Import-time injection into PerGameCommonOptions and WebWorld option groups
# =============================================================================
# Done entirely within the NoLogic APWorld — no main Archipelago files modified.
#
# Strategy:
#   • Add nl_ to PerGameCommonOptions.__annotations__ → type_hints returns them
#     for every game → they appear in YAML templates universally.
#   • __init_subclass__ hook: injects nl_ into each new subclass's __annotations__
#     BEFORE @dataclass processes it, so the generated __init__ natively accepts
#     nl_ kwargs for worlds loaded after noLogic.
#   • MultiWorld.set_options patch: for worlds already compiled before noLogic,
#     strips nl_ kwargs from the constructor call (avoiding TypeError) and
#     attaches the values as plain attributes afterward.
#   • Insert "No Logic Meta Options" OptionGroup into WebWorld.option_groups
#     (covers all worlds without custom WebWorlds) and into each registered
#     custom WebWorld subclass — so the group appears by name in the
#     OptionsCreator and YAML templates for every game.
#   • Patch WebWorldRegister.__new__ so future custom WebWorld subclasses also
#     get the group inserted after their class is created.
# =============================================================================

_nl_meta_option_group = OptionGroup("No Logic Meta Options", [
    MetaForceProgressionItems,
    MetaExcludeProgressionItems,
], start_collapsed=True)


def _insert_nl_group_into(option_groups_list):
    """Insert _nl_meta_option_group before 'Item & Location Options' in the list.
    No-ops if the group is already present."""
    if any(g.name == "No Logic Meta Options" for g in option_groups_list):
        return
    for i, g in enumerate(option_groups_list):
        if g.name == "Item & Location Options":
            option_groups_list.insert(i, _nl_meta_option_group)
            return
    option_groups_list.append(_nl_meta_option_group)


def _inject_nologic_meta_options():
    """Inject nl_force/exclude_progression_items into PerGameCommonOptions so the
    options appear in every game's YAML template and OptionsCreator."""
    if 'nl_force_progression_items' in PerGameCommonOptions.__annotations__:
        return  # already injected (e.g. module reloaded)

    # 1. Add annotations to PerGameCommonOptions so type_hints includes them for all
    #    games, which makes them appear in YAML templates and OptionsCreator universally.
    PerGameCommonOptions.__annotations__['nl_force_progression_items'] = MetaForceProgressionItems
    PerGameCommonOptions.__annotations__['nl_exclude_progression_items'] = MetaExcludeProgressionItems

    # 2. Clear the type_hints LRU cache so the updated annotations are visible.
    try:
        from Options import OptionsMetaProperty
        OptionsMetaProperty.type_hints.fget.cache_clear()
    except Exception:
        pass

    # 3. Install __init_subclass__ on PerGameCommonOptions so that worlds loaded AFTER
    #    noLogic have nl_ added to their cls.__annotations__ BEFORE @dataclass processes
    #    them.  The @dataclass-generated __init__ then naturally accepts nl_ kwargs —
    #    no manual wrapping of any subclass __init__ is needed.
    _existing_subclass_hook = PerGameCommonOptions.__dict__.get('__init_subclass__')

    @classmethod
    def _nl_init_subclass_hook(cls, **kwargs):
        if _existing_subclass_hook is not None:
            _existing_subclass_hook.__func__(cls, **kwargs)
        else:
            super(PerGameCommonOptions, cls).__init_subclass__(**kwargs)
        if issubclass(cls, PerGameCommonOptions) and cls is not NoLogicOptions:
            cls.__annotations__.setdefault('nl_force_progression_items', MetaForceProgressionItems)
            cls.__annotations__.setdefault('nl_exclude_progression_items', MetaExcludeProgressionItems)

    PerGameCommonOptions.__init_subclass__ = _nl_init_subclass_hook

    # 4. Patch MultiWorld.set_options to handle worlds whose @dataclass __init__ was
    #    already compiled before this injection (alphabetically earlier worlds).
    #    For those worlds, nl_ kwargs are excluded from the constructor call to avoid
    #    TypeError, then set as plain attributes so NoLogic can read them uniformly.
    try:
        from BaseClasses import MultiWorld

        _orig_set_options = MultiWorld.set_options

        def _nl_set_options(multiworld_self, args):
            from worlds import AutoWorld as _AutoWorld
            for player in multiworld_self.player_ids:
                world_type = _AutoWorld.AutoWorldRegister.world_types[
                    multiworld_self.game[player]]
                multiworld_self.worlds[player] = world_type(multiworld_self, player)
                options_dataclass = world_type.options_dataclass
                dc_fields = getattr(options_dataclass, '__dataclass_fields__', {})
                # Build kwargs filtered to only the fields the constructor actually knows.
                multiworld_self.worlds[player].options = options_dataclass(**{
                    k: getattr(args, k)[player]
                    for k in options_dataclass.type_hints
                    if k in dc_fields
                })
                # For worlds without native nl_ support, attach values as plain attributes
                # so NoLogic can always read them regardless of loading order.
                if 'nl_force_progression_items' not in dc_fields:
                    opts = multiworld_self.worlds[player].options
                    opts.nl_force_progression_items = getattr(
                        args, 'nl_force_progression_items', {}
                    ).get(player, MetaForceProgressionItems(frozenset()))
                    opts.nl_exclude_progression_items = getattr(
                        args, 'nl_exclude_progression_items', {}
                    ).get(player, MetaExcludeProgressionItems(frozenset()))

        MultiWorld.set_options = _nl_set_options
    except Exception:
        pass

    # 5. Insert the "No Logic Meta Options" group into WebWorld.option_groups
    #    (the base class list, shared by all worlds without a custom WebWorld),
    #    and into the option_groups list of each already-registered custom
    #    WebWorld subclass.  noLogic's own WebWorld already has the group defined
    #    in no_logic_option_groups, so _insert_nl_group_into is a no-op for it.
    try:
        from worlds.AutoWorld import WebWorld, WebWorldRegister, AutoWorldRegister

        # Patch the base WebWorld.option_groups (covers all worlds using the default web)
        _insert_nl_group_into(WebWorld.option_groups)

        # Patch each registered world whose WebWorld subclass owns its own option_groups
        for _world_cls in AutoWorldRegister.world_types.values():
            _web_cls = type(_world_cls.web)
            if _web_cls is not WebWorld and 'option_groups' in _web_cls.__dict__:
                _insert_nl_group_into(_web_cls.option_groups)

        # Patch WebWorldRegister.__new__ so future custom WebWorld subclasses get
        # the group inserted right after their class is created by the metaclass.
        _orig_webworld_new = WebWorldRegister.__new__

        def _nl_webworld_new(mcs, name, bases, dct):
            cls = _orig_webworld_new(mcs, name, bases, dct)
            if 'option_groups' in dct and any(issubclass(b, WebWorld) for b in bases):
                _insert_nl_group_into(cls.option_groups)
            return cls

        WebWorldRegister.__new__ = _nl_webworld_new
    except Exception:
        pass


_inject_nologic_meta_options()
