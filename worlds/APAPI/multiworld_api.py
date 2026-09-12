from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
import functools
import logging
import sys
import threading
import time
from typing import Any, TYPE_CHECKING

from worlds.AutoWorld import AutoWorldRegister

from .core_hooks import register_soft_after, register_soft_before
from .hard_patch import hard_patches, register_scoped_local_wrapper
from .host_config import get_universal_tracker_snapshot_config, is_universal_tracker_snapshot_enabled
from .playthrough_model import decompose_logical_spheres
from .soft_patch import FuncStack

if TYPE_CHECKING:
    from BaseClasses import MultiWorld


logger = logging.getLogger("APAPI")


_world_fill_slot_data_patched: set[type] = set()
_bootstrap_done = False
_main_scoped_wrapper_done = False
_main_return_wrapper_done = False

_current_multiworld_lock = threading.RLock()
_current_multiworld: "MultiWorld | None" = None
_current_multiworld_local = threading.local()

# Internal scoped hook point for Main.main -> local write_multidata()
_write_multidata_before = FuncStack(return_as=list, global_return_type=type(None))
_write_multidata_after = FuncStack(return_as=list, global_return_type=type(None))


def register_main_write_multidata_before(hook: Callable[[], None]) -> None:
    _write_multidata_before.push(hook, return_type=type(None))


def register_main_write_multidata_after(hook: Callable[[], None]) -> None:
    _write_multidata_after.push(hook, return_type=type(None))


def set_current_multiworld(multiworld: "MultiWorld | None") -> None:
    """Set the currently active MultiWorld handle for APAPI consumers."""
    global _current_multiworld
    with _current_multiworld_lock:
        _current_multiworld = multiworld
    _current_multiworld_local.value = multiworld


def clear_current_multiworld() -> None:
    set_current_multiworld(None)


def get_current_multiworld(default: "MultiWorld | None" = None) -> "MultiWorld | None":
    """Return current MultiWorld if known, preferring thread-local context."""
    local_value = getattr(_current_multiworld_local, "value", None)
    if local_value is not None:
        return local_value
    with _current_multiworld_lock:
        return _current_multiworld if _current_multiworld is not None else default


def require_current_multiworld() -> "MultiWorld":
    current = get_current_multiworld()
    if current is None:
        raise RuntimeError("APAPI current multiworld is not available yet.")
    return current


def has_current_multiworld() -> bool:
    return get_current_multiworld() is not None


def _build_sphere_maps(multiworld: "MultiWorld") -> tuple[dict[int, int], list[dict[int, list[int]]]]:
    sphere_index_by_location_obj: dict[int, int] = {}
    sendable_spheres: list[dict[int, list[int]]] = []

    reachable_spheres, _unreachable = decompose_logical_spheres(multiworld)
    for sphere_index, sphere in enumerate(reachable_spheres):
        by_player: dict[int, list[int]] = defaultdict(list)
        for location in sphere:
            sphere_index_by_location_obj[id(location)] = sphere_index
            if isinstance(location.address, int) and location.item and isinstance(location.item.code, int):
                by_player[location.player].append(location.address)
        sendable_spheres.append({player: sorted(ids) for player, ids in by_player.items()})

    return sphere_index_by_location_obj, sendable_spheres


def _build_entrance_snapshot(multiworld: "MultiWorld") -> dict[int, list[dict[str, Any]]]:
    by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for region in multiworld.regions:
        for entrance in region.exits:
            by_player[region.player].append(
                {
                    "name": entrance.name,
                    "parent_region": region.name,
                    "connected_region": entrance.connected_region.name if entrance.connected_region else None,
                }
            )
    return {player: entries for player, entries in by_player.items()}


def _build_ut_snapshot_for_multiworld(multiworld: "MultiWorld") -> dict[int, dict[str, Any]]:
    cfg = get_universal_tracker_snapshot_config()
    verbose_location_log = bool(cfg.get("verbose_location_log", True))

    sphere_index_by_location_obj, sendable_spheres = _build_sphere_maps(multiworld)
    entrances_by_player = _build_entrance_snapshot(multiworld)

    locations_by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    items_by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for location in multiworld.get_filled_locations():
        location_id = location.address if isinstance(location.address, int) else None
        item_id = location.item.code if location.item and isinstance(location.item.code, int) else None
        sphere_index = sphere_index_by_location_obj.get(id(location), -1)

        location_record = {
            "location_name": location.name,
            "location_id": location_id,
            "location_player": location.player,
            "item_name": location.item.name if location.item else None,
            "item_id": item_id,
            "item_player": location.item.player if location.item else None,
            "item_flags": int(location.item.flags) if location.item else 0,
            "sphere": sphere_index,
        }
        locations_by_player[location.player].append(location_record)

        if location.item:
            items_by_player[location.item.player].append(
                {
                    "item_name": location.item.name,
                    "item_id": item_id,
                    "location_name": location.name,
                    "location_id": location_id,
                    "location_player": location.player,
                    "sphere": sphere_index,
                }
            )

        if verbose_location_log:
            logger.info(
                "[APAPI][UT] P%s Loc '%s' id=%s -> %s (P%s, id=%s) sphere=%s",
                location.player,
                location.name,
                location_id,
                location.item.name if location.item else "None",
                location.item.player if location.item else "?",
                item_id,
                sphere_index,
            )

    players_snapshot = {
        player: {
            "player_name": multiworld.player_name.get(player, f"Player {player}"),
            "game": multiworld.game.get(player, "Unknown"),
            "locations": locations_by_player.get(player, []),
            "incoming_items": items_by_player.get(player, []),
            "entrances": entrances_by_player.get(player, []),
        }
        for player in multiworld.player_ids
    }

    shared_metadata = {
        "seed_name": multiworld.seed_name,
        "players": {
            player: {
                "name": multiworld.player_name.get(player, f"Player {player}"),
                "game": multiworld.game.get(player, "Unknown"),
            }
            for player in multiworld.player_ids
        },
        "sendable_spheres": sendable_spheres,
    }

    return {
        player: {
            "ut_can_gen_without_yaml": True,
            "apapi_ut_snapshot_version": 1,
            "apapi_ut_shared": shared_metadata,
            "apapi_ut_player": players_snapshot[player],
        }
        for player in multiworld.player_ids
    }


