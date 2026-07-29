"""Launcher Hook for Shortcut Manager - integrates shortcuts into launcher components."""

from pathlib import Path
from typing import Optional
from Utils import local_path, user_path

from .shortcut_manager import ShortcutStorage, ShortcutExecutor
from .structures import ShortcutCollection, LinkType, Shortcut, ShortcutType

# Module-level flag to prevent re-entry during initialization
_initialization_in_progress = False

# Track if launcher confirmed running or confirmed NOT a launcher, for atexit restart mechanism
# Only restart on exit if this stays False (meaning launcher crashed before it could be identified)
_exit_normally = False


def _find_shortcut_manager_world() -> Path:
    """Find the shortcut_manager world path (dev or apworld)."""
    dev_path = Path(local_path()) / "worlds" / "shortcut_manager"
    if dev_path.exists() and dev_path.is_dir():
        return dev_path
    apworld_path = Path(user_path()) / "custom_worlds" / "shortcut_manager.apworld"
    if apworld_path.exists() and apworld_path.is_file():
        return apworld_path
    return dev_path


def _patch_install_apworld() -> None:
    """Patch LauncherComponents.install_apworld to preserve shortcut_manager shortcuts on any APWorld install."""
    try:
        from worlds import LauncherComponents
        from .shortcut_manager import ShortcutStorage
        
        original_install_apworld = LauncherComponents._install_apworld
        
        def patched_install_apworld(apworld_src: str = ""):
            # Load existing shortcut_manager shortcuts BEFORE installation
            existing_shortcuts = None
            try:
                world_path = _find_shortcut_manager_world()
                if world_path.exists():
                    existing_shortcuts = ShortcutStorage.load_shortcuts(world_path)
                    print(f"[SHORTCUT-MANAGER] Backed up shortcuts before install")
            except Exception as e:
                print(f"[SHORTCUT-MANAGER] Failed to load shortcuts before install: {e}")
            
            # Run original install function
            result = original_install_apworld(apworld_src)
            
            # Resave shortcuts after installation
            if existing_shortcuts:
                try:
                    world_path = _find_shortcut_manager_world()
                    ShortcutStorage.save_shortcuts(world_path, existing_shortcuts)
                    print(f"[SHORTCUT-MANAGER] Preserved shortcuts to {world_path}")
                except Exception as e:
                    print(f"[SHORTCUT-MANAGER] Failed to save to main location, backing up: {e}")
                    # Save to backup location as fallback
                    try:
                        ShortcutStorage.save_shortcuts_backup("shortcut_manager", existing_shortcuts)
                        print(f"[SHORTCUT-MANAGER] Backed up shortcuts for later restoration")
                    except Exception as backup_e:
                        print(f"[SHORTCUT-MANAGER] Backup failed: {backup_e}")
            
            return result
        
        LauncherComponents._install_apworld = patched_install_apworld
        print("[SHORTCUT-MANAGER] Patched install_apworld for shortcut preservation")
    except Exception as e:
        print(f"[SHORTCUT-MANAGER] Failed to patch install_apworld: {e}")


def _restore_apworld_shortcuts_from_backup() -> None:
    """Restore shortcut_manager shortcuts from backup location if they exist."""
    try:
        from .shortcut_manager import ShortcutStorage
        
        collection = ShortcutStorage.load_shortcuts_backup("shortcut_manager")
        if collection:
            try:
                world_path = _find_shortcut_manager_world()
                if world_path.exists():
                    ShortcutStorage.save_shortcuts(world_path, collection)
                    print(f"[SHORTCUT-MANAGER] Restored shortcuts from backup")
            except Exception as e:
                print(f"[SHORTCUT-MANAGER] Failed to restore backup: {e}")
    except Exception as e:
        print(f"[SHORTCUT-MANAGER] Backup restoration check failed: {e}")


def _migrate_invalid_icons(collection: ShortcutCollection) -> None:
    """Replace invalid icons with 'icon' and save."""
    try:
        from worlds.LauncherComponents import icon_paths
    except ImportError:
        return
    
    valid_icon_names = set(icon_paths.keys())
    updated = False
    
    for shortcut in collection.shortcuts:
        if not shortcut.icon:
            shortcut.icon = "icon"
            updated = True
        elif shortcut.icon not in valid_icon_names and not (
            shortcut.icon.endswith(('.png', '.jpg', '.jpeg', '.gif')) or 
            '\\' in shortcut.icon or '/' in shortcut.icon
        ):
            shortcut.icon = "icon"
            updated = True
    
    if updated:
        try:
            world_path = _find_shortcut_manager_world()
            ShortcutStorage.save_shortcuts(world_path, collection)
        except Exception as e:
            print(f"[SHORTCUT-MANAGER] Failed to save migrated shortcuts: {e}")


