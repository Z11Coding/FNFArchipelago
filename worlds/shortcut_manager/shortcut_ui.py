"""Launcher UI for Shortcut Manager - integrates with the Launcher GUI."""

import sys
from typing import List


class SteamLibraryError(Exception):
    """Custom exception for Steam library errors."""
    pass

from pathlib import Path
from typing import Optional, Callable, List
import sys
import platform

from .structures import Shortcut, LinkedShortcut, ShortcutType, LinkType, ShortcutCollection
from .shortcut_manager import ShortcutStorage


def _get_executable_filetypes() -> List[tuple]:
    """Get appropriate executable filetypes for current OS."""
    if sys.platform == "win32":
        return [
            ("Windows Executables", "*.exe *.bat *.cmd *.com"),
            ("PowerShell Scripts", "*.ps1"),
            ("All Files", "*.*")
        ]
    elif sys.platform == "darwin":
        return [
            ("Executable Files", "*"),
            ("Shell Scripts", "*.sh"),
            ("Applications", "*.app"),
            ("All Files", "*.*")
        ]
    else:
        return [
            ("Executable Files", "*"),
            ("Shell Scripts", "*.sh"),
            ("Perl Scripts", "*.pl"),
            ("Ruby Scripts", "*.rb"),
            ("JavaScript/Node", "*.js"),
            ("All Files", "*.*")
        ]


def _get_wine_executable_filetypes() -> List[tuple]:
    """Get Windows executable filetypes for Wine on Linux."""
    return [
        ("Windows Executables", "*.exe"),
        ("All Files", "*.*")
    ]


def _get_steam_games() -> List[str]:
    """Get list of games from Steam library."""
    try:
        try:
            import vdf
        except ImportError:
            print("[SHORTCUT-MANAGER] VDF library not found, Using internal.")
            from . import vdf as vdf
        from pathlib import Path
        import os
        import string
        
        steam_root = None
        library_paths = []
        
        if sys.platform == "win32":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                    steam_root = Path(winreg.QueryValueEx(key, "SteamPath")[0])
            except:
                for path in [
                    Path("C:/Program Files (x86)/Steam"),
                    Path("C:/Program Files/Steam"),
                ]:
                    if path.exists():
                        steam_root = path
                        break
                if not steam_root and "ProgramFiles(x86)" in os.environ:
                    path = Path(os.environ["ProgramFiles(x86)"]) / "Steam"
                    if path.exists():
                        steam_root = path
            
            if steam_root:
                library_paths.append(steam_root / "steamapps")
                
                try:
                    libraryfolders_path = steam_root / "libraryfolders.vdf"
                    if libraryfolders_path.exists():
                        with open(libraryfolders_path, 'r') as f:
                            data = vdf.load(f)
                            for key, library_data in data.get("LibraryFolders", {}).items():
                                if isinstance(library_data, dict):
                                    lib_path = library_data.get("path", "")
                                    if lib_path:
                                        library_paths.append(Path(lib_path) / "steamapps")
                except:
                    pass
                
                for drive in string.ascii_uppercase:
                    steam_lib_root = Path(f"{drive}:/SteamLibrary")
                    if steam_lib_root.exists():
                        steamapps_path = steam_lib_root / "steamapps"
                        if steamapps_path not in library_paths:
                            library_paths.append(steamapps_path)
                        try:
                            lib_vdf_path = steam_lib_root / "libraryfolder.vdf"
                            if lib_vdf_path.exists():
                                with open(lib_vdf_path, 'r') as f:
                                    data = vdf.load(f)
                                    for key, library_data in data.get("LibraryFolders", {}).items():
                                        if isinstance(library_data, dict):
                                            lib_path = library_data.get("path", "")
                                            if lib_path:
                                                additional_path = Path(lib_path) / "steamapps"
                                                if additional_path not in library_paths:
                                                    library_paths.append(additional_path)
                        except:
                            pass
        
        elif sys.platform == "darwin":
            steam_root = Path.home() / "Library" / "Application Support" / "Steam"
            if steam_root.exists():
                library_paths.append(steam_root / "steamapps")
                try:
                    libraryfolders_path = steam_root / "libraryfolders.vdf"
                    if libraryfolders_path.exists():
                        with open(libraryfolders_path, 'r') as f:
                            data = vdf.load(f)
                            for key, library_data in data.get("LibraryFolders", {}).items():
                                if isinstance(library_data, dict):
                                    lib_path = library_data.get("path", "")
                                    if lib_path:
                                        library_paths.append(Path(lib_path) / "steamapps")
                except:
                    pass
        
        else:
            steam_root = Path.home() / ".steam" / "root"
            if not steam_root.exists():
                steam_root = Path.home() / ".local" / "share" / "Steam"
            
            if steam_root.exists():
                library_paths.append(steam_root / "steamapps")
                try:
                    libraryfolders_path = steam_root / "libraryfolders.vdf"
                    if libraryfolders_path.exists():
                        with open(libraryfolders_path, 'r') as f:
                            data = vdf.load(f)
                            for key, library_data in data.get("LibraryFolders", {}).items():
                                if isinstance(library_data, dict):
                                    lib_path = library_data.get("path", "")
                                    if lib_path:
                                        library_paths.append(Path(lib_path) / "steamapps")
                except:
                    pass
        
        if not library_paths:
            raise SteamLibraryError("Steam installation not found")
        
        games = []
        for lib_apps in library_paths:
            if not lib_apps.exists():
                continue
            
            for app_manifest in lib_apps.glob("appmanifest_*.acf"):
                try:
                    with open(app_manifest, 'r') as mf:
                        app_data = vdf.load(mf)
                        app_state = app_data.get("AppState", {})
                        game_name = app_state.get("name", "Unknown")
                        app_id = app_manifest.stem.replace("appmanifest_", "")
                        games.append(f"{game_name} ({app_id})")
                except:
                    continue
        
        if not games:
            raise SteamLibraryError("No games found in Steam library")
        
        return sorted(list(set(games)))
    except SteamLibraryError:
        raise
    except ImportError as e:
        print(f"[SHORTCUT-MANAGER] VDF library not available, cannot read Steam library: {e}")
        import traceback
        traceback.print_exc()
        raise SteamLibraryError(f"Steam Integration failed - {str(e)}")
    except Exception as e:
        print(f"[SHORTCUT-MANAGER] Error reading Steam library: {e}")
        import traceback
        traceback.print_exc()
        raise SteamLibraryError(f"Error reading Steam library: {str(e)}")


try:
    from kvui import ScrollBox, dp, MDBoxLayout, MDButton, MDButtonText, MDLabel, MDTextField, Widget, ThemedApp
    from kivymd.uix.dialog import MDDialog, MDDialogHeadlineText, MDDialogSupportingText, MDDialogButtonContainer, MDDialogContentContainer
    from kivymd.uix.menu import MDDropdownMenu
    from kivymd.uix.scrollview import MDScrollView
    from kivy.properties import ObjectProperty
    from kivy.core.window import Window
    KIVY_AVAILABLE = True
except ImportError:
    KIVY_AVAILABLE = False
    print("[SHORTCUT-MANAGER] Kivy/KivyMD unavailable.")
    import traceback
    traceback.print_exc()


