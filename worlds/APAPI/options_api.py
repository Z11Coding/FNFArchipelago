from __future__ import annotations

from collections import OrderedDict
import inspect
import logging
import time
from typing import Any, Dict, List, Type

from BaseClasses import MultiWorld
from Options import Option, OptionGroup, PerGameCommonOptions, Range
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


class NotImplementedOption(Option[str]):
    """Sentinel for an option that does not exist in a world's version schema.

    Assigned (never rolled or defaulted) for option keys the rest of the
    multiworld has but this version never defined, so older worlds never
    silently receive "default" values for options that were never part of
    them. Loud on value use (prevents incorrect use in logic); safe to
    display (spoiler/log surfaces show "NotImplemented").
    """

    display_name = "Not Implemented"
    default = "NotImplemented"

    def __init__(self, option_key: str = "", game: str = "", version: str = "") -> None:
        self._option_key = str(option_key)
        self._game = str(game)
        self._version = str(version)

    @classmethod
    def from_any(cls, data: Any) -> "NotImplementedOption":
        if isinstance(data, NotImplementedOption):
            return data
        return cls()

    @property
    def value(self) -> str:  # type: ignore[override]
        raise NotImplementedError(
            f"Option '{self._option_key}' is not implemented"
            + (f" in {self._game}" if self._game else "")
            + (f" {self._version}" if self._version else "")
            + "; it must not be read for logic.")

    @property
    def current_option_name(self) -> str:
        return "NotImplemented"

    def __str__(self) -> str:
        return "NotImplemented"


def build_player_options(world_type: Any, args: Any, player: int,
                         option_union: Any = None, game: str = "",
                         version: str = "") -> Any:
    """Build one player's options object, tolerating schema divergence.

    Missing option keys (versioned schemas, globally injected options that
    postdate args) fall back to the option default instead of crashing,
    mirroring Generate's missing-option path. Keys the dataclass constructor
    does not accept are attached afterwards. Shared by the set_options loops
    so versioned and unversioned generations behave identically.

    option_union: keys present anywhere in this generation for the game. Keys
    the player's version schema lacks get a NotImplementedOption marker
    instead of a silent default, so older worlds never receive defaults for
    options that were never part of them (loud on value use, "NotImplemented"
    on display).
    """
    options_dataclass: type[PerGameCommonOptions] = world_type.options_dataclass
    type_hints = options_dataclass.type_hints
    kwargs: Dict[str, Any] = {}
    for option_key in type_hints:
        # args may lack keys that were injected into type_hints after
        # args was built (e.g. No Logic meta options registered globally
        # via a cleared type-hint cache), or keys another routed version
        # rolled but this player's version lacks. Fall back to the default.
        values = getattr(args, option_key, None)
        if isinstance(values, dict) and player in values:
            kwargs[option_key] = values[player]
        else:
            option_class = type_hints[option_key]
            kwargs[option_key] = option_class.from_any(option_class.default)

    init_params = set(inspect.signature(options_dataclass).parameters) - {"self"}
    overflow = {k: v for k, v in kwargs.items() if k not in init_params}
    ctor_kwargs = {k: v for k, v in kwargs.items() if k in init_params}

    options = options_dataclass(**ctor_kwargs)
    for option_key, option_value in overflow.items():
        setattr(options, option_key, option_value)
    if option_union:
        schema_keys = set(type_hints)
        for option_key in sorted(set(option_union)):
            if option_key in schema_keys or hasattr(options, option_key):
                continue
            try:
                setattr(options, option_key, NotImplementedOption(option_key, game, version))
            except Exception:
                continue
    return options


def _patch_multiworld_set_options() -> None:
    global _patched_set_options
    if _patched_set_options:
        return

    try:
        from .hard_patch import hard_patches
        if "BaseClasses.MultiWorld.set_options" in hard_patches.list_targets():
            # The updater's routing wrapper already carries an equivalent
            # tolerant loop; a direct assignment here would silently replace
            # it and drop per-player version routing.
            _patched_set_options = True
            return
    except Exception:
        pass

    original = MultiWorld.set_options

    def patched_set_options(self: MultiWorld, args: Any) -> None:
        # Prefer a routed versioned class when the updater assigned one;
        # otherwise use the registered class (unchanged behavior).
        routed = getattr(self, "_apapi_version_classes", None) or {}
        unions = getattr(self, "_apapi_option_union", None) or {}
        labels = getattr(self, "_apapi_version_labels", None) or {}
        for player in self.player_ids:
            game = self.game[player]
            world_type = routed.get(player) or AutoWorldRegister.world_types[game]
            self.worlds[player] = world_type(self, player)
            self.worlds[player].options = build_player_options(
                world_type, args, player,
                option_union=unions.get(game), game=game,
                version=labels.get(player, ""))

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
