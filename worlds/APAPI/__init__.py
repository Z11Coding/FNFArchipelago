from __future__ import annotations

"""APAPI package exports."""

# Early tracer - logs first time root is set to DEBUG (the cause of Placed spam), deduped
try:
    import logging as _early_logging
    import traceback as _early_tb
    _orig_early_setLevel = _early_logging.Logger.setLevel
    _early_seen: set[str] = set()
    def _early_traced_setLevel(self, level):
        try:
            # Only log DEBUG sets, and only once per unique caller, skip our own progress wrapper
            if level == _early_logging.DEBUG:
                stack = "".join(_early_tb.format_stack(limit=10))
                if "progress.py" in stack and "_wrap" in stack:
                    return _orig_early_setLevel(self, level)
                key = stack.split("File")[-1][:250] if "File" in stack else stack[:250]
                if key not in _early_seen:
                    _early_seen.add(key)
                    import logging as _l
                    lvl_name = _l.getLevelName(level)
                    # Use print for early visibility before logger configured
                    print(f"[EARLY-TRACER] setLevel {lvl_name} on {getattr(self, 'name', 'root')} by:\n{stack}")
        except Exception:
            pass
        return _orig_early_setLevel(self, level)
    _early_logging.Logger.setLevel = _early_traced_setLevel  # type: ignore
except Exception:
    pass

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
    FlexibleRange,
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
from .appack import install_appack, list_top_level_folders
from .loader import initialize as initialize_appack_loader, install_appack_ui, scan_and_unpack_pending
from .generation_gate import initialize_generation_gate, wait_for_all_patches
from .progress import initialize_progress, is_progress_enabled, set_progress_enabled
from .fuzzy import did_you_mean, format_did_you_mean
from .launch_context import (
    GENERATE as LAUNCH_GENERATE,
    LAUNCHER as LAUNCH_LAUNCHER,
    SERVER as LAUNCH_SERVER,
    HOST as LAUNCH_HOST,
    CLIENT as LAUNCH_CLIENT,
    UPLOADER as LAUNCH_UPLOADER,
    OPTIONS_CREATOR as LAUNCH_OPTIONS_CREATOR,
    UNKNOWN as LAUNCH_UNKNOWN,
    get_launch_context,
    is_generate_context,
    is_launcher_context,
    is_server_context,
    is_uploader_context,
    should_skip_app_window,
    should_skip_gui_patch,
)


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
    "FlexibleRange",
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
    "install_appack",
    "list_top_level_folders",
    "initialize_appack_loader",
    "install_appack_ui",
    "scan_and_unpack_pending",
    "initialize_generation_gate",
    "wait_for_all_patches",
    "initialize_progress",
    "is_progress_enabled",
    "set_progress_enabled",
    "did_you_mean",
    "format_did_you_mean",
    "LAUNCH_GENERATE",
    "LAUNCH_LAUNCHER",
    "LAUNCH_SERVER",
    "LAUNCH_HOST",
    "LAUNCH_CLIENT",
    "LAUNCH_UPLOADER",
    "LAUNCH_OPTIONS_CREATOR",
    "LAUNCH_UNKNOWN",
    "get_launch_context",
    "is_generate_context",
    "is_launcher_context",
    "is_server_context",
    "is_uploader_context",
    "should_skip_app_window",
    "should_skip_gui_patch",
]


initialize_core_hooks()
initialize_multiworld_features()
initialize_stage_tracking()
ensure_run_info()
initialize_appack_loader()
initialize_generation_gate()
initialize_progress()
# VerboseCollectionState – detailed Fill failure reports (host.yaml apapi.verbose_collection_state.enabled)
try:
    from . import verbose_state as _verbose_state  # noqa: F401
except Exception:
    pass