def _load_shortcuts() -> Optional[ShortcutCollection]:
    """Load and validate shortcuts from storage."""
    try:
        world_path = _find_shortcut_manager_world()
        collection = ShortcutStorage.load_shortcuts(world_path)
        if collection:
            _migrate_invalid_icons(collection)
        return collection
    except Exception as e:
        print(f"[SHORTCUT-MANAGER] Failed to load shortcuts: {e}")
        return None


def _register_custom_icon(icon_key: str, image_path: Path) -> Path | None:
    """Resize icon to 48x48 and save to temp, return path or None."""
    try:
        from worlds.LauncherComponents import icon_paths
    except ImportError:
        return None
    
    try:
        from PIL import Image
        import tempfile
        
        img = Image.open(image_path)
        if img.size != (48, 48):
            img = img.resize((48, 48), Image.Resampling.LANCZOS)
        
        temp_dir = Path(tempfile.gettempdir()) / "archipelago_shortcuts"
        temp_dir.mkdir(exist_ok=True)
        safe_name = icon_key.replace(":", "_")
        output_path = temp_dir / f"{safe_name}.png"
        img.save(output_path, "PNG")
        icon_paths[icon_key] = str(output_path)
        return output_path
    except ImportError:
        icon_paths[icon_key] = str(image_path)
        return None
    except Exception as e:
        print(f"[SHORTCUT-MANAGER] Failed to process custom icon {image_path}: {e}")
        icon_paths[icon_key] = str(image_path)
        return None


def register_shortcuts_as_components(collection: ShortcutCollection) -> None:
    """Create launcher components for each shortcut."""
    try:
        from worlds.LauncherComponents import Component, Type, components, icon_paths
    except ImportError:
        return
    if not collection:
        return
    
    valid_icon_names = set(icon_paths.keys())
    for shortcut in collection.shortcuts:
        def make_executor(sc=shortcut):
            def executor(*args):
                ShortcutExecutor.execute(sc)
            return executor
        
        try:
            component_type = Type[shortcut.component_type]
        except (KeyError, AttributeError):
            component_type = Type.MISC
        
        icon_to_use = shortcut.icon or "icon"
        
        if icon_to_use and (icon_to_use.endswith(('.png', '.jpg', '.jpeg', '.gif')) or '\\' in icon_to_use or '/' in icon_to_use):
            try:
                icon_path = Path(icon_to_use)
                if icon_path.exists():
                    icon_key = f"shortcut:{shortcut.name}"
                    temp_icon_path = _register_custom_icon(icon_key, icon_path)
                    if temp_icon_path:
                        shortcut.temp_icon_path = str(temp_icon_path)
                    icon_to_use = icon_key
                else:
                    icon_to_use = "icon"
            except Exception:
                icon_to_use = "icon"
        elif icon_to_use not in valid_icon_names:
            icon_to_use = "icon"
        
        component = Component(
            display_name=shortcut.name,
            func=make_executor(),
            cli=False,
            component_type=component_type,
            icon=icon_to_use,
            description=shortcut.description,
        )
        components.append(component)


def _make_primary_shortcut_wrapper(original_func, primary_shortcut, component):
    """Wrap component func to show choice dialog between component and shortcut."""
    def wrapped_func(*args, **kwargs):
        try:
            import subprocess
            from Launcher import get_exe, launch as launcher_launch
            
            def execute_component():
                if original_func:
                    original_func(*args, **kwargs)
                else:
                    exe = get_exe(component)
                    if exe:
                        launcher_launch(exe, component.cli)
                    else:
                        print(f"[SHORTCUT-MANAGER] Cannot execute {component.display_name}")
            
            import sys, time
            for _ in range(50):
                if 'kvui' in sys.modules:
                    break
                time.sleep(0.05)
            
            if 'kvui' in sys.modules:
                from kvui import ButtonsPrompt
                from kivy.app import App
                
                def handle_response(choice, _execute_component=execute_component):
                    if choice == component.display_name:
                        _execute_component()
                    elif choice == primary_shortcut.name:
                        _execute_linked_shortcut(primary_shortcut, component)
                    dialog.dismiss()
                
                dialog = ButtonsPrompt(
                    "Choose Action",
                    "Which would you like to open?",
                    handle_response,
                    component.display_name,
                    primary_shortcut.name
                )
                app = App.get_running_app()
                if app:
                    dialog.open()
                else:
                    execute_component()
            else:
                execute_component()
        except Exception as e:
            print(f"[SHORTCUT-MANAGER] Error in wrapped func: {e}")
            try:
                if original_func:
                    original_func(*args, **kwargs)
                else:
                    import subprocess
                    from Launcher import get_exe
                    exe = get_exe(component)
                    if exe:
                        subprocess.Popen([*exe, *args])
            except Exception as fallback_e:
                print(f"[SHORTCUT-MANAGER] Fallback failed: {fallback_e}")
    return wrapped_func


