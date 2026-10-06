from __future__ import annotations

from collections import OrderedDict
import inspect
import logging
import time
from typing import Dict, List, Type

from BaseClasses import MultiWorld
from Options import OptionGroup, PerGameCommonOptions, Range
from worlds.AutoWorld import AutoWorldRegister, WebWorld, WebWorldRegister

from .debug import dprint
from .injection import GameRef

logger = logging.getLogger("APAPI.Options")


class FlexibleRange(Range):
    """
    A Range that allows out-of-bounds values with warnings instead of hard errors.

    Set ``allow_below_range`` / ``allow_above_range`` to permit values outside
    the bounds (below-range is still rejected unless explicitly allowed).
    When an out-of-bounds value is allowed, ``verify()`` warns; with
    ``needs_confirmation`` (default) it prompts to proceed like normal,
    otherwise it shows the warning for a moment and continues.
    """
    allow_below_range: bool = False
    allow_above_range: bool = False
    needs_confirmation: bool = True

    def __init__(self, value: int):
        # Check bounds but allow if configured to do so
        if value < self.range_start:
            if not self.allow_below_range:
                raise Exception(f"{value} is lower than minimum {self.range_start} for option {self.__class__.__name__}")
            else:
                # Value is below range but allowed - store with warning
                logger.warning(f"{self.__class__.__name__}: {value} is below recommended minimum of {self.range_start}")
        elif value > self.range_end:
            if not self.allow_above_range:
                raise Exception(f"{value} is higher than maximum {self.range_end} for option {self.__class__.__name__}")
            else:
                # Value is above range but allowed - store with warning
                logger.warning(f"{self.__class__.__name__}: {value} is above recommended maximum of {self.range_end}")
        self.value = value

    def _confirm_or_pause(self, warning_msg: str, player_name: str) -> None:
        display_name = getattr(self, "display_name", self.__class__.__name__)
        if self.needs_confirmation:
            try:
                response = input(warning_msg + "\nProceed? (y/n): ").strip().lower()
            except (EOFError, OSError):
                raise Exception(f"Generation cancelled for player {player_name}. "
                                f"{display_name} out-of-bounds value was not able to be confirmed.")
            if response != "y":
                raise Exception(f"Generation cancelled for player {player_name}. "
                                f"{display_name} out-of-bounds value was not confirmed.")
        else:
            # No confirmation needed: show the warning for a moment, then continue.
            logger.warning(warning_msg + "Continuing generation.")
            time.sleep(1)

    def verify(self, world, player_name: str, plando_options) -> None:
        """Warn about out-of-bounds values; confirm or pause, then continue."""
        display_name = getattr(self, "display_name", self.__class__.__name__)

        if self.value < self.range_start and self.allow_below_range:
            self._confirm_or_pause(
                f"Player {player_name}: {display_name} is set to {self.value}, which is below the recommended "
                f"minimum of {self.range_start}. This may cause unexpected behavior. ",
                player_name,
            )
        elif self.value > self.range_end and self.allow_above_range:
            self._confirm_or_pause(
                f"Player {player_name}: {display_name} is set to {self.value}, which is above the recommended "
                f"maximum of {self.range_end}. This may cause unexpected behavior. ",
                player_name,
            )


_registered_options: "OrderedDict[str, type]" = OrderedDict()
_group_names: Dict[str, tuple[List[type], bool]] = {}
_patched_webworld_register = False
_patched_set_options = False


def _clear_option_type_hint_cache() -> None:
    try:
        from Options import OptionsMetaProperty

        OptionsMetaProperty.type_hints.fget.cache_clear()
    except Exception:
        pass


def _insert_group_into(option_groups: list[OptionGroup], group: OptionGroup) -> None:
    for existing in option_groups:
        if existing.name == group.name:
            for option in group.options:
                if option not in existing.options:
                    existing.options.append(option)
            return

    for idx, existing in enumerate(option_groups):
        if existing.name == "Item & Location Options":
            option_groups.insert(idx, group)
            return
    option_groups.append(group)


def _build_group(name: str) -> OptionGroup:
    options, start_collapsed = _group_names[name]
    return OptionGroup(name, list(options), start_collapsed)


