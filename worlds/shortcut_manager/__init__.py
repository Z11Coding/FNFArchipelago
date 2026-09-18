"""Shortcut Manager component — defers heavy init during generation."""

try:
    from worlds.LauncherComponents import Component, Type, components
    from . import launcher_hook

    # Only register Launcher component when not generating; Generate shouldn't pollute LauncherComponents
    # Uploader is allowed (not Generate), Launcher itself is allowed
    _skip = False
    try:
        from worlds.APAPI.launch_context import should_skip_gui_patch
        _skip = should_skip_gui_patch()
    except Exception:
        pass
    if _skip:
        print("[SHORTCUT-MANAGER] Skipping component registration during generation")
    else:
        export_component = Component(
            display_name="Shortcut Manager",
            func=launcher_hook.main,
            cli=True,
            component_type=Type.TOOL,
            description="Create and manage shortcuts that appear in the Launcher."
        )
        components.append(export_component)
except Exception as e:
    print(f"[SHORTCUT-MANAGER] Could not register launcher component: {e}")