def _wrap_component_func_with_shortcut(original_func, primary_shortcut, component):
    """Wrap a component's func to prompt for choice between component and shortcut."""
    return _make_primary_shortcut_wrapper(original_func, primary_shortcut, component)


def _get_icon_for_shortcut_type(shortcut_type: ShortcutType, has_args: bool = False) -> str:
    """Map shortcut type to Material Design icon name."""
    icons = {
        ShortcutType.SCRIPT: "application-braces",
        ShortcutType.EXECUTABLE: "application-array" if has_args else "application",
        ShortcutType.FOLDER: "folder",
        ShortcutType.URL: "web",
        ShortcutType.FUNCTION: "function-variant" if has_args else "function",
        ShortcutType.WINE: "glass-wine",
        ShortcutType.STEAM: "steam",
    }
    return icons.get(shortcut_type, "star-plus")


def patch_components_with_linked_shortcuts(collection: ShortcutCollection) -> None:
    """Link shortcuts to components and wrap component funcs."""
    try:
        from worlds.LauncherComponents import components
    except ImportError:
        return
    if not collection or not collection.linked_shortcuts:
        return
    
    primary_links = {}
    secondary_links = {}
    
    for linked in collection.linked_shortcuts:
        if linked.link_type == LinkType.PRIMARY:
            if linked.target_component not in primary_links:
                primary_links[linked.target_component] = linked
            else:
                print(f"[SHORTCUT-MANAGER] Warning: Multiple PRIMARY links for '{linked.target_component}'. "f"Using first. Assign {linked.name} as SECONDARY.")
        else:
            if linked.target_component not in secondary_links:
                secondary_links[linked.target_component] = []
            secondary_links[linked.target_component].append(linked)
    
    for component in components:
        if component.display_name in primary_links:
            linked_shortcut = primary_links[component.display_name]
            if not hasattr(component, 'primary_shortcut'):
                component.primary_shortcut = linked_shortcut
            original_func = component.func
            component.func = _wrap_component_func_with_shortcut(original_func, linked_shortcut, component)
        
        if component.display_name in secondary_links:
            if not hasattr(component, 'secondary_shortcuts'):
                component.secondary_shortcuts = []
            component.secondary_shortcuts.extend(secondary_links[component.display_name])