if KIVY_AVAILABLE:
    class SteamGameSelectionDialog(MDDialog):
        """Dialog for selecting a Steam game from a dropdown menu."""
        
        def __init__(self, games: List[str], callback: Callable[[Optional[str]], None], on_cancel_callback: Callable[[], None] = None, **kwargs):
            """Initialize dialog with game selection dropdown.
            Args:
                games: List of "GameName (AppID)" strings
                callback: Called with selected game string when confirmed
                on_cancel_callback: Called when dialog is cancelled to restore parent
            """
            self.games = games
            self.callback = callback
            self.on_cancel_callback = on_cancel_callback
            self.selected_game = None
            
            menu_items = [
                {
                    "text": game,
                    "on_release": lambda game=game: self._on_game_selected(game),
                }
                for game in games
            ]
            
            self.dropdown_menu = MDDropdownMenu(
                items=menu_items,
                width_mult=4,
            )
            
            self.game_button = MDButton(
                MDButtonText(text="Select a game..."),
                style="outlined",
                on_release=self._open_dropdown,
            )
            self.dropdown_menu.caller = self.game_button
            
            def on_confirm(*args):
                if self.selected_game:
                    self.dismiss()
                    self.callback(self.selected_game)
            
            def on_cancel(*args):
                self.dismiss()
                if self.on_cancel_callback:
                    self.on_cancel_callback()
            
            content = MDDialogContentContainer(
                self.game_button,
                orientation="vertical",
                padding=dp(16),
                spacing=dp(16),
                size_hint_y=None,
                height=dp(60),
            )
            
            button_container = MDDialogButtonContainer(
                MDButton(MDButtonText(text="Confirm"), on_release=on_confirm, style="text"),
                MDButton(MDButtonText(text="Cancel"), on_release=on_cancel, style="text"),
                spacing="8dp",
            )
            
            super().__init__(
                MDDialogHeadlineText(text="Select Steam Game"),
                content,
                button_container,
                size_hint_y=0.5,
                size_hint_x=0.8,
                auto_dismiss=False,
            )
        
        def _on_game_selected(self, game: str):
            """Handle game selection from dropdown."""
            self.selected_game = game
            self.game_button.children[0].text = game
            self.dropdown_menu.dismiss()
        
        def _open_dropdown(self, *args):
            """Open the dropdown menu when button is clicked."""
            self.dropdown_menu.open()


    class ShortcutCreateDialog(MDDialog):
        """Create shortcut dialog."""
        
        def __init__(self, callback: Callable[[Optional[Shortcut]], None], pre_filled_shortcut: Optional[Shortcut] = None, **kwargs):
            """Initialize dialog."""
            self.callback = callback
            self.pre_filled_shortcut = pre_filled_shortcut
        
            self.selected_type = pre_filled_shortcut.shortcut_type if pre_filled_shortcut else ShortcutType.SCRIPT
            self.selected_component_type = pre_filled_shortcut.component_type if pre_filled_shortcut else "MISC"
            self.selected_icon = pre_filled_shortcut.icon if pre_filled_shortcut else "icon"
            
            self.name_field = MDTextField(hint_text="Name", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            self.target_field = MDTextField(hint_text="Target", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            self.description_field = MDTextField(hint_text="Description", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            self.args_field = MDTextField(hint_text="Arguments", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            
            if pre_filled_shortcut:
                self.name_field.text = pre_filled_shortcut.name
                self.target_field.text = pre_filled_shortcut.target
                self.description_field.text = pre_filled_shortcut.description or ""
                self.args_field.text = pre_filled_shortcut.args or ""
            
            type_menu_items = [
                {"text": st.value, "on_release": lambda x=st.value: self._set_type(x)}
                for st in ShortcutType
                if not (st == ShortcutType.WINE and sys.platform == "win32")
            ]
            self.type_dropdown = MDDropdownMenu(items=type_menu_items, width=dp(200))
            type_text = pre_filled_shortcut.shortcut_type.value if pre_filled_shortcut else "script"
            self.type_btn = MDButton(MDButtonText(text=type_text), size_hint_x=0.5, size_hint_y=None, height=dp(40))
            self.type_btn.bind(on_release=self._show_type_menu)
            
            comp_menu_items = [
                {"text": c, "on_release": lambda x=c: self._set_component_type(x)}
                for c in ["TOOL", "MISC", "CLIENT", "ADJUSTER", "HIDDEN"]
            ]
            self.comp_dropdown = MDDropdownMenu(items=comp_menu_items, width=dp(200))
            comp_text = pre_filled_shortcut.component_type if pre_filled_shortcut else "MISC"
            self.comp_btn = MDButton(MDButtonText(text=comp_text), size_hint_x=0.5, size_hint_y=None, height=dp(40))
            self.comp_btn.bind(on_release=self._show_comp_menu)
            
            icon_names = self._get_available_icons()
            icon_menu_items = [
                {"text": icon, "on_release": lambda x=icon: self._set_icon(x)}
                for icon in icon_names
            ]
            self.icon_dropdown = MDDropdownMenu(items=icon_menu_items, width=dp(250))
            icon_text = pre_filled_shortcut.icon if pre_filled_shortcut else "icon"
            self.icon_btn = MDButton(MDButtonText(text=icon_text), size_hint_x=0.4, size_hint_y=None, height=dp(40))
            self.icon_btn.bind(on_release=self._show_icon_menu)
            
            browse_icon_btn = MDButton(MDButtonText(text="Browse..."), size_hint_x=None, width=dp(90), size_hint_y=None, height=dp(40))
            browse_icon_btn.bind(on_release=self._on_browse_icon)
            
            browse_btn = MDButton(MDButtonText(text="Browse"), size_hint_x=None, width=dp(100), size_hint_y=None, height=dp(40))
            browse_btn.bind(on_release=self._on_browse)
            
            content = MDDialogContentContainer(orientation="vertical", spacing=dp(12), padding=dp(16))
            
            name_label = MDLabel(text="Name:", size_hint_y=None, height=dp(20))
            content.add_widget(name_label)
            content.add_widget(self.name_field)
            
            type_comp_row = MDBoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(40))
            type_label = MDLabel(text="Type:", size_hint_x=0.2, size_hint_y=None, height=dp(40))
            type_comp_row.add_widget(type_label)
            type_comp_row.add_widget(self.type_btn)
            comp_label = MDLabel(text="Component:", size_hint_x=0.25, size_hint_y=None, height=dp(40))
            type_comp_row.add_widget(comp_label)
            type_comp_row.add_widget(self.comp_btn)
            content.add_widget(type_comp_row)
            
            icon_label = MDLabel(text="Icon:", size_hint_y=None, height=dp(20))
            content.add_widget(icon_label)
            icon_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(40))
            icon_row.add_widget(self.icon_btn)
            icon_row.add_widget(browse_icon_btn)
            content.add_widget(icon_row)
            
            target_label = MDLabel(text="Target:", size_hint_y=None, height=dp(20))
            content.add_widget(target_label)
            target_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(56))
            target_row.add_widget(self.target_field)
            target_row.add_widget(browse_btn)
            content.add_widget(target_row)
            
            desc_args_label_row = MDBoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(20))
            desc_label = MDLabel(text="Description:", size_hint_x=0.5)
            desc_args_label_row.add_widget(desc_label)
            args_label = MDLabel(text="Arguments:")
            desc_args_label_row.add_widget(args_label)
            content.add_widget(desc_args_label_row)
            
            desc_args_row = MDBoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(56))
            desc_args_row.add_widget(self.description_field)
            desc_args_row.add_widget(self.args_field)
            content.add_widget(desc_args_row)
            
            buttons = MDDialogButtonContainer(
                MDButton(MDButtonText(text="Create"), on_release=lambda *args: self._create_shortcut(), style="filled"),
                MDButton(MDButtonText(text="Cancel"), on_release=lambda *args: self.dismiss(), style="text"),
                spacing="8dp"
            )
            
            super().__init__(
                MDDialogHeadlineText(text="Create Shortcut"),
                content,
                buttons,
                auto_dismiss=False,
                **kwargs
            )
        
        def _get_available_icons(self) -> List[str]:
            """Get list of available icon names."""
            try:
                from worlds.LauncherComponents import icon_paths
                return sorted(icon_paths.keys())
            except ImportError:
                return ["icon", "discord"]
        
        def _show_type_menu(self, *args):
            """Show type dropdown."""
            self.type_dropdown.caller = self.type_btn
            self.type_dropdown.open()
        
        def _show_comp_menu(self, *args):
            """Show component dropdown."""
            self.comp_dropdown.caller = self.comp_btn
            self.comp_dropdown.open()
        
        def _show_icon_menu(self, *args):
            """Show icon dropdown."""
            self.icon_dropdown.caller = self.icon_btn
            self.icon_dropdown.open()
        
        def _set_type(self, type_name: str):
            """Set shortcut type."""
            self.selected_type = ShortcutType[type_name.upper()]
            self.type_btn.children[0].text = type_name
            self.type_dropdown.dismiss()
            self._update_target_hint()
        
        def _set_component_type(self, comp_name: str):
            """Set component type."""
            self.selected_component_type = comp_name
            self.comp_btn.children[0].text = comp_name
            self.comp_dropdown.dismiss()
        
        def _set_icon(self, icon_name: str):
            """Set icon."""
            self.selected_icon = icon_name
            display_name = icon_name
            if len(display_name) > 25:
                display_name = display_name.split("\\")[-1] if "\\" in display_name else display_name.split("/")[-1]
            if len(display_name) > 25:
                display_name = display_name[:22] + "..."
            self.icon_btn.children[0].text = display_name
            self.icon_dropdown.dismiss()
        
        def _update_target_hint(self):
            """Update target hint based on type."""
            hints = {
                ShortcutType.SCRIPT: "Path to Python script",
                ShortcutType.EXECUTABLE: "Path to executable",
                ShortcutType.FOLDER: "Path to folder",
                ShortcutType.URL: "URL (http://...)",
                ShortcutType.FUNCTION: "module.function_name",
                ShortcutType.WINE: "Path to Windows executable (.exe)",
                ShortcutType.STEAM: "Steam game (auto-populated from library)",
            }
            self.target_field.hint_text = hints.get(self.selected_type, "Target")
        
        def _on_browse_icon(self, *args):
            """Open file browser for icon."""
            import tkinter as tk
            from tkinter import filedialog
            
            root = tk.Tk()
            root.withdraw()
            
            try:
                path = filedialog.askopenfilename(
                    title="Select Icon Image",
                    filetypes=[("Image Files", "*.png *.jpg *.jpeg *.gif"), ("All Files", "*.*")]
                )
                
                if path:
                    self.selected_icon = path
                    filename = path.split("\\")[-1] if "\\" in path else path.split("/")[-1]
                    display_name = filename if len(filename) <= 25 else filename[:22] + "..."
                    self.icon_btn.children[0].text = display_name
            finally:
                root.destroy()
        
        def _on_browse(self, *args):
            """Open file browser."""
            import tkinter as tk
            from tkinter import filedialog
            
            if self.selected_type == ShortcutType.STEAM:
                self._show_steam_selection()
                return
            
            root = tk.Tk()
            root.withdraw()
            
            try:
                if self.selected_type == ShortcutType.FOLDER:
                    path = filedialog.askdirectory(title="Select Folder")
                elif self.selected_type == ShortcutType.SCRIPT:
                    path = filedialog.askopenfilename(
                        title="Select Python Script",
                        filetypes=[("Python Files", "*.py *.pyw *.pyc"), ("All Files", "*.*")]
                    )
                elif self.selected_type == ShortcutType.EXECUTABLE:
                    path = filedialog.askopenfilename(
                        title="Select Executable",
                        filetypes=_get_executable_filetypes()
                    )
                elif self.selected_type == ShortcutType.WINE:
                    path = filedialog.askopenfilename(
                        title="Select Windows Executable for Wine",
                        filetypes=_get_wine_executable_filetypes()
                    )
                else:
                    path = None
                
                if path:
                    self.target_field.text = path
            finally:
                root.destroy()
        
        def _show_steam_selection(self):
            """Show Steam game selection dialog."""
            try:
                games = _get_steam_games()
                current_state = self._get_current_shortcut()
                
                def on_game_selected(selected_game):
                    if current_state:
                        current_state.target = selected_game
                    dialog = ShortcutCreateDialog(self.callback, pre_filled_shortcut=current_state if current_state else Shortcut(
                        name="", shortcut_type=self.selected_type, target=selected_game, 
                        description="", icon="icon", args="", component_type="MISC"
                    ))
                    dialog.open()
                
                def reopen_dialog():
                    dialog = ShortcutCreateDialog(self.callback, pre_filled_shortcut=current_state)
                    dialog.open()
                
                dialog = SteamGameSelectionDialog(games, on_game_selected, on_cancel_callback=reopen_dialog)
                self.dismiss()
                dialog.open()
            except SteamLibraryError as e:
                from tkinter import messagebox
                import tkinter as tk
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("Steam Library", str(e))
                root.destroy()
        
        def _get_current_shortcut(self) -> Optional[Shortcut]:
            """Get the current shortcut being edited (for state restoration)."""
            if not self.name_field.text.strip():
                return None
            return Shortcut(
                name=self.name_field.text.strip(),
                shortcut_type=self.selected_type,
                target=self.target_field.text.strip(),
                description=self.description_field.text.strip(),
                icon=self.selected_icon,
                args=self.args_field.text.strip(),
                component_type=self.selected_component_type,
            )
        
        def _create_shortcut(self):
            """Create shortcut."""
            if not self.name_field.text.strip() or not self.target_field.text.strip():
                return
            
            try:
                shortcut = Shortcut(
                    name=self.name_field.text.strip(),
                    shortcut_type=self.selected_type,
                    target=self.target_field.text.strip(),
                    description=self.description_field.text.strip(),
                    icon=self.selected_icon,
                    args=self.args_field.text.strip(),
                    component_type=self.selected_component_type,
                )
                self.callback(shortcut)
                self.dismiss()
            except Exception as e:
                print(f"Error creating shortcut: {e}")


    class ShortcutEditDialog(MDDialog):
        """Edit shortcut dialog."""
        
        def __init__(self, shortcut: Shortcut, callback: Callable[[Optional[Shortcut]], None], **kwargs):
            """Initialize with shortcut values."""
            self.callback = callback
            self.original_shortcut = shortcut
            
            self.selected_type = shortcut.shortcut_type
            self.selected_component_type = shortcut.component_type
            self.selected_icon = shortcut.icon
            
            self.name_field = MDTextField(text=shortcut.name, hint_text="Name", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            self.target_field = MDTextField(text=shortcut.target, hint_text="Target", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            self.description_field = MDTextField(text=shortcut.description, hint_text="Description", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            self.args_field = MDTextField(text=shortcut.args, hint_text="Arguments", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            
            type_menu_items = [
                {"text": st.value, "on_release": lambda x=st.value: self._set_type(x)}
                for st in ShortcutType
                if not (st == ShortcutType.WINE and sys.platform == "win32")
            ]
            self.type_dropdown = MDDropdownMenu(items=type_menu_items, width=dp(200))
            self.type_btn = MDButton(MDButtonText(text=shortcut.shortcut_type.value), size_hint_x=0.5, size_hint_y=None, height=dp(40))
            self.type_btn.bind(on_release=self._show_type_menu)
            
            comp_menu_items = [
                {"text": c, "on_release": lambda x=c: self._set_component_type(x)}
                for c in ["TOOL", "MISC", "CLIENT", "ADJUSTER", "GAME"]
            ]
            self.comp_dropdown = MDDropdownMenu(items=comp_menu_items, width=dp(200))
            self.comp_btn = MDButton(MDButtonText(text=shortcut.component_type), size_hint_x=0.5, size_hint_y=None, height=dp(40))
            self.comp_btn.bind(on_release=self._show_comp_menu)
            
            icon_names = self._get_available_icons()
            icon_menu_items = [
                {"text": icon, "on_release": lambda x=icon: self._set_icon(x)}
                for icon in icon_names
            ]
            self.icon_dropdown = MDDropdownMenu(items=icon_menu_items, width=dp(250))
            icon_display = shortcut.icon
            if len(icon_display) > 25:
                icon_display = icon_display.split("\\")[-1] if "\\" in icon_display else icon_display.split("/")[-1]
            if len(icon_display) > 25:
                icon_display = icon_display[:22] + "..."
            self.icon_btn = MDButton(MDButtonText(text=icon_display), size_hint_x=0.4, size_hint_y=None, height=dp(40))
            self.icon_btn.bind(on_release=self._show_icon_menu)
            
            browse_icon_btn = MDButton(MDButtonText(text="Browse..."), size_hint_x=None, width=dp(90), size_hint_y=None, height=dp(40))
            browse_icon_btn.bind(on_release=self._on_browse_icon)
            
            browse_btn = MDButton(MDButtonText(text="Browse"), size_hint_x=None, width=dp(100), size_hint_y=None, height=dp(40))
            browse_btn.bind(on_release=self._on_browse)
            
            content = MDDialogContentContainer(orientation="vertical", spacing=dp(12), padding=dp(16))
            
            name_label = MDLabel(text="Name:", size_hint_y=None, height=dp(20))
            content.add_widget(name_label)
            content.add_widget(self.name_field)
            
            type_comp_row = MDBoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(40))
            type_label = MDLabel(text="Type:", size_hint_x=0.2, size_hint_y=None, height=dp(40))
            type_comp_row.add_widget(type_label)
            type_comp_row.add_widget(self.type_btn)
            comp_label = MDLabel(text="Component:", size_hint_x=0.25, size_hint_y=None, height=dp(40))
            type_comp_row.add_widget(comp_label)
            type_comp_row.add_widget(self.comp_btn)
            content.add_widget(type_comp_row)
            
            icon_label = MDLabel(text="Icon:", size_hint_y=None, height=dp(20))
            content.add_widget(icon_label)
            icon_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(40))
            icon_row.add_widget(self.icon_btn)
            icon_row.add_widget(browse_icon_btn)
            content.add_widget(icon_row)
            
            target_label = MDLabel(text="Target:", size_hint_y=None, height=dp(20))
            content.add_widget(target_label)
            target_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(56))
            target_row.add_widget(self.target_field)
            target_row.add_widget(browse_btn)
            content.add_widget(target_row)
            
            desc_args_label_row = MDBoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(20))
            desc_label = MDLabel(text="Description:", size_hint_x=0.5)
            desc_args_label_row.add_widget(desc_label)
            args_label = MDLabel(text="Arguments:")
            desc_args_label_row.add_widget(args_label)
            content.add_widget(desc_args_label_row)
            
            desc_args_row = MDBoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(56))
            desc_args_row.add_widget(self.description_field)
            desc_args_row.add_widget(self.args_field)
            content.add_widget(desc_args_row)
            
            buttons = MDDialogButtonContainer(
                MDButton(MDButtonText(text="Save"), on_release=lambda *args: self._save_shortcut(), style="filled"),
                MDButton(MDButtonText(text="Cancel"), on_release=lambda *args: self.dismiss(), style="text"),
                spacing="8dp"
            )
            
            super().__init__(
                MDDialogHeadlineText(text="Edit Shortcut"),
                content,
                buttons,
                auto_dismiss=False,
                **kwargs
            )
        
        def _get_available_icons(self) -> List[str]:
            """Get list of available icon names."""
            try:
                from worlds.LauncherComponents import icon_paths
                return sorted(icon_paths.keys())
            except ImportError:
                return ["icon", "discord"]
        
        def _show_type_menu(self, *args):
            """Show type dropdown."""
            self.type_dropdown.caller = self.type_btn
            self.type_dropdown.open()
        
        def _show_comp_menu(self, *args):
            """Show component dropdown."""
            self.comp_dropdown.caller = self.comp_btn
            self.comp_dropdown.open()
        
        def _show_icon_menu(self, *args):
            """Show icon dropdown."""
            self.icon_dropdown.caller = self.icon_btn
            self.icon_dropdown.open()
        
        def _set_type(self, type_name: str):
            """Set shortcut type."""
            self.selected_type = ShortcutType[type_name.upper()]
            self.type_btn.children[0].text = type_name
            self.type_dropdown.dismiss()
            self._update_target_hint()
        
        def _set_component_type(self, comp_name: str):
            """Set component type."""
            self.selected_component_type = comp_name
            self.comp_btn.children[0].text = comp_name
            self.comp_dropdown.dismiss()
        
        def _set_icon(self, icon_name: str):
            """Set icon."""
            self.selected_icon = icon_name
            display_name = icon_name
            if len(display_name) > 25:
                display_name = display_name.split("\\")[-1] if "\\" in display_name else display_name.split("/")[-1]
            if len(display_name) > 25:
                display_name = display_name[:22] + "..."
            self.icon_btn.children[0].text = display_name
            self.icon_dropdown.dismiss()
        
        def _update_target_hint(self):
            """Update target hint based on type."""
            hints = {
                ShortcutType.SCRIPT: "Path to Python script",
                ShortcutType.EXECUTABLE: "Path to executable",
                ShortcutType.FOLDER: "Path to folder",
                ShortcutType.URL: "URL (http://...)",
                ShortcutType.FUNCTION: "module.function_name",
                ShortcutType.WINE: "Path to Windows executable (.exe)",
                ShortcutType.STEAM: "Steam game (auto-populated from library)",
            }
            self.target_field.hint_text = hints.get(self.selected_type, "Target")
        
        def _on_browse_icon(self, *args):
            """Open file browser for icon."""
            import tkinter as tk
            from tkinter import filedialog
            
            root = tk.Tk()
            root.withdraw()
            
            try:
                path = filedialog.askopenfilename(
                    title="Select Icon Image",
                    filetypes=[("Image Files", "*.png *.jpg *.jpeg *.gif"), ("All Files", "*.*")]
                )
                
                if path:
                    self.selected_icon = path
                    filename = path.split("\\")[-1] if "\\" in path else path.split("/")[-1]
                    display_name = filename if len(filename) <= 25 else filename[:22] + "..."
                    self.icon_btn.children[0].text = display_name
            finally:
                root.destroy()
        
        def _on_browse(self, *args):
            """Open file browser."""
            import tkinter as tk
            from tkinter import filedialog
            
            if self.selected_type == ShortcutType.STEAM:
                self._show_steam_selection()
                return
            
            root = tk.Tk()
            root.withdraw()
            
            try:
                if self.selected_type == ShortcutType.FOLDER:
                    path = filedialog.askdirectory(title="Select Folder")
                elif self.selected_type == ShortcutType.SCRIPT:
                    path = filedialog.askopenfilename(
                        title="Select Python Script",
                        filetypes=[("Python Files", "*.py"), ("All Files", "*.*")]
                    )
                elif self.selected_type == ShortcutType.EXECUTABLE:
                    path = filedialog.askopenfilename(
                        title="Select Executable",
                        filetypes=_get_executable_filetypes()
                    )
                elif self.selected_type == ShortcutType.WINE:
                    path = filedialog.askopenfilename(
                        title="Select Windows Executable for Wine",
                        filetypes=_get_wine_executable_filetypes()
                    )
                else:
                    path = None
                
                if path:
                    self.target_field.text = path
            finally:
                root.destroy()
        
        def _show_steam_selection(self):
            """Show Steam game selection dialog."""
            try:
                games = _get_steam_games()
                current_state = Shortcut(
                    name=self.name_field.text.strip(),
                    shortcut_type=self.selected_type,
                    target=self.target_field.text.strip(),
                    description=self.description_field.text.strip(),
                    icon=self.selected_icon,
                    args=self.args_field.text.strip(),
                    component_type=self.selected_component_type,
                )
                
                def on_game_selected(selected_game):
                    current_state.target = selected_game
                    dialog = ShortcutEditDialog(self.callback, current_state)
                    dialog.open()
                
                def reopen_dialog():
                    dialog = ShortcutEditDialog(self.callback, current_state)
                    dialog.open()
                
                dialog = SteamGameSelectionDialog(games, on_game_selected, on_cancel_callback=reopen_dialog)
                self.dismiss()
                dialog.open()
            except SteamLibraryError as e:
                from tkinter import messagebox
                import tkinter as tk
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("Steam Library", str(e))
                root.destroy()
        
        def _save_shortcut(self):
            """Save changes to shortcut."""
            if not self.name_field.text.strip() or not self.target_field.text.strip():
                return
            
            try:
                shortcut = Shortcut(
                    name=self.name_field.text.strip(),
                    shortcut_type=self.selected_type,
                    target=self.target_field.text.strip(),
                    description=self.description_field.text.strip(),
                    icon=self.selected_icon,
                    args=self.args_field.text.strip(),
                    working_dir=self.original_shortcut.working_dir,
                    component_type=self.selected_component_type,
                    metadata=self.original_shortcut.metadata,
                )
                self.callback(shortcut)
                self.dismiss()
            except Exception as e:
                print(f"Error saving shortcut: {e}")


    class LinkedShortcutCreateDialog(MDDialog):
        """Create linked shortcut dialog."""
        
        def __init__(self, callback: Callable[[Optional[LinkedShortcut]], None], pre_filled_linked: Optional[LinkedShortcut] = None, **kwargs):
            """Initialize dialog."""
            self.callback = callback
            self.pre_filled_linked = pre_filled_linked
            
            self.selected_type = pre_filled_linked.shortcut_type if pre_filled_linked else ShortcutType.SCRIPT
            self.selected_link_type = pre_filled_linked.link_type if pre_filled_linked else LinkType.PRIMARY
            
            self.component_names = self._get_available_components()
            self.selected_component = pre_filled_linked.target_component if pre_filled_linked else (self.component_names[0] if self.component_names else "")
            
            self.name_field = MDTextField(hint_text="Name", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            self.target_field = MDTextField(hint_text="Target", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            self.description_field = MDTextField(hint_text="Description", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            
            if pre_filled_linked:
                self.name_field.text = pre_filled_linked.name
                self.target_field.text = pre_filled_linked.target
                self.description_field.text = pre_filled_linked.description or ""
            
            type_menu_items = [
                {"text": st.value, "on_release": lambda x=st.value: self._set_type(x)}
                for st in ShortcutType
                if not (st == ShortcutType.WINE and sys.platform == "win32")
            ]
            self.type_dropdown = MDDropdownMenu(items=type_menu_items, width=dp(200))
            type_text = pre_filled_linked.shortcut_type.value if pre_filled_linked else "script"
            self.type_btn = MDButton(MDButtonText(text=type_text), size_hint_x=0.33, size_hint_y=None, height=dp(40))
            self.type_btn.bind(on_release=self._show_type_menu)
            
            link_menu_items = [
                {"text": lt.value, "on_release": lambda x=lt.value: self._set_link_type(x)}
                for lt in LinkType
            ]
            self.link_dropdown = MDDropdownMenu(items=link_menu_items, width=dp(200))
            link_text = pre_filled_linked.link_type.value if pre_filled_linked else "primary"
            self.link_btn = MDButton(MDButtonText(text=link_text), size_hint_x=0.33, size_hint_y=None, height=dp(40))
            self.link_btn.bind(on_release=self._show_link_menu)
            
            comp_menu_items = [
                {"text": c, "on_release": lambda x=c: self._set_component(x)}
                for c in self.component_names
            ]
            self.comp_dropdown = MDDropdownMenu(items=comp_menu_items, width=dp(280))
            comp_text = self.component_names[0] if self.component_names else "No components"
            self.comp_btn = MDButton(MDButtonText(text=comp_text), size_hint_x=0.5, size_hint_y=None, height=dp(40))
            self.comp_btn.bind(on_release=self._show_comp_menu)
            
            browse_btn = MDButton(MDButtonText(text="Browse"), size_hint_x=None, width=dp(100), size_hint_y=None, height=dp(40))
            browse_btn.bind(on_release=self._on_browse)
            
            content = MDDialogContentContainer(orientation="vertical", spacing=dp(12), padding=dp(16))
            
            name_label = MDLabel(text="Name:", size_hint_y=None, height=dp(20))
            content.add_widget(name_label)
            content.add_widget(self.name_field)
            
            type_link_comp_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(40))
            type_label = MDLabel(text="Type:", size_hint_x=None, width=dp(40), size_hint_y=None, height=dp(40))
            type_link_comp_row.add_widget(type_label)
            type_link_comp_row.add_widget(Widget())
            type_link_comp_row.add_widget(self.type_btn)
            link_label = MDLabel(text="Link:", size_hint_x=None, width=dp(35), size_hint_y=None, height=dp(40))
            type_link_comp_row.add_widget(link_label)
            type_link_comp_row.add_widget(Widget())
            type_link_comp_row.add_widget(self.link_btn)
            type_link_comp_row.add_widget(Widget())
            content.add_widget(type_link_comp_row)
            
            comp_label = MDLabel(text="Link to component:", size_hint_y=None, height=dp(20))
            content.add_widget(comp_label)
            content.add_widget(self.comp_btn)
            
            target_label = MDLabel(text="Target:", size_hint_y=None, height=dp(20))
            content.add_widget(target_label)
            target_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(56))
            target_row.add_widget(self.target_field)
            target_row.add_widget(browse_btn)
            content.add_widget(target_row)
            
            desc_label = MDLabel(text="Description:", size_hint_y=None, height=dp(20))
            content.add_widget(desc_label)
            content.add_widget(self.description_field)
            
            buttons = MDDialogButtonContainer(
                MDButton(MDButtonText(text="Create"), on_release=lambda *args: self._create_link(), style="filled"),
                MDButton(MDButtonText(text="Cancel"), on_release=lambda *args: self.dismiss(), style="text"),
                spacing="8dp"
            )
            
            super().__init__(
                MDDialogHeadlineText(text="Create Linked Shortcut"),
                content,
                buttons,
                auto_dismiss=False,
                **kwargs
            )
        
        def _get_available_components(self) -> List[str]:
            """Get list of available launcher components."""
            try:
                from worlds.LauncherComponents import components, Type
                return [c.display_name for c in components if c.type != Type.HIDDEN]
            except ImportError:
                return ["(No components available????)"]
        
        def _show_type_menu(self, *args):
            """Show type dropdown."""
            self.type_dropdown.caller = self.type_btn
            self.type_dropdown.open()
        
        def _show_link_menu(self, *args):
            """Show link type dropdown."""
            self.link_dropdown.caller = self.link_btn
            self.link_dropdown.open()
        
        def _show_comp_menu(self, *args):
            """Show component dropdown."""
            self.comp_dropdown.caller = self.comp_btn
            self.comp_dropdown.open()
        
        def _set_type(self, type_name: str):
            """Set shortcut type."""
            self.selected_type = ShortcutType[type_name.upper()]
            self.type_btn.children[0].text = type_name
            self.type_dropdown.dismiss()
            self._update_target_hint()
        
        def _set_link_type(self, link_name: str):
            """Set link type."""
            self.selected_link_type = LinkType[link_name.upper()]
            self.link_btn.children[0].text = link_name
            self.link_dropdown.dismiss()
        
        def _set_component(self, comp_name: str):
            """Set target component."""
            self.selected_component = comp_name
            self.comp_btn.children[0].text = comp_name
            self.comp_dropdown.dismiss()
        
        def _update_target_hint(self):
            """Update target hint based on type."""
            hints = {
                ShortcutType.SCRIPT: "Path to Python script",
                ShortcutType.EXECUTABLE: "Path to executable",
                ShortcutType.FOLDER: "Path to folder",
                ShortcutType.URL: "URL (http://...)",
                ShortcutType.FUNCTION: "module.function_name",
                ShortcutType.WINE: "Path to Windows executable (.exe)",
                ShortcutType.STEAM: "Steam game (auto-populated from library)",
            }
            self.target_field.hint_text = hints.get(self.selected_type, "Target")
        
        def _on_browse(self, *args):
            """Open file browser."""
            import tkinter as tk
            from tkinter import filedialog
            
            root = tk.Tk()
            root.withdraw()
            
            if self.selected_type == ShortcutType.STEAM:
                root.destroy()
                self._show_steam_selection()
                return
            
            try:
                if self.selected_type == ShortcutType.FOLDER:
                    path = filedialog.askdirectory(title="Select Folder")
                elif self.selected_type == ShortcutType.SCRIPT:
                    path = filedialog.askopenfilename(
                        title="Select Python Script",
                        filetypes=[("Python Files", "*.py"), ("All Files", "*.*")]
                    )
                elif self.selected_type == ShortcutType.EXECUTABLE:
                    path = filedialog.askopenfilename(
                        title="Select Executable",
                        filetypes=_get_executable_filetypes()
                    )
                elif self.selected_type == ShortcutType.WINE:
                    path = filedialog.askopenfilename(
                        title="Select Windows Executable for Wine",
                        filetypes=_get_wine_executable_filetypes()
                    )
                else:
                    path = None
                
                if path:
                    self.target_field.text = path
            finally:
                root.destroy()
        
        def _show_steam_selection(self):
            """Show Steam game selection dialog."""
            try:
                games = _get_steam_games()
                current_state = LinkedShortcut(
                    name=self.name_field.text.strip(),
                    shortcut_type=self.selected_type,
                    target=self.target_field.text.strip(),
                    description=self.description_field.text.strip(),
                    target_component=self.selected_component,
                    link_type=self.selected_link_type,
                )
                
                def on_game_selected(selected_game):
                    current_state.target = selected_game
                    dialog = LinkedShortcutCreateDialog(self.callback, pre_filled_linked=current_state)
                    dialog.open()
                
                def reopen_dialog():
                    dialog = LinkedShortcutCreateDialog(self.callback, pre_filled_linked=current_state)
                    dialog.open()
                
                dialog = SteamGameSelectionDialog(games, on_game_selected, on_cancel_callback=reopen_dialog)
                self.dismiss()
                dialog.open()
            except SteamLibraryError as e:
                from tkinter import messagebox
                import tkinter as tk
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("Steam Library", str(e))
                root.destroy()
        
        def _create_link(self):
            """Create link."""
            if not self.name_field.text.strip() or not self.target_field.text.strip() or not self.selected_component:
                return
            
            try:
                linked = LinkedShortcut(
                    name=self.name_field.text.strip(),
                    shortcut_type=self.selected_type,
                    target=self.target_field.text.strip(),
                    target_component=self.selected_component,
                    link_type=self.selected_link_type,
                    description=self.description_field.text.strip(),
                )
                self.callback(linked)
                self.dismiss()
            except Exception as e:
                print(f"Error creating linked shortcut: {e}")


    class LinkedShortcutEditDialog(MDDialog):
        """Edit linked shortcut dialog."""
        
        def __init__(self, linked: LinkedShortcut, callback: Callable[[Optional[LinkedShortcut]], None], **kwargs):
            """Initialize with linked shortcut."""
            self.callback = callback
            self.original_linked = linked
            
            self.selected_type = linked.shortcut_type
            self.selected_link_type = linked.link_type
            self.selected_component = linked.target_component
            
            self.component_names = self._get_available_components()
            self.name_field = MDTextField(text=linked.name, hint_text="Name", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            self.target_field = MDTextField(text=linked.target, hint_text="Target", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            self.description_field = MDTextField(text=linked.description, hint_text="Description", mode="outlined", multiline=False, size_hint_y=None, height=dp(56))
            
            type_menu_items = [
                {"text": st.value, "on_release": lambda x=st.value: self._set_type(x)}
                for st in ShortcutType
                if not (st == ShortcutType.WINE and sys.platform == "win32")
            ]
            self.type_dropdown = MDDropdownMenu(items=type_menu_items, width=dp(200))
            self.type_btn = MDButton(MDButtonText(text=linked.shortcut_type.value), size_hint_x=0.33, size_hint_y=None, height=dp(40))
            self.type_btn.bind(on_release=self._show_type_menu)
            
            link_menu_items = [
                {"text": lt.value, "on_release": lambda x=lt.value: self._set_link_type(x)}
                for lt in LinkType
            ]
            self.link_dropdown = MDDropdownMenu(items=link_menu_items, width=dp(200))
            self.link_btn = MDButton(MDButtonText(text=linked.link_type.value), size_hint_x=0.33, size_hint_y=None, height=dp(40))
            self.link_btn.bind(on_release=self._show_link_menu)
            
            comp_menu_items = [
                {"text": c, "on_release": lambda x=c: self._set_component(x)}
                for c in self.component_names
            ]
            self.comp_dropdown = MDDropdownMenu(items=comp_menu_items, width=dp(280))
            self.comp_btn = MDButton(MDButtonText(text=linked.target_component), size_hint_x=0.5, size_hint_y=None, height=dp(40))
            self.comp_btn.bind(on_release=self._show_comp_menu)
            
            browse_btn = MDButton(MDButtonText(text="Browse"), size_hint_x=None, width=dp(100), size_hint_y=None, height=dp(40))
            browse_btn.bind(on_release=self._on_browse)
            
            content = MDDialogContentContainer(orientation="vertical", spacing=dp(12), padding=dp(16))
            
            name_label = MDLabel(text="Name:", size_hint_y=None, height=dp(20))
            content.add_widget(name_label)
            content.add_widget(self.name_field)
            
            type_link_comp_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(40))
            type_label = MDLabel(text="Type:", size_hint_x=None, width=dp(40), size_hint_y=None, height=dp(40))
            type_link_comp_row.add_widget(type_label)
            type_link_comp_row.add_widget(Widget())
            type_link_comp_row.add_widget(self.type_btn)
            link_label = MDLabel(text="Link:", size_hint_x=None, width=dp(35), size_hint_y=None, height=dp(40))
            type_link_comp_row.add_widget(link_label)
            type_link_comp_row.add_widget(Widget())
            type_link_comp_row.add_widget(self.link_btn)
            type_link_comp_row.add_widget(Widget())
            content.add_widget(type_link_comp_row)
            
            comp_label = MDLabel(text="Link to component:", size_hint_y=None, height=dp(20))
            content.add_widget(comp_label)
            content.add_widget(self.comp_btn)
            
            target_label = MDLabel(text="Target:", size_hint_y=None, height=dp(20))
            content.add_widget(target_label)
            target_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(56))
            target_row.add_widget(self.target_field)
            target_row.add_widget(browse_btn)
            content.add_widget(target_row)
            
            desc_label = MDLabel(text="Description:", size_hint_y=None, height=dp(20))
            content.add_widget(desc_label)
            content.add_widget(self.description_field)
            
            buttons = MDDialogButtonContainer(
                MDButton(MDButtonText(text="Save"), on_release=lambda *args: self._save_link(), style="filled"),
                MDButton(MDButtonText(text="Cancel"), on_release=lambda *args: self.dismiss(), style="text"),
                spacing="8dp"
            )
            
            super().__init__(
                MDDialogHeadlineText(text="Edit Linked Shortcut"),
                content,
                buttons,
                auto_dismiss=False,
                **kwargs
            )
        
        def _get_available_components(self) -> List[str]:
            """Get list of available launcher components."""
            try:
                from worlds.LauncherComponents import components, Type
                return [c.display_name for c in components if c.type != Type.HIDDEN]
            except ImportError:
                return ["(No components available????)"]
        
        def _show_type_menu(self, *args):
            """Show type dropdown."""
            self.type_dropdown.caller = self.type_btn
            self.type_dropdown.open()
        
        def _show_link_menu(self, *args):
            """Show link type dropdown."""
            self.link_dropdown.caller = self.link_btn
            self.link_dropdown.open()
        
        def _show_comp_menu(self, *args):
            """Show component dropdown."""
            self.comp_dropdown.caller = self.comp_btn
            self.comp_dropdown.open()
        
        def _set_type(self, type_name: str):
            """Set shortcut type."""
            self.selected_type = ShortcutType[type_name.upper()]
            self.type_btn.children[0].text = type_name
            self.type_dropdown.dismiss()
            self._update_target_hint()
        
        def _set_link_type(self, link_name: str):
            """Set link type."""
            self.selected_link_type = LinkType[link_name.upper()]
            self.link_btn.children[0].text = link_name
            self.link_dropdown.dismiss()
        
        def _set_component(self, comp_name: str):
            """Set target component."""
            self.selected_component = comp_name
            self.comp_btn.children[0].text = comp_name
            self.comp_dropdown.dismiss()
        
        def _update_target_hint(self):
            """Update target hint based on type."""
            hints = {
                ShortcutType.SCRIPT: "Path to Python script",
                ShortcutType.EXECUTABLE: "Path to executable",
                ShortcutType.FOLDER: "Path to folder",
                ShortcutType.URL: "URL (http://...)",
                ShortcutType.FUNCTION: "module.function_name",
                ShortcutType.WINE: "Path to Windows executable (.exe)",
                ShortcutType.STEAM: "Steam game (auto-populated from library)",
            }
            self.target_field.hint_text = hints.get(self.selected_type, "Target")
        
        def _on_browse(self, *args):
            """Open file browser."""
            import tkinter as tk
            from tkinter import filedialog
            
            root = tk.Tk()
            root.withdraw()
            
            if self.selected_type == ShortcutType.STEAM:
                root.destroy()
                self._show_steam_selection()
                return
            
            try:
                if self.selected_type == ShortcutType.FOLDER:
                    path = filedialog.askdirectory(title="Select Folder")
                elif self.selected_type == ShortcutType.SCRIPT:
                    path = filedialog.askopenfilename(
                        title="Select Python Script",
                        filetypes=[("Python Files", "*.py"), ("All Files", "*.*")]
                    )
                elif self.selected_type == ShortcutType.EXECUTABLE:
                    path = filedialog.askopenfilename(
                        title="Select Executable",
                        filetypes=_get_executable_filetypes()
                    )
                elif self.selected_type == ShortcutType.WINE:
                    path = filedialog.askopenfilename(
                        title="Select Windows Executable for Wine",
                        filetypes=_get_wine_executable_filetypes()
                    )
                else:
                    path = None
                
                if path:
                    self.target_field.text = path
            finally:
                root.destroy()
        
        def _show_steam_selection(self):
            """Show Steam game selection dialog."""
            try:
                games = _get_steam_games()
                current_state = LinkedShortcut(
                    name=self.name_field.text.strip(),
                    shortcut_type=self.selected_type,
                    target=self.target_field.text.strip(),
                    description=self.description_field.text.strip(),
                    target_component=self.selected_component,
                    link_type=self.selected_link_type,
                )
                
                def on_game_selected(selected_game):
                    current_state.target = selected_game
                    dialog = LinkedShortcutEditDialog(current_state, self.callback)
                    dialog.open()
                
                def reopen_dialog():
                    dialog = LinkedShortcutEditDialog(current_state, self.callback)
                    dialog.open()
                
                dialog = SteamGameSelectionDialog(games, on_game_selected, on_cancel_callback=reopen_dialog)
                self.dismiss()
                dialog.open()
            except SteamLibraryError as e:
                from tkinter import messagebox
                import tkinter as tk
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("Steam Library", str(e))
                root.destroy()
        
        def _save_link(self):
            """Save link."""
            if not self.name_field.text.strip() or not self.target_field.text.strip() or not self.selected_component:
                return
            
            try:
                linked = LinkedShortcut(
                    name=self.name_field.text.strip(),
                    shortcut_type=self.selected_type,
                    target=self.target_field.text.strip(),
                    target_component=self.selected_component,
                    link_type=self.selected_link_type,
                    description=self.description_field.text.strip(),
                    icon=self.original_linked.icon,
                    args=self.original_linked.args,
                    working_dir=self.original_linked.working_dir,
                    metadata=self.original_linked.metadata,
                )
                self.callback(linked)
                self.dismiss()
            except Exception as e:
                print(f"Error saving linked shortcut: {e}")


    class ShortcutOverrideConfirmDialog(MDDialog):
        """Confirmation dialog when shortcut already exists."""
        
        def __init__(self, existing: Shortcut, new_shortcut: Shortcut, callback: Callable[[bool], None], on_cancel_callback: Callable[[], None] = None, **kwargs):
            """Initialize dialog with existing and new shortcut info."""
            self.callback = callback
            self.on_cancel_callback = on_cancel_callback
            self.new_shortcut = new_shortcut
            
            info_lines = [
                f"Name: {existing.name}",
                f"Type: {existing.shortcut_type.value}",
                f"Target: {existing.target[:50]}{'...' if len(existing.target) > 50 else ''}",
            ]
            if existing.args:
                info_lines.append(f"Args: {existing.args[:50]}")
            if existing.description:
                info_lines.append(f"Desc: {existing.description[:50]}")
            
            info_text = "\n".join(info_lines)
            
            content = MDBoxLayout(orientation="vertical", spacing=dp(8), adaptive_height=True)
            content.add_widget(MDLabel(
                text="Shortcut with this name already exists:",
                size_hint_y=None,
                height=dp(24),
                bold=True
            ))
            content.add_widget(MDLabel(
                text=info_text,
                size_hint_y=None,
                height=dp(120),
                font_size="11sp"
            ))
            
            def on_override(*args):
                self.callback(True)
                self.dismiss()
            
            def on_cancel(*args):
                self.dismiss()
                if self.on_cancel_callback:
                    self.on_cancel_callback()
                else:
                    self.callback(False)
            
            super().__init__(
                MDDialogHeadlineText(text="Override Shortcut?"),
                MDDialogContentContainer(content),
                MDDialogButtonContainer(
                    MDButton(MDButtonText(text="Cancel"), on_release=on_cancel),
                    MDButton(MDButtonText(text="Override"), on_release=on_override),
                    orientation="horizontal",
                    spacing=dp(8),
                    size_hint_x=1,
                ),
                **kwargs
            )


    class LinkedShortcutOverrideConfirmDialog(MDDialog):
        """Confirmation dialog when linked shortcut already exists."""
        
        def __init__(self, existing: LinkedShortcut, new_linked: LinkedShortcut, callback: Callable[[bool], None], on_cancel_callback: Callable[[], None] = None, **kwargs):
            """Initialize dialog with existing and new linked shortcut info."""
            self.callback = callback
            self.on_cancel_callback = on_cancel_callback
            self.new_linked = new_linked
            
            info_lines = [
                f"Name: {existing.name}",
                f"Type: {existing.shortcut_type.value}",
                f"Target: {existing.target_component}",
                f"Link: {existing.link_type.value}",
            ]
            if existing.description:
                info_lines.append(f"Desc: {existing.description[:50]}")
            
            info_text = "\n".join(info_lines)
            
            content = MDBoxLayout(orientation="vertical", spacing=dp(8), adaptive_height=True)
            content.add_widget(MDLabel(
                text="Linked shortcut with this name already exists:",
                size_hint_y=None,
                height=dp(24),
                bold=True
            ))
            content.add_widget(MDLabel(
                text=info_text,
                size_hint_y=None,
                height=dp(110),
                font_size="11sp"
            ))
            
            def on_override(*args):
                self.callback(True)
                self.dismiss()
            
            def on_cancel(*args):
                self.dismiss()
                if self.on_cancel_callback:
                    self.on_cancel_callback()
                else:
                    self.callback(False)
            
            super().__init__(
                MDDialogHeadlineText(text="Override Linked Shortcut?"),
                MDDialogContentContainer(content),
                MDDialogButtonContainer(
                    MDButton(MDButtonText(text="Cancel"), on_release=on_cancel),
                    MDButton(MDButtonText(text="Override"), on_release=on_override),
                    orientation="horizontal",
                    spacing=dp(8),
                    size_hint_x=1,
                ),
                **kwargs
            )


class ShortcutManagerWindow(MDBoxLayout):
    """Main window."""
    
    def __init__(self, ui: 'ShortcutManagerUI', **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.spacing = dp(8)
        self.padding = dp(8)
        self.ui = ui
        
        self.md_bg_color = ui.theme_cls.backgroundColor
        
        title = MDLabel(text="Shortcut Manager", size_hint_y=None, height=dp(35), bold=True, font_size="16sp")
        self.add_widget(title)
        
        button_layout = MDBoxLayout(orientation='horizontal', spacing=dp(8), size_hint_y=None, height=dp(44))
        button_layout.md_bg_color = ui.theme_cls.backgroundColor
        
        add_btn = MDButton(MDButtonText(text="Add Shortcut"))
        add_btn.bind(on_press=self.on_add_shortcut)
        button_layout.add_widget(add_btn)
        
        link_btn = MDButton(MDButtonText(text="Link Shortcut"))
        link_btn.bind(on_press=self.on_link_shortcut)
        button_layout.add_widget(link_btn)
        
        refresh_btn = MDButton(MDButtonText(text="Refresh"))
        refresh_btn.bind(on_press=lambda *args: self.refresh_lists())
        button_layout.add_widget(refresh_btn)
        
        self.add_widget(button_layout)
        
        self.add_widget(MDLabel(text="Shortcuts:", size_hint_y=None, height=dp(18), font_size="13sp"))
        
        self.shortcuts_scroll = ScrollBox(size_hint=(1, 0.4))
        self.shortcuts_scroll.md_bg_color = ui.theme_cls.backgroundColor
        self.add_widget(self.shortcuts_scroll)
        
        self.add_widget(MDLabel(text="Linked Shortcuts:", size_hint_y=None, height=dp(18), font_size="13sp"))
        
        self.linked_scroll = ScrollBox(size_hint=(1, 0.4))
        self.linked_scroll.md_bg_color = ui.theme_cls.backgroundColor
        self.add_widget(self.linked_scroll)
        
        self.refresh_lists()
    
    def refresh_lists(self) -> None:
        """Refresh card lists."""
        self.shortcuts_scroll.layout.clear_widgets()
        
        if not self.ui.collection.shortcuts:
            empty_label = MDLabel(text="(No shortcuts)", size_hint_y=None, height=dp(32))
            self.shortcuts_scroll.layout.add_widget(empty_label)
        else:
            for shortcut in self.ui.collection.shortcuts:
                card_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(80), padding=dp(8))
                
                info_col = MDBoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=1)
                info_col.add_widget(MDLabel(
                    text=f"{shortcut.name}",
                    size_hint_y=None,
                    height=dp(24),
                    bold=True,
                    font_size="14sp"
                ))
                info_col.add_widget(MDLabel(
                    text=f"{shortcut.shortcut_type.value.title()} • {shortcut.component_type}",
                    size_hint_y=None,
                    height=dp(18),
                    font_size="11sp",
                    color=(0.7, 0.7, 0.7, 1)
                ))
                if shortcut.description:
                    info_col.add_widget(MDLabel(
                        text=shortcut.description[:40] + ("..." if len(shortcut.description) > 40 else ""),
                        size_hint_y=None,
                        height=dp(20),
                        font_size="10sp",
                        color=(0.6, 0.6, 0.6, 1)
                    ))
                card_row.add_widget(info_col)
                
                buttons_col = MDBoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=None, width=dp(100))
                edit_btn = MDButton(MDButtonText(text="Edit"), size_hint_x=1, size_hint_y=None, height=dp(36))
                edit_btn.bind(on_press=lambda *args, sc=shortcut: self.on_edit_shortcut(sc))
                buttons_col.add_widget(edit_btn)
                
                delete_btn = MDButton(MDButtonText(text="Delete"), size_hint_x=1, size_hint_y=None, height=dp(36), style="text")
                delete_btn.bind(on_press=lambda *args, sc=shortcut: self.on_delete_shortcut(sc))
                buttons_col.add_widget(delete_btn)
                
                card_row.add_widget(buttons_col)
                self.shortcuts_scroll.layout.add_widget(card_row)
        
        self.linked_scroll.layout.clear_widgets()
        
        if not self.ui.collection.linked_shortcuts:
            empty_label = MDLabel(text="(No linked shortcuts)", size_hint_y=None, height=dp(32))
            self.linked_scroll.layout.add_widget(empty_label)
        else:
            for linked in self.ui.collection.linked_shortcuts:
                card_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(80), padding=dp(8))
                
                info_col = MDBoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=1)
                info_col.add_widget(MDLabel(
                    text=f"{linked.name} -> {linked.target_component} ({linked.link_type.value})",
                    size_hint_y=None,
                    height=dp(24),
                    bold=True,
                    font_size="14sp"
                ))
                info_col.add_widget(MDLabel(
                    text=f"{linked.shortcut_type.value.title()}",
                    size_hint_y=None,
                    height=dp(18),
                    font_size="10sp",
                    color=(0.6, 0.6, 0.6, 1)
                ))
                if linked.description:
                    info_col.add_widget(MDLabel(
                        text=linked.description[:40] + ("..." if len(linked.description) > 40 else ""),
                        size_hint_y=None,
                        height=dp(18),
                        font_size="10sp",
                        color=(0.55, 0.55, 0.55, 1)
                    ))
                card_row.add_widget(info_col)
                
                buttons_col = MDBoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=None, width=dp(100))
                edit_btn = MDButton(MDButtonText(text="Edit"), size_hint_x=1, size_hint_y=None, height=dp(36))
                edit_btn.bind(on_press=lambda *args, lc=linked: self.on_edit_linked(lc))
                buttons_col.add_widget(edit_btn)
                
                delete_btn = MDButton(MDButtonText(text="Delete"), size_hint_x=1, size_hint_y=None, height=dp(36), style="text")
                delete_btn.bind(on_press=lambda *args, lc=linked: self.on_delete_linked(lc))
                buttons_col.add_widget(delete_btn)
                
                card_row.add_widget(buttons_col)
                self.linked_scroll.layout.add_widget(card_row)
    
    def on_add_shortcut(self, *args) -> None:
        """Handle add button."""
        dialog = ShortcutCreateDialog(self.on_shortcut_created)
        dialog.open()
    
    def on_shortcut_created(self, shortcut: Optional[Shortcut]) -> None:
        """Handle creation."""
        if shortcut:
            existing = next((s for s in self.ui.collection.shortcuts if s.name == shortcut.name), None)
            if existing:
                def reopen_creation_dialog():
                    dialog = ShortcutCreateDialog(self.on_shortcut_created, pre_filled_shortcut=shortcut)
                    dialog.open()
                
                def handle_override(override: bool) -> None:
                    if override:
                        self.ui.collection.shortcuts = [s for s in self.ui.collection.shortcuts if s.name != shortcut.name]
                        self.ui.collection.add_shortcut(shortcut)
                        self.ui._save_changes()
                        self.refresh_lists()
                
                dialog = ShortcutOverrideConfirmDialog(existing, shortcut, handle_override, on_cancel_callback=reopen_creation_dialog)
                dialog.open()
            else:
                self.ui.collection.add_shortcut(shortcut)
                self.ui._save_changes()
                self.refresh_lists()
    
    def on_link_shortcut(self, *args) -> None:
        """Handle link button."""
        dialog = LinkedShortcutCreateDialog(self.on_linked_shortcut_created)
        dialog.open()
    
    def on_linked_shortcut_created(self, linked: Optional[LinkedShortcut]) -> None:
        """Handle new linked shortcut creation."""
        if linked:
            existing = next((l for l in self.ui.collection.linked_shortcuts if l.name == linked.name), None)
            if existing:
                def reopen_creation_dialog():
                    dialog = LinkedShortcutCreateDialog(self.on_linked_shortcut_created, pre_filled_linked=linked)
                    dialog.open()
                
                def handle_override(override: bool) -> None:
                    if override:
                        self.ui.collection.remove_linked_shortcut(linked.name)
                        self.ui.collection.add_linked_shortcut(linked)
                        self.ui._save_changes()
                        self.refresh_lists()
                
                dialog = LinkedShortcutOverrideConfirmDialog(existing, linked, handle_override, on_cancel_callback=reopen_creation_dialog)
                dialog.open()
            else:
                success = self.ui.collection.add_linked_shortcut(linked)
                if success:
                    self.ui._save_changes()
                    self.refresh_lists()
    
    def on_edit_shortcut(self, shortcut: Shortcut) -> None:
        """Handle edit shortcut."""
        def on_shortcut_edited_callback(edited_shortcut: Optional[Shortcut]) -> None:
            if edited_shortcut:
                self.ui.collection.shortcuts = [s for s in self.ui.collection.shortcuts if s.name != shortcut.name]
                self.ui.collection.add_shortcut(edited_shortcut)
                self.ui._save_changes()
                self.refresh_lists()
        dialog = ShortcutEditDialog(shortcut, on_shortcut_edited_callback)
        dialog.open()
    
    def on_delete_shortcut(self, shortcut: Shortcut) -> None:
        """Handle delete shortcut."""
        self.ui.collection.shortcuts.remove(shortcut)
        self.ui._save_changes()
        self.refresh_lists()
    
    def on_edit_linked(self, linked: LinkedShortcut) -> None:
        """Handle edit linked shortcut."""
        def on_linked_edited_callback(edited_linked: Optional[LinkedShortcut]) -> None:
            if edited_linked:
                self.ui.collection.remove_linked_shortcut(linked.name)
                self.ui.collection.add_linked_shortcut(edited_linked)
                self.ui._save_changes()
                self.refresh_lists()
        dialog = LinkedShortcutEditDialog(linked, on_linked_edited_callback)
        dialog.open()
    
    def on_delete_linked(self, linked: LinkedShortcut) -> None:
        """Handle delete linked shortcut."""
        self.ui.collection.linked_shortcuts.remove(linked)
        self.ui._save_changes()
        self.refresh_lists()


