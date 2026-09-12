# APAPI

APAPI is a core hooking helper package for Archipelago worlds.

## Features

1. Soft-patching with `FuncStack` and global hook points.
2. Hard-patching with wrapper chains around existing functions.
3. Experimental runtime patching for lexical local functions.
4. Global option injection API for other worlds.

## Soft-Patching

Register hooks against core hook point names.

```python
from worlds.APAPI import register_soft_before, register_soft_after


def before_main(args, seed=None, baked_server_options=None):
    print("before Main.main")


def after_main(args, seed=None, baked_server_options=None):
    print("after Main.main")


register_soft_before("core.main", before_main)
register_soft_after("core.main", after_main)
```

Hook functions must accept the same required arguments as the target function.

## Hard-Patching

Register wrappers around any dotted callable path.

```python
from worlds.APAPI import register_hard_wrapper


def logging_wrapper(next_callable, *args, **kwargs):
    print("wrapped call")
    return next_callable(*args, **kwargs)


register_hard_wrapper("Main.main", logging_wrapper)
```

## Core Hook Points

- `core.main` -> `Main.main`
- `core.multiworld_init` -> `BaseClasses.MultiWorld.__init__`
- `core.autoworld_call_single` -> `worlds.AutoWorld.call_single`
- `core.autoworld_call_all` -> `worlds.AutoWorld.call_all`
- `core.multiworld_get_spheres` -> `BaseClasses.MultiWorld.get_spheres`
- `core.multiworld_get_sendable_spheres` -> `BaseClasses.MultiWorld.get_sendable_spheres`
- `core.launcher_run_gui` -> `Launcher.run_gui`
- `core.commonclient_default` -> `CommonClient.ClientCommandProcessor.default`

APAPI applies these targets with deferred activation to avoid import-order recursion.

## Global Option Injection

APAPI does not ship built-in options. Worlds can register options to inject globally.

```python
from worlds.APAPI import register_global_option
from Options import Toggle


class MyGlobalToggle(Toggle):
    display_name = "My Global Toggle"
    default = False


register_global_option("my_global_toggle", MyGlobalToggle, group_name="My Integration")
```

## Experimental Nested Local Patching

Use this only for best-effort instrumentation of lexical local functions.

```python
from worlds.APAPI import wrap_runtime_local_function


def outer(...):
    def inner(...):
        ...


def wrap_inner(inner_func):
    def wrapped(*args, **kwargs):
        return inner_func(*args, **kwargs)
    return wrapped


patched_outer = wrap_runtime_local_function(outer, "inner", wrap_inner)
```

This path can fail depending on Python runtime behavior for frame locals.

## Built-in MultiWorld + UT Support

APAPI includes built-in world injection for Universal Tracker snapshot support.

1. APAPI ensures `host.yaml` contains:

```yaml
apapi:
    universal_tracker_snapshot:
        enabled: true
        verbose_location_log: true
```

2. When enabled, APAPI injects into all loaded world classes:
- `ut_can_gen_without_yaml = True`
- `interpret_slot_data` fallback staticmethod when a world does not define one
- `fill_slot_data` wrapper that appends APAPI UT snapshot fields

3. Injected slot_data fields:
- `apapi_ut_can_gen_without_yaml`
- `apapi_ut_snapshot_version`
- `apapi_ut_shared`
- `apapi_ut_player`

`apapi_ut_player` includes per-player reconstructed data such as locations/items/entrances and per-location sphere index. `apapi_ut_shared` includes seed-level metadata and sendable sphere groups.

4. Utility API:

```python
from worlds.APAPI import get_multiworld_snapshot

snapshot_by_player = get_multiworld_snapshot(multiworld)
```

Current active MultiWorld handle:

```python
from worlds.APAPI import get_current_multiworld, require_current_multiworld

mw = get_current_multiworld()  # None if not active yet
mw_required = require_current_multiworld()  # raises RuntimeError if missing
```

APAPI keeps this synchronized from `BaseClasses.MultiWorld.__init__` and `Main.main` return, so it tracks the actual object used by generation.

5. Built-in scoped hard hook for internal local function:
- target: `Main.main` local `write_multidata`
- soft hook stacks: `register_main_write_multidata_before`, `register_main_write_multidata_after`