def _monkey_patch_launcher(collection: ShortcutCollection) -> None:
    """Patch Launcher.build_card to inject secondary shortcuts."""
    import sys, time
    global _exit_normally
    
    Launcher = None
    for _ in range(200):
        try:
            if 'kvui' not in sys.modules:
                time.sleep(0.1)
                continue
            from kivy.app import App
            app = App.get_running_app()
            if app and app.__class__.__name__ == 'Launcher':
                Launcher = app.__class__
                break
            elif app and app.__class__.__name__ != 'Launcher':
                print(f"[SHORTCUT-MANAGER] Found app, but it's not Launcher: {app.__class__.__name__} (attempt {_})")
                break
        except Exception:
            pass
        time.sleep(0.1)
    
    if not Launcher:
        # Confirmed this is not a launcher process, don't restart on exit
        _exit_normally = True
        print("[SHORTCUT-MANAGER] Launcher app not running. Likely not running Launcher.")
        return
    
    try:
        secondary_lookup = {}
        for linked in collection.linked_shortcuts:
            if linked.link_type == LinkType.SECONDARY:
                if linked.target_component not in secondary_lookup:
                    secondary_lookup[linked.target_component] = []
                secondary_lookup[linked.target_component].append(linked)
        
        if not secondary_lookup:
            # Launcher found and confirmed, even if no shortcuts to patch
            _exit_normally = True
            return
        
        if not hasattr(Launcher, '_original_build_card'):
            Launcher._original_build_card = Launcher.build_card
        
        original_build_card_method = Launcher._original_build_card
        
        def patched_build_card(self, component):
            card = original_build_card_method(self, component)
            if component.display_name in secondary_lookup:
                try:
                    from kivymd.uix.menu import MDDropdownMenu
                    existing_items = list(card.context_button.menu.items)
                    
                    for linked_shortcut in secondary_lookup[component.display_name]:
                        icon = _get_icon_for_shortcut_type(linked_shortcut.shortcut_type, bool(linked_shortcut.args))
                        existing_items.append({
                            "text": linked_shortcut.name,
                            "leading_icon": icon,
                            "on_release": lambda ls=linked_shortcut, comp=component: _execute_linked_shortcut(ls, comp)
                        })
                    
                    card.context_button.menu = MDDropdownMenu(caller=card.context_button, items=existing_items)
                except Exception as e:
                    print(f"[SHORTCUT-MANAGER] Failed to add shortcuts to {component.display_name}: {e}")
            return card
        
        Launcher.build_card = patched_build_card
        # Patch successful, launcher confirmed running
        _exit_normally = True
        print("[SHORTCUT-MANAGER] Patched Launcher.build_card")
    except Exception as e:
        print(f"[SHORTCUT-MANAGER] Monkey patch failed: {e}")


def _execute_linked_shortcut(linked_shortcut, component) -> None:
    """Execute a linked shortcut."""
    try:
        shortcut = Shortcut(
            name=linked_shortcut.name,
            shortcut_type=linked_shortcut.shortcut_type,
            target=linked_shortcut.target,
            description=linked_shortcut.description,
            icon=linked_shortcut.icon,
            args=linked_shortcut.args,
            working_dir=linked_shortcut.working_dir,
            component_type=component.type.name if hasattr(component.type, 'name') else str(component.type),
        )
        ShortcutExecutor.execute(shortcut)
    except Exception as e:
        print(f"[SHORTCUT-MANAGER] Error executing '{linked_shortcut.name}': {e}")


def initialize_shortcuts() -> None:
    """Load shortcuts and register them with launcher."""
    collection = _load_shortcuts()
    if collection:
        register_shortcuts_as_components(collection)
        patch_components_with_linked_shortcuts(collection)
        import threading
        thread = threading.Thread(target=_monkey_patch_launcher, args=(collection,), daemon=True)
        thread.start()
    
    # Restore shortcuts from backup if they exist (on startup)
    _restore_apworld_shortcuts_from_backup()
    # Patch install_apworld to preserve shortcuts on updates
    _patch_install_apworld()


def delete_shortcut_and_cleanup(shortcut) -> None:
    """Delete temp icon file for a shortcut (call from UI on deletion)."""
    if shortcut.temp_icon_path:
        try:
            icon_path = Path(shortcut.temp_icon_path)
            if icon_path.exists():
                icon_path.unlink()
                print(f"[SHORTCUT-MANAGER] Cleaned up: {icon_path}")
        except Exception as e:
            print(f"[SHORTCUT-MANAGER] Cleanup failed: {e}")


def _add_game_type_to_enum() -> bool:
    """Dynamically add Type.GAME to the Type enum."""
    try:
        from worlds.LauncherComponents import Type as TYpe
        import enum
        from enum import auto
        
        if hasattr(TYpe, 'GAME'):
            return True

        setattr(TYpe, 'GAME', auto())
        TYpe.GAME = TYpe(len(TYpe))
        print(f"[SHORTCUT-MANAGER] Added Type.GAME")
        return True
    except Exception as e:
        print(f"[SHORTCUT-MANAGER] Failed to add Type.GAME: {e}")
        import traceback
        traceback.print_exc()
        return False


def _generate_random_gamepad_icon() -> str:
    """Generate a random gamepad icon (usually gamepad-round, rarely with direction)."""
    import random
    
    if random.random() < 0.85:
        return "gamepad-round"
    
    directions = ["up", "down", "left", "right"]
    return f"gamepad-round-{random.choice(directions)}"


