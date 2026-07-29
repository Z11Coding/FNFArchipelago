"""Shortcut Manager component."""

try:
    from worlds.LauncherComponents import Component, Type, components
    from . import launcher_hook
    
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
