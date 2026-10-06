"""Core Shortcut Manager - handles storage and retrieval of shortcuts."""

import zipfile
import json
import os
import shutil
from pathlib import Path
from typing import Optional, Tuple, Dict, List
from .structures import ShortcutCollection, Shortcut, LinkedShortcut, ShortcutType

from Utils import user_path, local_path


class ShortcutStorage:
    """Shortcut storage for dev and APWorld modes."""
    
    DEBUG_FOLDER = "__debug_shortcuts__"
    SHORTCUTS_FILE = "shortcuts.json"
    
    @classmethod
    def get_debug_folder(cls) -> Path:
        """Debug folder path in AP root."""
        return Path(local_path()) / cls.DEBUG_FOLDER
    
    @classmethod
    def get_apworld_folder(cls) -> Path:
        """Custom worlds folder path."""
        return Path(user_path()) / "custom_worlds"
    
    @classmethod
    def is_dev_mode(cls, world_path: Path) -> bool:
        """Check if world is in dev mode."""
        return world_path.parent.name == "worlds"
    
    @classmethod
    def load_shortcuts(cls, world_path: Path) -> ShortcutCollection:
        """Load shortcuts."""
        if cls.is_dev_mode(world_path):
            return cls._load_from_debug(world_path)
        else:
            return cls._load_from_apworld(world_path)
    
    @classmethod
    def save_shortcuts(cls, world_path: Path, collection: ShortcutCollection) -> None:
        """Save shortcuts."""
        if cls.is_dev_mode(world_path):
            cls._save_to_debug(world_path, collection)
        else:
            cls._save_to_apworld(world_path, collection)
    
    @classmethod
    def _load_from_debug(cls, world_path: Path) -> ShortcutCollection:
        """Load from debug folder."""
        debug_folder = cls.get_debug_folder()
        world_name = world_path.name
        shortcuts_file = debug_folder / world_name / cls.SHORTCUTS_FILE
        
        if shortcuts_file.exists():
            with open(shortcuts_file, 'r') as f:
                return ShortcutCollection.from_json(f.read())
        
        return ShortcutCollection()
    
    @classmethod
    def _save_to_debug(cls, world_path: Path, collection: ShortcutCollection) -> None:
        """Save to debug folder."""
        debug_folder = cls.get_debug_folder()
        world_name = world_path.name
        world_debug_folder = debug_folder / world_name
        world_debug_folder.mkdir(parents=True, exist_ok=True)
        
        shortcuts_file = world_debug_folder / cls.SHORTCUTS_FILE
        with open(shortcuts_file, 'w') as f:
            f.write(collection.to_json())
    
    @classmethod
    def _load_from_apworld(cls, apworld_path: Path) -> ShortcutCollection:
        """Load from APWorld zip."""
        if not apworld_path.exists() or not apworld_path.suffix == ".apworld":
            return ShortcutCollection()
        
        try:
            with zipfile.ZipFile(apworld_path, 'r') as zf:
                for name in zf.namelist():
                    if name.endswith(cls.SHORTCUTS_FILE):
                        with zf.open(name) as f:
                            return ShortcutCollection.from_json(f.read().decode('utf-8'))
        except (zipfile.BadZipFile, KeyError):
            pass
        
        return ShortcutCollection()
    
    @classmethod
    def _save_to_apworld(cls, apworld_path: Path, collection: ShortcutCollection) -> None:
        """Save to APWorld zip."""
        if not apworld_path.exists() or not apworld_path.suffix == ".apworld":
            return
        world_name = apworld_path.stem
        temp_dir = Path(apworld_path.parent) / f".temp_{world_name}"
        temp_dir.mkdir(exist_ok=True)
        try:
            with zipfile.ZipFile(apworld_path, 'r') as zf:
                zf.extractall(temp_dir)
            world_dirs = [d for d in (temp_dir / world_name).iterdir() if d.is_dir()]
            shortcuts_file = world_dirs[0] / cls.SHORTCUTS_FILE if world_dirs else temp_dir / world_name / cls.SHORTCUTS_FILE
            shortcuts_file.parent.mkdir(parents=True, exist_ok=True)
            with open(shortcuts_file, 'w') as f:
                f.write(collection.to_json())
            with zipfile.ZipFile(apworld_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(temp_dir)
                        zf.write(file_path, arcname)
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
    
    @classmethod
    def list_apworlds(cls) -> List[Tuple[str, Path]]:
        """List available APWorld files."""
        apworlds = []
        custom_folder = cls.get_apworld_folder()
        if custom_folder.exists():
            for apworld in custom_folder.glob("*.apworld"):
                apworlds.append((apworld.stem, apworld))
        worlds_folder = Path(local_path()) / "worlds"
        if worlds_folder.exists():
            for world_dir in worlds_folder.iterdir():
                if world_dir.is_dir() and (world_dir / "__init__.py").exists():
                    apworlds.append((world_dir.name, world_dir))
        
        return apworlds
    
    @classmethod
    def get_backup_folder(cls) -> Path:
        """Backup folder path for shortcuts when APWorld is missing."""
        backup_folder = Path(local_path()) / "data" / "apworld_shortcuts_backup"
        backup_folder.mkdir(parents=True, exist_ok=True)
        return backup_folder
    
    @classmethod
    def save_shortcuts_backup(cls, world_name: str, collection: ShortcutCollection) -> bool:
        """Save shortcuts to backup location (data folder)."""
        try:
            backup_folder = cls.get_backup_folder()
            backup_file = backup_folder / f"{world_name}.json"
            with open(backup_file, 'w') as f:
                f.write(collection.to_json())
            return True
        except Exception as e:
            print(f"Error saving shortcuts backup for {world_name}: {e}")
            return False
    
    @classmethod
    def load_shortcuts_backup(cls, world_name: str) -> Optional[ShortcutCollection]:
        """Load shortcuts from backup location and delete the backup file."""
        try:
            backup_folder = cls.get_backup_folder()
            backup_file = backup_folder / f"{world_name}.json"
            
            if backup_file.exists():
                with open(backup_file, 'r') as f:
                    collection = ShortcutCollection.from_json(f.read())
                backup_file.unlink()  # Delete backup file after loading
                return collection
        except Exception as e:
            print(f"Error loading shortcuts backup for {world_name}: {e}")
        
        return None


class ShortcutExecutor:
    """Execute shortcuts."""
    
    @classmethod
    def execute(cls, shortcut: Shortcut, cwd: Optional[str] = None) -> bool:
        """Execute shortcut."""
        import subprocess
        import webbrowser
        
        try:
            if shortcut.shortcut_type == ShortcutType.SCRIPT:
                return cls._execute_script(shortcut, cwd)
            elif shortcut.shortcut_type == ShortcutType.EXECUTABLE:
                return cls._execute_executable(shortcut, cwd)
            elif shortcut.shortcut_type == ShortcutType.FOLDER:
                return cls._open_folder(shortcut)
            elif shortcut.shortcut_type == ShortcutType.URL:
                return cls._open_url(shortcut)
            elif shortcut.shortcut_type == ShortcutType.FUNCTION:
                return cls._execute_function(shortcut)
            elif shortcut.shortcut_type == ShortcutType.WINE:
                return cls._execute_wine(shortcut, cwd)
            elif shortcut.shortcut_type == ShortcutType.STEAM:
                return cls._execute_steam(shortcut)
        except Exception as e:
            print(f"Error executing shortcut '{shortcut.name}': {e}")
            return False
        
        return False
    
    @classmethod
    def _execute_script(cls, shortcut: Shortcut, cwd: Optional[str] = None) -> bool:
        """Execute Python script."""
        import subprocess
        import sys
        
        target = Path(shortcut.target)
        if not target.exists():
            return False
        
        cmd = [sys.executable, str(target)]
        if shortcut.args:
            cmd.extend(shortcut.args.split())
        
        subprocess.Popen(cmd, cwd=shortcut.working_dir or target.parent.absolute().resolve() or os.getcwd())
        return True
    
    @classmethod
    def _execute_executable(cls, shortcut: Shortcut, cwd: Optional[str] = None) -> bool:
        """Execute executable."""
        import subprocess
        
        target = Path(shortcut.target)
        if not target.exists():
            return False
        
        cmd = [str(target)]
        if shortcut.args:
            cmd.extend(shortcut.args.split())
        
        subprocess.Popen(cmd, cwd=shortcut.working_dir or str(target.parent.absolute().resolve()) or os.getcwd())
        return True
    
    @classmethod
    def _open_folder(cls, shortcut: Shortcut) -> bool:
        """Open folder."""
        import subprocess
        import sys
        import platform
        
        folder = Path(shortcut.target)
        if not folder.exists():
            return False
        
        try:
            if platform.system() == "Windows":
                os.startfile(str(folder))
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", str(folder)])
            else:  # Linux
                subprocess.Popen(["xdg-open", str(folder)])
            return True
        except Exception as e:
            print(f"Error opening folder: {e}")
            return False
    
    @classmethod
    def _open_url(cls, shortcut: Shortcut) -> bool:
        """Open URL."""
        import webbrowser
        
        webbrowser.open(shortcut.target)
        return True
    
    @classmethod
    def _execute_function(cls, shortcut: Shortcut) -> bool:
        """Execute Python function."""
        try:
            parts = shortcut.target.rsplit(".", 1)
            if len(parts) == 2:
                module_name, func_name = parts
                import importlib
                module = importlib.import_module(module_name)
                func = getattr(module, func_name)
                
                if shortcut.args:
                    func(*shortcut.args.split())
                else:
                    func()
                return True
        except Exception as e:
            print(f"Error executing function shortcut: {e}")
        
        return False
    
    @classmethod
    def _execute_wine(cls, shortcut: Shortcut, cwd: Optional[str] = None) -> bool:
        """Execute Windows executable via Wine."""
        import subprocess
        import sys
        
        if sys.platform == "win32":
            print("Wine is only available on non-Windows systems")
            return False
        
        target = Path(shortcut.target)
        if not target.exists():
            return False
        
        cmd = ["wine", str(target)]
        if shortcut.args:
            cmd.extend(shortcut.args.split())
        
        work_dir = shortcut.working_dir or target.parent
        subprocess.Popen(cmd, cwd=str(work_dir))
        return True
    
    @classmethod
    def _execute_steam(cls, shortcut: Shortcut) -> bool:
        """Launch Steam game by app ID."""
        import webbrowser
        import urllib.parse
        
        target = shortcut.target
        if not target or "(" not in target or ")" not in target:
            print(f"Error: Invalid Steam target format: {target}")
            import tkinter
            from tkinter import messagebox
            root = tkinter.Tk()
            root.withdraw()
            messagebox.showerror("Error", f"Invalid Steam target format: {target}")
            root.destroy()
            return False
        
        app_id = target.split("(")[-1].rstrip(")")
        
        try:
            if not shortcut.args:
                webbrowser.open(f"steam://run/{app_id}")
            else:
                encoded_args = urllib.parse.quote(shortcut.args, safe='')
                webbrowser.open(f"steam://run/{app_id}//{encoded_args}")
            return True
        except Exception as e:
            print(f"Error launching Steam game: {e}")
            return False