def _patch_launcher_for_game_button_wip() -> None:
    """[WIP] Inject GAME button into sidebar after Launcher is running. Currently disabled due to rendering issues."""
    import sys
    import time
    
    launcher_app = None
    for attempt in range(400):
        try:
            if 'kvui' not in sys.modules:
                time.sleep(0.05)
                continue
            
            from kivy.app import App
            app = App.get_running_app()
            if app and app.__class__.__name__ == 'Launcher':
                if app.root:
                    launcher_app = app
                    print(f"[SHORTCUT-MANAGER] Found Launcher app with root widget (attempt {attempt})")
                    break
            elif app and app.__class__.__name__ != 'Launcher':
                print(f"[SHORTCUT-MANAGER] Found app, but it's not Launcher: {app.__class__.__name__} (attempt {attempt})")
                break

        except Exception:
            pass
        time.sleep(0.05)
    
    if not launcher_app:
        print("[SHORTCUT-MANAGER] Launcher app not running or root widget not built")
        return
    
    def inject_game_button_on_main_thread(dt):
        """Create and inject GAME button on the main Kivy thread."""
        try:
            print(f"[SHORTCUT-MANAGER] App root: {launcher_app.root}")
            print(f"[SHORTCUT-MANAGER] App root class: {launcher_app.root.__class__.__name__}")
            
            navigation = None
            
            if launcher_app.root and hasattr(launcher_app.root, 'ids'):
                print(f"[SHORTCUT-MANAGER] Root has ids: {list(launcher_app.root.ids.keys()) if hasattr(launcher_app.root.ids, 'keys') else launcher_app.root.ids}")
                navigation = launcher_app.root.ids.get('navigation', None)
                print(f"[SHORTCUT-MANAGER] Got navigation from root.ids: {navigation}")
            
            if not navigation and hasattr(launcher_app, 'navigation') and launcher_app.navigation:
                navigation = launcher_app.navigation
                print(f"[SHORTCUT-MANAGER] Got navigation from app.navigation")
            
            if not navigation:
                print("[SHORTCUT-MANAGER] Could not find navigation grid")
                return
            
            from worlds.LauncherComponents import Type
            from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText
            
            print(f"[SHORTCUT-MANAGER] Navigation found: {navigation}")
            print(f"[SHORTCUT-MANAGER] Navigation has {len(navigation.children)} children")
            
            for i, child in enumerate(navigation.children):
                print(f"[SHORTCUT-MANAGER]   Child {i}: {child.__class__.__name__}")
            
            icon_name = _generate_random_gamepad_icon()
            print(f"[SHORTCUT-MANAGER] Generated icon: {icon_name}")
            
            game_button = MDButton(style="text")
            game_button.type = (Type.GAME,)
            game_button.bind(on_release=launcher_app.filter_clients_by_type)
            
            icon_widget = MDButtonIcon(icon=icon_name)
            text_widget = MDButtonText(text="Game")
            text_widget.theme_text_color = "Custom"
            text_widget.text_color = launcher_app.theme_cls.primaryColor
            game_button.add_widget(icon_widget)
            game_button.add_widget(text_widget)
            
            print(f"[SHORTCUT-MANAGER] Game button created with {len(game_button.children)} children")
            for j, child in enumerate(game_button.children):
                print(f"[SHORTCUT-MANAGER]     Button child {j}: {child.__class__.__name__}")
                if hasattr(child, 'text'):
                    print(f"[SHORTCUT-MANAGER]       Text: {child.text}, theme_text_color: {getattr(child, 'theme_text_color', 'N/A')}")
                if hasattr(child, 'icon'):
                    print(f"[SHORTCUT-MANAGER]       Icon: {child.icon}")
            for j, child in enumerate(game_button.children):
                print(f"[SHORTCUT-MANAGER]     Button child {j}: {child.__class__.__name__}")
                if hasattr(child, 'text'):
                    print(f"[SHORTCUT-MANAGER]       Text: {child.text}")
                if hasattr(child, 'icon'):
                    print(f"[SHORTCUT-MANAGER]       Icon: {child.icon}")
            
            favorites_index = None
            for i, child in enumerate(navigation.children):
                if hasattr(child, 'children'):
                    for subchild in child.children:
                        if hasattr(subchild, 'text') and 'Favorites' in getattr(subchild, 'text', ''):
                            favorites_index = i
                            print(f"[SHORTCUT-MANAGER] Found Favorites at index {i}")
                            break
            
            if favorites_index is not None:
                navigation.children.insert(favorites_index, game_button)
                print(f"[SHORTCUT-MANAGER] Injected GAME button at index {favorites_index} (before Favorites)")
            else:
                divider_found = False
                for i, child in enumerate(navigation.children):
                    if child.__class__.__name__ == 'MDNavigationDrawerDivider':
                        navigation.children.insert(i, game_button)
                        divider_found = True
                        print(f"[SHORTCUT-MANAGER] Injected GAME button at index {i} (before divider)")
                        break
                
                if not divider_found:
                    navigation.add_widget(game_button)
                    print("[SHORTCUT-MANAGER] Injected GAME button at end")
            
            navigation.do_layout()
            print(f"[SHORTCUT-MANAGER] Called do_layout() on navigation")
            print(f"[SHORTCUT-MANAGER] Navigation now has {len(navigation.children)} children:")
            for i, child in enumerate(navigation.children):
                print(f"[SHORTCUT-MANAGER]   Child {i}: {child.__class__.__name__}")
                if hasattr(child, 'children') and len(child.children) > 0:
                    for j, subchild in enumerate(child.children):
                        print(f"[SHORTCUT-MANAGER]     Subchild {j}: {subchild.__class__.__name__}")
                        if hasattr(subchild, 'text'):
                            print(f"[SHORTCUT-MANAGER]       text: {subchild.text}")
                        if hasattr(subchild, 'icon'):
                            print(f"[SHORTCUT-MANAGER]       icon: {subchild.icon}")
            
            launcher_app.current_filter = (Type.CLIENT, Type.TOOL, Type.ADJUSTER, Type.MISC, Type.GAME)
            print("[SHORTCUT-MANAGER] Updated current_filter to include Type.GAME")
            print("[SHORTCUT-MANAGER] GAME button injection successful!")
            
        except Exception as e:
            import traceback
            print(f"[SHORTCUT-MANAGER] Failed to inject GAME button: {e}")
            traceback.print_exc()
    
    try:
        from kivy.clock import Clock
        Clock.schedule_once(inject_game_button_on_main_thread, 0)
        print("[SHORTCUT-MANAGER] Scheduled GAME button injection on main thread")
    except Exception as e:
        print(f"[SHORTCUT-MANAGER] Failed to schedule injection: {e}")