def _sync_webworld_groups() -> None:
    for group_name in _group_names:
        _insert_group_into(WebWorld.option_groups, _build_group(group_name))

    for world_type in AutoWorldRegister.world_types.values():
        web_class = world_type.web.__class__
        for group_name in _group_names:
            _insert_group_into(web_class.option_groups, _build_group(group_name))


def _patch_webworld_register() -> None:
    global _patched_webworld_register
    if _patched_webworld_register:
        return

    original_new = WebWorldRegister.__new__

    def patched_new(mcs: Any, name: str, bases: Any, dct: Any) -> Any:
        cls = original_new(mcs, name, bases, dct)
        for group_name in _group_names:
            _insert_group_into(cls.option_groups, _build_group(group_name))
        return cls

    WebWorldRegister.__new__ = patched_new
    _patched_webworld_register = True


def _patch_multiworld_set_options() -> None:
    global _patched_set_options
    if _patched_set_options:
        return

    original = MultiWorld.set_options

    def patched_set_options(self: MultiWorld, args: Any) -> None:
        from worlds import AutoWorld

        for player in self.player_ids:
            world_type = AutoWorld.AutoWorldRegister.world_types[self.game[player]]
            self.worlds[player] = world_type(self, player)

            options_dataclass: type[PerGameCommonOptions] = world_type.options_dataclass
            kwargs = {option_key: getattr(args, option_key)[player] for option_key in options_dataclass.type_hints}

            init_params = set(inspect.signature(options_dataclass).parameters) - {"self"}
            overflow = {k: v for k, v in kwargs.items() if k not in init_params}
            ctor_kwargs = {k: v for k, v in kwargs.items() if k in init_params}

            if overflow:
                self.worlds[player].options = options_dataclass(**ctor_kwargs)
                for option_key, option_value in overflow.items():
                    setattr(self.worlds[player].options, option_key, option_value)
            else:
                self.worlds[player].options = options_dataclass(**kwargs)

    MultiWorld.set_options = patched_set_options
    _patched_set_options = True


def register_global_option(
    option_key: str,
    option_class: Type,
    group_name: str = "APAPI Global Options",
    start_collapsed: bool = True,
) -> None:
    """
    Register an option class to be injected into all game options.

    APAPI itself registers nothing by default; worlds call this function to opt in.
    """
    existing = _registered_options.get(option_key)
    if existing and existing is not option_class:
        raise ValueError(
            f"Global option key {option_key} already registered with {existing.__name__}; "
            f"cannot replace with {option_class.__name__}."
        )

    _registered_options[option_key] = option_class
    if group_name not in _group_names:
        _group_names[group_name] = ([], start_collapsed)
    if option_class not in _group_names[group_name][0]:
        _group_names[group_name][0].append(option_class)

    annotations = PerGameCommonOptions.__annotations__
    if option_key not in annotations:
        annotations[option_key] = option_class
        _clear_option_type_hint_cache()

    _patch_webworld_register()
    _sync_webworld_groups()
    _patch_multiworld_set_options()
    dprint("options", f"registered global option '{option_key}' ({option_class.__name__})")


def register_global_options(options: Dict[str, Type], group_name: str = "APAPI Global Options") -> None:
    for option_key, option_class in options.items():
        register_global_option(option_key, option_class, group_name=group_name)


def register_option_for_games(
    option_key: str,
    option_class: Type,
    games: list[GameRef],
    group_name: str = "APAPI Add-On Options",
    start_collapsed: bool = True,
) -> None:
    """Inject ``option_class`` only into the listed games' options_dataclass.

    Each entry may be a game-name string or a world class directly.
    Delegates to :func:`worlds.APAPI.injection.inject_option`, which owns all
    waiting/patching exclusively (immediate, deferred, and late-register
    paths plus cooperative ``set_options`` value attach).
    """
    from .injection import inject_option

    inject_option(
        option_key,
        option_class,
        games=games,
        group_name=group_name,
        start_collapsed=start_collapsed,
    )


def list_global_options() -> list[str]:
    return list(_registered_options)
