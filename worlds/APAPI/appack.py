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


def list_top_level_apworlds(appack_path: str | os.PathLike) -> list[str]:
    apworlds: list[str] = []
    seen: set[str] = set()
    with zipfile.ZipFile(appack_path, "r") as zf:
        for info in zf.infolist():
            filename = info.filename
            if not filename or filename.startswith("/") or ".." in filename.split("/"):
                continue
            if "/" in filename:
                continue
            if not filename.lower().endswith(APWORLD_SUFFIX):
                continue
            if filename not in seen:
                seen.add(filename)
                apworlds.append(filename)
    return apworlds


def _is_safe_apworld_name(name: str) -> bool:
    if not name.lower().endswith(APWORLD_SUFFIX):
        return False
    base = name[:-len(APWORLD_SUFFIX)]
    return _is_safe_folder_name(base)


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


def _register_and_load_apworld(target: pathlib.Path) -> bool:
    try:
        import worlds
        import bisect
        for existing in worlds.world_sources:
            try:
                if pathlib.Path(existing.resolved_path) == target:
                    logger.info("World already loaded. Restart required to update: %s", target)
                    return True
            except Exception:
                continue
        source = worlds.WorldSource(str(target), is_zip=True, relative=False)
        bisect.insort(worlds.world_sources, source)
        logger.info("Loading APWorld from: %s...", target)
        ok = bool(source.load())
        if ok:
            try:
                from worlds.AutoWorld import AutoWorldRegister
                from worlds.Files import APWorldContainer
                apworld = APWorldContainer(str(target))
                apworld.read()
                game = apworld.game
                if game and game in AutoWorldRegister.world_types:
                    data = AutoWorldRegister.world_types[game].get_data_package_data()
                    worlds.network_data_package["games"][game] = data
            except Exception as exc:
                logger.warning("Failed to register and load APWorld from: %s (%s)", target, exc) #TODO: Add traceback for clarification.
                pass
        else:
            logger.warning("Failed to load APWorld from: %s", target)
        return ok
    except Exception:
        return False


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
        apworld_files = list_top_level_apworlds(src)
        valid_apworlds: list[str] = []
        for apw in apworld_files:
            if not _is_safe_apworld_name(apw):
                skipped.append(f"{apw} (unsafe name)")
                continue
            valid_apworlds.append(apw)
        if not valid and not valid_apworlds:
            raise Exception(
                "APack appears to contain no worlds. (expected top-level folders with __init__.py or top-level .apworld files)")

    installed: list[pathlib.Path] = []
    skipped_existing: list[str] = []
    for folder in valid:
        target = dest_dir / (folder + APWORLD_SUFFIX)
        if target.exists() and not overwrite:
            skipped_existing.append(f"{folder} (already installed)")
            continue
        build_apworld_from_folder(src, folder, target)
        installed.append(target)
        try:
            _register_and_load_apworld(target)
        except Exception:
            pass
    for apw in valid_apworlds:
        target = dest_dir / apw
        if target.exists() and not overwrite:
            skipped_existing.append(f"{apw} (already installed)")
            continue
        try:
            with zipfile.ZipFile(src, "r") as zf2:
                data = zf2.read(apw)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_fd, tmp_name = tempfile.mkstemp(prefix=pathlib.Path(apw).stem + "_", suffix=APWORLD_SUFFIX, dir=str(dest_dir))
            try:
                with os.fdopen(tmp_fd, "wb") as tmp_file:
                    tmp_file.write(data)
                shutil.move(tmp_name, target)
            finally:
                try:
                    if os.path.exists(tmp_name):
                        os.remove(tmp_name)
                except OSError:
                    pass
            installed.append(target)
            try:
                _register_and_load_apworld(target)
            except Exception:
                pass
        except Exception as exc:
            skipped.append(f"{apw} ({exc})")
            continue

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
        import os
        cur_exe = sys.executable
        if not cur_exe.lower().endswith(".exe"):
            return False
        try:
            from Utils import local_path
            normal = local_path("ArchipelagoLauncher.exe")
        except Exception:
            normal = os.path.join(os.path.dirname(cur_exe), "ArchipelagoLauncher.exe")
        exe = normal if os.path.isfile(normal) else cur_exe
        if os.path.basename(exe).lower() != "archipelagolauncher.exe":
            cand = os.path.join(os.path.dirname(cur_exe), "ArchipelagoLauncher.exe")
            if os.path.isfile(cand):
                exe = cand
            else:
                return False
        if not exe.lower().endswith("archipelagolauncher.exe"):
            return False
    except Exception:
        return False
    prog_id = "ArchipelagoAPack"
    for suffix in (APPACK_SUFFIX, APPACK_SUFFIX_ALT):
        if not suffix.startswith("."):
            suffix = "." + suffix
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{suffix}") as k:
                val, _ = winreg.QueryValueEx(k, "")
                already_ok = (val == prog_id)
                if already_ok:
                    try:
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\shell\\open\\command") as k2:
                            cmd, _ = winreg.QueryValueEx(k2, "")
                            if exe in cmd:
                                try:
                                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}") as k3:
                                        desc, _ = winreg.QueryValueEx(k3, "")
                                        if desc == "Archipelago World Pack":
                                            continue
                                except FileNotFoundError:
                                    pass
                    except FileNotFoundError:
                        pass
        except FileNotFoundError:
            pass
        except Exception:
            pass
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{suffix}") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, prog_id)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Archipelago World Pack")
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
    "list_top_level_apworlds",
    "list_top_level_folders",
]
