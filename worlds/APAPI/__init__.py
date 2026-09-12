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
from .nested_hooks import wrap_runtime_local_function
from .options_api import list_global_options, register_global_option, register_global_options
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
    "list_global_options",
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
