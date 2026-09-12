from __future__ import annotations

from collections import OrderedDict
import inspect
from typing import Dict, List, Type

from BaseClasses import MultiWorld
from Options import OptionGroup, PerGameCommonOptions
from worlds.AutoWorld import AutoWorldRegister, WebWorld, WebWorldRegister


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

    def patched_new(mcs, name, bases, dct):
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

    def patched_set_options(self: MultiWorld, args) -> None:
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


def register_global_options(options: Dict[str, Type], group_name: str = "APAPI Global Options") -> None:
    for option_key, option_class in options.items():
        register_global_option(option_key, option_class, group_name=group_name)


def list_global_options() -> list[str]:
    return list(_registered_options)
