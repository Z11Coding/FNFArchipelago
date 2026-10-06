
# Register launcher component
try:
    from worlds.LauncherComponents import Component, Type, components
    from . import ap_hook
    
    export_component = Component(
        display_name="Export World Data",
        func=ap_hook.main,
        cli=True,
        component_type=Type.TOOL,
        description="Export all world metadata to a JSON file and open it."
    )
    components.append(export_component)
except Exception as e:
    print(f"[SP-YAML-PLUGIN] Could not register launcher component: {e}")