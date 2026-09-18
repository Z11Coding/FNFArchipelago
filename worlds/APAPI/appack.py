from __future__ import annotations

from worlds.APAPI.debug import dprint

"""Appack support: packs multiple world folders into apworld archives."""

import logging
import os
import pathlib
import shutil
import tempfile
import zipfile

logger = logging.getLogger("APAPI.AppPack")

APPACK_SUFFIX = ".appack"
APPACK_SUFFIX_ALT = ".apack"
APWORLD_SUFFIX = ".apworld"


def _is_safe_folder_name(name: str) -> bool:
    """Input: name. Returns: True if safe folder name."""
    if not name or name in (".", ".."):
        return False
    if "/" in name or "\\" in name or ":" in name:
        return False
    if name.startswith((".", "_")):
        return False
    if ".." in name:
        return False
    return True


def list_top_level_folders(appack_path: str | os.PathLike) -> list[str]:
    """Input: appack zip path. Returns: top-level folder names."""
    folders: list[str] = []
    seen: set[str] = set()
    with zipfile.ZipFile(appack_path, "r") as zf:
        for info in zf.infolist():
            filename = info.filename
            if not filename or filename.startswith("/") or ".." in filename.split("/"):
                continue
            parts = filename.split("/")
            if len(parts) < 2 or not parts[0]:
                continue
            top = parts[0]
            if top not in seen:
                seen.add(top)
                folders.append(top)
    return folders


def _folder_has_init(zf: zipfile.ZipFile, folder: str, namelist: set[str]) -> bool:
    """Input: zip, folder, namelist. Returns: True if folder has __init__.py."""
    return f"{folder}/__init__.py" in namelist or f"{folder}/__init__.pyc" in namelist


def build_apworld_from_folder(
    appack_path: str | os.PathLike,
    folder: str,
    dest_apworld_path: str | os.PathLike,
) -> None:
    """Input: appack path, folder name, dest path. Returns: None (writes apworld)."""
    dest_apworld_path = pathlib.Path(dest_apworld_path)
    with zipfile.ZipFile(appack_path, "r") as src:
        names = [info for info in src.infolist()
                 if info.filename == folder + "/" or info.filename.startswith(folder + "/")]
        if not names:
            raise Exception(f"Folder {folder!r} not found in {appack_path}.")
        dest_apworld_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=dest_apworld_path.stem + "_", suffix=".apworld",
            dir=str(dest_apworld_path.parent))
        try:
            with os.fdopen(tmp_fd, "wb") as tmp_file:
                with zipfile.ZipFile(tmp_file, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as dst:
                    for info in names:
                        data = src.read(info.filename)
                        dst.writestr(info.filename, data)
            shutil.move(tmp_name, dest_apworld_path)
        finally:
            try:
                if os.path.exists(tmp_name):
                    os.remove(tmp_name)
            except OSError:
                pass


def _user_folder() -> pathlib.Path:
    """Returns: custom_worlds folder path."""
    try:
        import worlds
        folder = getattr(worlds, "user_folder", None)
    except Exception:
        folder = None
    if not folder:
        from Utils import user_path
        folder = user_path("custom_worlds")
    return pathlib.Path(folder)


def install_appack(
    appack_src: str | os.PathLike = "",
    overwrite: bool = True,
) -> tuple[pathlib.Path, list[pathlib.Path], list[str]]:
    """Input: appack_src, overwrite flag. Returns: (source, installed, skipped)."""
    if not appack_src:
        raise Exception("No appack file given.")
    src = pathlib.Path(appack_src)
    if not src.is_file():
        raise Exception(f"APack file not found: {src}")
    if src.suffix.lower() != APPACK_SUFFIX and src.suffix.lower() != APPACK_SUFFIX_ALT:
        raise Exception(f"Wrong file format, looking for {APPACK_SUFFIX} or {APPACK_SUFFIX_ALT}. File identified: {src}")
    try:
        if not zipfile.is_zipfile(src):
            raise Exception(f"File is not a valid zip archive: {src}")
    except Exception as exc:
        raise Exception(f"Archive appears invalid or damaged: {exc}") from exc

    dest_dir = _user_folder()
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise Exception("Custom Worlds directory appears to not be writable.") from exc

    with zipfile.ZipFile(src, "r") as zf:
        try:
            namelist = set(zf.namelist())
        except Exception as exc:
            raise Exception("Archive appears invalid or damaged.") from exc
        folders = list_top_level_folders(src)
        valid: list[str] = []
        skipped: list[str] = []
        for folder in folders:
            if not _is_safe_folder_name(folder):
                skipped.append(f"{folder} (unsafe name)")
                continue
            if not _folder_has_init(zf, folder, namelist):
                skipped.append(f"{folder} (missing __init__.py)")
                continue
            valid.append(folder)
        if not valid:
            raise Exception(
                "APack appears to contain no worlds. (expected top-level folders with __init__.py)")

    installed: list[pathlib.Path] = []
    skipped_existing: list[str] = []
    for folder in valid:
        target = dest_dir / (folder + APWORLD_SUFFIX)
        if target.exists() and not overwrite:
            skipped_existing.append(f"{folder} (already installed)")
            continue
        build_apworld_from_folder(src, folder, target)
        installed.append(target)

    return src, installed, skipped + skipped_existing


def ensure_appack_association() -> bool:
    """Ensure .apack/.appack files open with Archipelago Launcher on first frozen launch."""
    try:
        from Utils import is_frozen
        if not is_frozen():
            return False
    except Exception:
        import sys
        if not getattr(sys, "frozen", False):
            return False
    try:
        import sys
        import winreg
    except Exception:
        return False
    if sys.platform != "win32":
        return False
    try:
        exe = sys.executable
        if not exe.lower().endswith(".exe"):
            return False
    except Exception:
        return False
    # Check both suffixes (appack with one p and two p's) for robustness
    for suffix in (APPACK_SUFFIX, APPACK_SUFFIX_ALT, ".apack", ".appack"):
        if not suffix.startswith("."):
            suffix = "." + suffix
        prog_id = "ArchipelagoAPack"
        # Use HKCU for per-user without admin, fallback to HKCR is handled by installer
        # Check if already associated correctly
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{suffix}") as k:
                val, _ = winreg.QueryValueEx(k, "")
                if val == prog_id:
                    # Check open command
                    try:
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\shell\\open\\command") as k2:
                            cmd, _ = winreg.QueryValueEx(k2, "")
                            if exe in cmd:
                                continue
                    except FileNotFoundError:
                        pass
        except FileNotFoundError:
            pass
        except Exception:
            continue
        # Not correctly associated, create it (first launch)
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{suffix}") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, prog_id)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Archipelago APack")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\DefaultIcon") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f"{exe},0")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\shell\\open\\command") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{exe}" "%1"')
            dprint("appack", f"associated {suffix} -> {prog_id} for first launch")
            logger.info("Associated %s with Archipelago Launcher for first launch", suffix)
        except Exception as exc:
            logger.debug("APack association failed for %s: %s", suffix, exc)
            continue
    return True


__all__ = [
    "APPACK_SUFFIX",
    "APWORLD_SUFFIX",
    "build_apworld_from_folder",
    "ensure_appack_association",
    "install_appack",
    "list_top_level_folders",
]
