from __future__ import annotations

from .core_hooks import (
    CORE_HOOK_TARGETS,
    initialize_core_hooks,
    list_core_hook_points,
    register_hard_wrapper,
    register_soft_after,
    register_soft_before,
)
from .hard_patch import register_after_patch, register_before_patch, register_scoped_local_wrapper
from .multiworld_api import (
    clear_current_multiworld,
    get_current_multiworld,
    get_multiworld_snapshot,
    has_current_multiworld,
    initialize_multiworld_features,
    require_current_multiworld,
    register_main_write_multidata_after,
    register_main_write_multidata_before,
    set_current_multiworld,
)
from .game_versions import check_world_version, get_world_version, is_game_loaded
from .debug import (
    dprint,
    dump_hook_stats,
    dump_referrer_report,
    get_hook_stats,
    hook_timer,
    is_debug_enabled,
    set_debug_enabled,
)
from .generation import KNOWN_STAGES, StageCallback, get_current_stage, initialize_stage_tracking, on_stage
from .injection import GameRef, inject_option, inject_world_behavior, list_injected_options
from .midgen import ExpansionSpec, LiveInjectError, inject_player_now
from .run_info import ensure_run_info, get_run_flags, get_spoiler_level, is_output_enabled
from .logic_api import first_blockades, sphere_summary_with_inventory
from .nested_hooks import wrap_runtime_local_function
from .options_api import (
    list_global_options,
    register_global_option,
    register_global_options,
    register_option_for_games,
)
from .variant_options import VariantOption
from .world_hooks import (
    CANCEL,
    HookAfter,
    HookBefore,
    HookWrapper,
    Unhook,
    hook_world_method,
    hook_worlds_for_game,
    patch_world_class_method,
)
from .world_ready import (
    get_world_type,
    is_game_available,
    on_worlds_loaded,
    when_game_available,
    worlds_loading_complete,
)
from .yaml_tools import (
    SafeFormatter,
    extract_player_names,
    format_player_name,
    iter_player_yaml_files,
    read_yaml_documents,
    read_yaml_documents_file,
    read_yaml_file,
    read_yaml_text,
    resolve_player_files_dir,
    resolve_player_name,
)
from .playthrough_model import (
    PlaythroughModel,
    SphereData,
    SphereLocationEntry,
    build_playthrough_model,
    decompose_logical_spheres,
)
from .soft_patch import FuncStack


__all__ = [
    "CORE_HOOK_TARGETS",
    "FuncStack",
    "initialize_core_hooks",
    "list_core_hook_points",
    "clear_current_multiworld",
    "get_current_multiworld",
    "get_multiworld_snapshot",
    "has_current_multiworld",
    "register_hard_wrapper",
    "register_before_patch",
    "register_after_patch",
    "register_scoped_local_wrapper",
    "register_soft_after",
    "register_soft_before",
    "require_current_multiworld",
    "register_main_write_multidata_before",
    "register_main_write_multidata_after",
    "set_current_multiworld",
    "register_global_option",
    "register_global_options",
    "register_option_for_games",
    "list_global_options",
    "KNOWN_STAGES",
    "StageCallback",
    "get_current_stage",
    "on_stage",
    "initialize_stage_tracking",
    "GameRef",
    "inject_option",
    "inject_world_behavior",
    "list_injected_options",
    "ExpansionSpec",
    "LiveInjectError",
    "inject_player_now",
    "ensure_run_info",
    "get_run_flags",
    "get_spoiler_level",
    "is_output_enabled",
    "CANCEL",
    "HookAfter",
    "HookBefore",
    "HookWrapper",
    "Unhook",
    "hook_world_method",
    "hook_worlds_for_game",
    "patch_world_class_method",
    "get_world_type",
    "is_game_available",
    "on_worlds_loaded",
    "when_game_available",
    "worlds_loading_complete",
    "SafeFormatter",
    "extract_player_names",
    "format_player_name",
    "iter_player_yaml_files",
    "read_yaml_documents",
    "read_yaml_documents_file",
    "read_yaml_file",
    "read_yaml_text",
    "resolve_player_files_dir",
    "resolve_player_name",
    "dprint",
    "dump_hook_stats",
    "dump_referrer_report",
    "get_hook_stats",
    "hook_timer",
    "is_debug_enabled",
    "set_debug_enabled",
    "check_world_version",
    "get_world_version",
    "is_game_loaded",
    "first_blockades",
    "sphere_summary_with_inventory",
    "VariantOption",
    "PlaythroughModel",
    "SphereData",
    "SphereLocationEntry",
    "build_playthrough_model",
    "decompose_logical_spheres",
    "wrap_runtime_local_function",
]


# Auto-activate APAPI core hooks when the world package is imported.
initialize_core_hooks()
initialize_multiworld_features()
initialize_stage_tracking()
ensure_run_info()
