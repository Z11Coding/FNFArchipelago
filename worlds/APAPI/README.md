# APAPI

APAPI is a core hooking helper package for Archipelago worlds.

## Features

1. Soft-patching with `FuncStack` and global hook points.
2. Hard-patching with wrapper chains around existing functions.
3. Experimental runtime patching for lexical local functions.
4. Global option injection API for other worlds.
5. World method hooks (per-instance and class-level) with timing.
6. Load-order-safe patching: queue work until worlds finish loading.
7. Typed YAML reading helpers.
8. Debug printer (on by default) + generation stage tracking.

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

## Targeted Injection (APAPI handles everything)

Add-on packs stay declarative — two calls, no waiting or patching logic of
their own. APAPI exclusively handles load-order waiting, patching, and
option plumbing (NoLogic-style, but targeted per game):

```python
from worlds.APAPI import inject_option, inject_world_behavior

# 1. The setting, native to the target game's own options.
inject_option("grass_actual_filler", GrassActualFiller, games=["TUNIC"], group_name="Game Addons")

# 2. The behavior check, inside the target world's own method.
inject_world_behavior("TUNIC", "create_items", after=after_create_items, min_version=(4, 0, 0))
```

Each game entry may also be a world class directly when the caller already
has access to it (patched immediately, no lookup/waiting):

```python
from worlds.tunic import TunicWorld

inject_option("grass_actual_filler", GrassActualFiller, games=[TunicWorld])
inject_world_behavior(TunicWorld, "create_items", after=after_create_items)
```

- Loaded games patch now; missing games queue via `when_game_available`;
  later-registered games are covered by the register wrapper.
- Options get native `__init__` support (dataclass re-run) plus a
  cooperative `set_options` wrapper so values always land.
- `games=None` injects globally. See `list_injected_options()`.

## Live Slot Injection (mid-generation)

`inject_player_now(multiworld, spec)` adds a player to a *live*
MultiWorld. Nothing is immutable: it bumps `players`, invalidates
`player_ids` + `__cache_*` lookups, extends every per-player dict and the
three `RegionManager` caches, repairs `CollectionState`, instantiates the
world, and catches the newcomer up through the current stage.

Two hard rules (loud `LiveInjectError` otherwise): only during
`generate_early` (later stages have un-runnable per-player processing, and
the running `call_all` already materialized its tuple), and no item-link
groups yet (their ids already occupy the space above the player range).
Later stages evaluate `player_ids` fresh, so newcomers flow through.

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

## World Hooks (with timing)

```python
from worlds.APAPI import hook_world_method, patch_world_class_method

# Per-instance (from your own generate_early):
hook_world_method(tunic_world, "create_item", after=lambda result, name: None)

# Class-level, after loading completes (load order can never prevent it):
from worlds.APAPI import when_game_available
when_game_available("TUNIC", lambda cls: patch_world_class_method(
    "TUNIC", "create_items", wrapper=my_wrapper))
```

Every hook execution is timed; hooks slower than 1.0s warn, and a summary
is dumped after `generate_output`. See `get_hook_stats()` / `dump_hook_stats()`.

## Load-Order Safety

```python
from worlds.APAPI import on_worlds_loaded, when_game_available

on_worlds_loaded(lambda: ...)  # runs after all worlds finish loading
when_game_available("TUNIC", lambda cls: ...)  # cls or None if missing
```

## YAML Helpers

```python
from worlds.APAPI import read_yaml_documents_file, iter_player_yaml_files, resolve_player_files_dir
```

Typed wrappers over `Utils.parse_yaml`: single/multi-document reads,
player-file discovery (`--player_files_path` or settings), name extraction
and `{number}`/`{player}` formatting.

## Debug Printer

On by default. Disable with `APAPI_DEBUG=0` or `set_debug_enabled(False)`.
Logs init events, hook success/failure, stage begin/finish, and hook
durations to the `APAPI.Debug` logger via `dprint(tag, message)`.

Leak hunts: `APAPI_REFCOUNT_DEBUG=1` logs a gc referrer census of the
finished MultiWorld (who keeps it alive) via `dump_referrer_report`.

## Run State (spoiler/output flags)

Worlds never see `Main.main` args, so APAPI captures them:

```python
from worlds.APAPI import get_spoiler_level, is_output_enabled

level = get_spoiler_level()  # int, or None when unknown (fail open)
```

Used e.g. to decide between appending to the spoiler file vs. writing a
standalone file into the output zip.
