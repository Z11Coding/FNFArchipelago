from __future__ import annotations

"""Appack loader: install, auto-unpack, and register appack worlds."""

import bisect
import logging
import pathlib

from .appack import APPACK_SUFFIX, install_appack
from .debug import dprint

logger = logging.getLogger("APAPI.Loader")

_registered = False


def _register_and_load_apworld(target: pathlib.Path) -> bool:
    """Input: apworld path. Returns: True if loaded."""
    try:
        import worlds
    except Exception as exc:
        logger.warning("[APAPI:loader] cannot register %s (no worlds module): %s", target, exc)
        return False
    try:
        for existing in worlds.world_sources:
            try:
                if pathlib.Path(existing.resolved_path) == target:
                    return True
            except Exception:
                continue
        source = worlds.WorldSource(str(target), is_zip=True, relative=False)
        bisect.insort(worlds.world_sources, source)
        ok = bool(source.load())
        if ok:
            _refresh_data_package_for(target)
        else:
            dprint("loader", f"{target.name} registered but failed to load (see log)")
        return ok
    except Exception as exc:
        dprint("loader", f"deferring load of {target.name}: {exc}")
        try:
            from .world_ready import on_worlds_loaded

            def _late_load(_target: pathlib.Path = target) -> None:
                _register_and_load_apworld(_target)

            on_worlds_loaded(_late_load)
        except Exception:
            pass
        return False


def _refresh_data_package_for(target: pathlib.Path) -> None:
    """Input: apworld path. Returns: None (updates data package)."""
    try:
        import worlds
        from worlds.AutoWorld import AutoWorldRegister
        from worlds.Files import APWorldContainer
        apworld = APWorldContainer(str(target))
        apworld.read()
        game = apworld.game
        if game and game in AutoWorldRegister.world_types:
            data = AutoWorldRegister.world_types[game].get_data_package_data()
            worlds.network_data_package["games"][game] = data
    except Exception:
        pass


def _notify_installed(src: pathlib.Path, installed: list[pathlib.Path], skipped: list[str]) -> None:
    """Input: src, installed, skipped. Returns: None (logs/notifies)."""
    names = ", ".join(path.stem for path in installed) if installed else "(none)"
    text = f"Installed APack from {src}:\n{names}"
    if skipped:
        text += f"\nSkipped: {', '.join(skipped)}"
    logging.info(text)
    try:
        import Utils
        Utils.messagebox("Install complete.", text)
    except Exception:
        pass


def install_appack_ui(appack_src: str = "") -> None:
    """Input: optional path (dialog if empty). Returns: None."""
    try:
        if not appack_src:
            try:
                import Utils
                picked = Utils.open_filename(
                    "Select APack file to install", (("APack", (APPACK_SUFFIX,)),))
            except Exception as exc:
                raise Exception(f"Could not open file dialog: {exc}") from exc
            if not picked:
                logging.info("Aborting APack installation.")
                return
            appack_src = picked
        src, installed, skipped = install_appack(appack_src, overwrite=True)
        for target in installed:
            _register_and_load_apworld(target)
        if not installed:
            raise Exception(f"Nothing installed from {src}. Skipped: {', '.join(skipped)}")
        _notify_installed(src, installed, skipped)
    except Exception as exc:
        logging.exception(exc)
        try:
            import Utils
            Utils.messagebox("Notice", str(exc), error=True)
        except Exception:
            pass


def scan_and_unpack_pending(notify: bool = True) -> tuple[list[pathlib.Path], list[str]]:
    """Input: notify flag. Returns: (installed, notes)."""
    installed_all: list[pathlib.Path] = []
    notes: list[str] = []
    try:
        import worlds
        folder = getattr(worlds, "user_folder", None)
    except Exception:
        folder = None
    if not folder:
        try:
            from Utils import user_path
            folder = user_path("custom_worlds")
        except Exception:
            return installed_all, notes
    base = pathlib.Path(folder)
    if not base.is_dir():
        return installed_all, notes
    try:
        candidates = sorted(path for path in base.iterdir()
                            if path.is_file() and path.suffix.lower() == APPACK_SUFFIX)
    except OSError:
        return installed_all, notes
    for appack_path in candidates:
        try:
            src, installed, skipped = install_appack(appack_path, overwrite=False)
        except Exception as exc:
            notes.append(f"{appack_path.name}: {exc}")
            logger.warning("[APAPI:loader] auto-unpack failed for %s: %s", appack_path, exc)
            continue
        for target in installed:
            _register_and_load_apworld(target)
        if installed:
            installed_all.extend(installed)
            dprint("loader", f"auto-unpacked {appack_path.name}: "
                             f"{', '.join(t.stem for t in installed)}")
        if skipped:
            notes.append(f"{appack_path.name}: skipped {', '.join(skipped)}")
    if notify and installed_all:
        names = ", ".join(path.stem for path in installed_all)
        text = f"APack file(s) in custom_worlds were automatically unpacked:\n{names}"
        logging.info(text)
        try:
            import Utils
            Utils.messagebox("APack auto-unpacked.", text)
        except Exception:
            pass
    return installed_all, notes


def _auto_unpack_once() -> None:
    """Input: None. Returns: None (scans and unpacks)."""
    try:
        scan_and_unpack_pending(notify=True)
    except Exception as exc:
        logger.warning("[APAPI:loader] auto-unpack pass failed: %s", exc)


def initialize() -> None:
    """Input: None. Returns: None (registers launcher component)."""
    global _registered
    if not _registered:
        try:
            from worlds.LauncherComponents import Component, SuffixIdentifier, components, Type
            exists = any(
                isinstance(getattr(c, "file_identifier", None), SuffixIdentifier)
                and APPACK_SUFFIX in tuple(getattr(c.file_identifier, "suffixes", ()))
                for c in components
            )
            if not exists:
                components.append(Component(
                    "Install APack",
                    func=install_appack_ui,
                    file_identifier=SuffixIdentifier(APPACK_SUFFIX),
                    component_type=Type.MISC,
                    description="Install an APack (multi-world pack: each top-level folder "
                                "becomes its own APWorld in custom_worlds).",
                ))
                dprint("loader", "registered Install APack launcher component")
        except Exception as exc:
            logger.warning("[APAPI:loader] launcher registration failed: %s", exc)
        _registered = True
    try:
        from .appack import ensure_appack_association
        ensure_appack_association()
    except Exception as exc:
        logger.debug("[APAPI:loader] appack association check failed: %s", exc)
    try:
        from .world_ready import on_worlds_loaded, worlds_loading_complete
        if worlds_loading_complete():
            _auto_unpack_once()
        else:
            on_worlds_loaded(_auto_unpack_once)
    except Exception:
        _auto_unpack_once()


__all__ = [
    "initialize",
    "install_appack_ui",
    "scan_and_unpack_pending",
]