def get_multiworld_snapshot(multiworld: "MultiWorld") -> dict[int, dict[str, Any]]:
    """Public helper: build (or return cached) APAPI UT snapshot for this multiworld."""
    cached = getattr(multiworld, "_apapi_ut_snapshot_by_player", None)
    if isinstance(cached, dict):
        return cached
    built = _build_ut_snapshot_for_multiworld(multiworld)
    setattr(multiworld, "_apapi_ut_snapshot_by_player", built)
    return built


def _default_interpret_slot_data(slot_data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(slot_data, Mapping):
        return {}
    snapshot = slot_data.get("apapi_ut_player")
    if isinstance(snapshot, dict):
        return dict(snapshot)
    return {}


def _patch_world_fill_slot_data(world_type: type) -> None:
    if world_type in _world_fill_slot_data_patched:
        return

    original_fill_slot_data = world_type.fill_slot_data

    @functools.wraps(original_fill_slot_data)
    def patched_fill_slot_data(self, *args: Any, **kwargs: Any):
        result = original_fill_slot_data(self, *args, **kwargs)
        if not isinstance(result, dict):
            result = {}

        if not is_universal_tracker_snapshot_enabled():
            return result

        multiworld = getattr(self, "multiworld", None)
        player = getattr(self, "player", None)
        if multiworld is None or not isinstance(player, int):
            return result

        snapshot_by_player = get_multiworld_snapshot(multiworld)
        snapshot = snapshot_by_player.get(player, {})

        result.setdefault("apapi_ut_can_gen_without_yaml", True)
        result.setdefault("apapi_ut_snapshot_version", snapshot.get("apapi_ut_snapshot_version", 1))
        result.setdefault("apapi_ut_shared", snapshot.get("apapi_ut_shared", {}))
        result.setdefault("apapi_ut_player", snapshot.get("apapi_ut_player", {}))

        return result

    world_type.fill_slot_data = patched_fill_slot_data

    # Universal Tracker checks these fields on the world class.
    setattr(world_type, "ut_can_gen_without_yaml", True)
    if not callable(getattr(world_type, "interpret_slot_data", None)):
        setattr(world_type, "interpret_slot_data", staticmethod(_default_interpret_slot_data))

    _world_fill_slot_data_patched.add(world_type)


def _inject_world_tracker_support() -> None:
    if not is_universal_tracker_snapshot_enabled():
        return
    for world_type in AutoWorldRegister.world_types.values():
        _patch_world_fill_slot_data(world_type)


def _wrap_main_local_write_multidata(local_func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(local_func)
    def wrapped_local(*args: Any, **kwargs: Any):
        _write_multidata_before()
        result = local_func(*args, **kwargs)
        _write_multidata_after()
        return result

    return wrapped_local


def _install_main_scoped_wrapper_deferred() -> None:
    global _main_scoped_wrapper_done
    if _main_scoped_wrapper_done:
        return

    for _ in range(240):
        if "Main" in sys.modules:
            try:
                register_scoped_local_wrapper(
                    "Main.main",
                    "write_multidata",
                    _wrap_main_local_write_multidata,
                    load_missing=False,
                )
                _main_scoped_wrapper_done = True
            except Exception as exc:
                logger.warning("APAPI could not install write_multidata scoped hook: %s", exc)
            return
        time.sleep(0.5)


def _main_return_wrapper(next_callable: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    clear_current_multiworld()
    result = next_callable(*args, **kwargs)
    if result is not None:
        set_current_multiworld(result)
    return result


def _install_main_return_wrapper_deferred() -> None:
    global _main_return_wrapper_done
    if _main_return_wrapper_done:
        return

    for _ in range(240):
        if "Main" in sys.modules:
            try:
                hard_patches.add_wrapper("Main.main", _main_return_wrapper, load_missing=False)
                _main_return_wrapper_done = True
            except Exception as exc:
                logger.warning("APAPI could not install Main.main return wrapper: %s", exc)
            return
        time.sleep(0.5)


def _before_main(*_args: Any, **_kwargs: Any) -> None:
    clear_current_multiworld()
    _inject_world_tracker_support()


def _after_multiworld_init(multiworld: "MultiWorld", *_args: Any, **_kwargs: Any) -> None:
    set_current_multiworld(multiworld)


def initialize_multiworld_features() -> None:
    global _bootstrap_done
    if _bootstrap_done:
        return

    # Ensure host config exists and bootstrap world-level tracker support before generation.
    get_universal_tracker_snapshot_config()
    register_soft_before("core.main", _before_main)
    register_soft_after("core.multiworld_init", _after_multiworld_init)

    # Built-in scoped-local hard patch target (Main.main -> write_multidata).
    scoped_thread = threading.Thread(target=_install_main_scoped_wrapper_deferred, name="APAPI-ScopedMain", daemon=True)
    scoped_thread.start()

    # Capture the authoritative multiworld object returned by Main.main.
    main_thread = threading.Thread(target=_install_main_return_wrapper_deferred, name="APAPI-MainReturn", daemon=True)
    main_thread.start()

    _bootstrap_done = True