def main(*args):
    """Main entry point for Shortcut Manager component."""
    from worlds.LauncherComponents import launch
    from .shortcut_ui import main_ui
    world_path = _find_shortcut_manager_world()
    launch(main_ui, name="Shortcut Manager", args=(world_path,))


def _is_launcher_process_from_args() -> bool:
    """Check if the first argument indicates this is running the launcher."""
    import sys
    from pathlib import Path
    
    if len(sys.argv) < 1:
        return False
    
    arg = sys.argv[0]
    
    # Check if the argument ends with Launcher.py or ArchipelagoLauncher.exe
    if not (arg.endswith("Launcher.py") or arg.endswith("ArchipelagoLauncher.exe")):
        return False
    
    # Verify the file actually exists
    try:
        path = Path(arg)
        if path.exists() and path.is_file():
            return True
    except Exception:
        pass
    
    return False


def _setup_launcher_restart_on_failure() -> None:
    """Setup atexit handler to restart launcher if it closes prematurely."""
    import atexit
    import subprocess
    import sys

    print(f"[SHORTCUT-MANAGER] Args are: {sys.argv}")
    is_launcher_arg = _is_launcher_process_from_args()
    print(f"[SHORTCUT-MANAGER] Launcher detected from args: {is_launcher_arg}")
    
    def restart_launcher_on_early_exit(is_launcher_arg=is_launcher_arg):
        """Restart launcher as a new process if it closed without being confirmed as running."""
        global _exit_normally
        if not _exit_normally and is_launcher_arg:
            print("[SHORTCUT-MANAGER] Launcher closed prematurely or failed before confirmation, restarting...")
            try:
                # Spawn completely fresh launcher process
                subprocess.Popen([sys.executable, "-m", "Launcher"], start_new_session=True)
            except Exception as e:
                print(f"[SHORTCUT-MANAGER] Failed to restart launcher: {e}")
    
    atexit.register(restart_launcher_on_early_exit)


try:
    _add_game_type_to_enum()
    initialize_shortcuts()
    _setup_launcher_restart_on_failure()
    print("[SHORTCUT-MANAGER] Initialized with auto-restart on failure.")
except Exception as e:
    print(f"[SHORTCUT-MANAGER] Init failed: {e}")