class ShortcutManagerUI(ThemedApp):
    """Standalone app for shortcut manager (separate window from Launcher)."""
    
    world_path: Optional[Path] = None
    collection: ShortcutCollection = ObjectProperty(None)
    window: Widget = ObjectProperty(None)
    
    def __init__(self, world_path: Optional[Path] = None, **kwargs):
        """Initialize the standalone UI app."""
        super().__init__(**kwargs)
        self.world_path = world_path
        self.collection = ShortcutCollection()
        
        if world_path:
            self.collection = ShortcutStorage.load_shortcuts(world_path)
        
        self.title = "Shortcut Manager"
    
    def _save_changes(self) -> None:
        """Save changes to disk."""
        if self.world_path:
            ShortcutStorage.save_shortcuts(self.world_path, self.collection)
    
    def build(self) -> Widget:
        """Build the UI."""
        self.set_colors()
        self.window = ShortcutManagerWindow(self)
        self.window.md_bg_color = self.theme_cls.backgroundColor
        return self.window


def main_ui(world_path: Optional[Path] = None) -> None:
    """Main UI entry point for shortcut manager (runs in subprocess via launch())."""
    if not KIVY_AVAILABLE:
        raise RuntimeError("Shortcut Manager requires Kivy UI. Kivy is not installed.")
    
    app = ShortcutManagerUI(world_path=world_path)
    app.run()