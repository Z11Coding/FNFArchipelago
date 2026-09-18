from __future__ import annotations

"""Launch context detection for APAPI.

Detects which core entry point is currently running (Generate, Launcher, etc.)
Works for both frozen (PyInstaller/cx_Freeze) and non-frozen (python *.py) launches.

Usage:
    from worlds.APAPI import get_launch_context, is_generate_context, should_skip_app_window

    if is_generate_context():
        # skip anything that would open a kivy/tk window
        pass

    if should_skip_app_window():
        # same — generation sans Uploader exception
        pass

Enum-esque string constants are exposed for direct comparison:
    GENERATE, LAUNCHER, SERVER, CLIENT, UPLOADER, OPTIONS_CREATOR, UNKNOWN, etc.
"""

import os
import sys
from typing import Final

# ---------------------------------------------------------------------------
# String constants — enum-esque
# ---------------------------------------------------------------------------
GENERATE: Final[str] = "Generate"
LAUNCHER: Final[str] = "Launcher"
SERVER: Final[str] = "Server"          # MultiServer / ArchipelagoServer
CLIENT: Final[str] = "Client"          # CommonClient / TextClient
UPLOADER: Final[str] = "Uploader"      # ArchipelagoUploader
OPTIONS_CREATOR: Final[str] = "OptionsCreator"
ADJUSTER: Final[str] = "Adjuster"
HOST: Final[str] = "Host"              # alias for Server
UNKNOWN: Final[str] = "Unknown"

# All known contexts (for validation / docs)
ALL_CONTEXTS: Final[tuple[str, ...]] = (
    GENERATE, LAUNCHER, SERVER, HOST, CLIENT, UPLOADER, OPTIONS_CREATOR, ADJUSTER, UNKNOWN,
)

# Normalised aliases
_HOST_ALIASES = {"host", "server", "multiserver", "archipelagoserver"}
_GENERATE_ALIASES = {"generate", "main"}  # Main.py is the generation worker called by Generate.py
_LAUNCHER_ALIASES = {"launcher", "archipelagolauncher"}
_CLIENT_ALIASES = {"commonclient", "textclient", "client"}
_UPLOADER_ALIASES = {"uploader", "archipelagouploader"}
_OPTIONS_CREATOR_ALIASES = {"optionscreator", "archipelagooptionscreator"}
_ADJUSTER_ALIASES = {"adjuster", "lttpadjuster", "ootadjuster"}

# ---------------------------------------------------------------------------
# Internal detection
# ---------------------------------------------------------------------------
_cached_context: str | None = None


def _is_frozen() -> bool:
    """Input: None. Returns: True if running frozen (PyInstaller/cx_Freeze)."""
    try:
        from Utils import is_frozen as _is_frozen_util  # type: ignore
        return bool(_is_frozen_util())
    except Exception:
        return bool(getattr(sys, "frozen", False))


def _exe_basename() -> str:
    """Input: None. Returns: lowercased basename of frozen executable or ''."""
    try:
        exe = sys.executable or ""
        return os.path.basename(exe).lower()
    except Exception:
        return ""


def _argv_basenames() -> list[str]:
    """Input: None. Returns: lowercased basenames from sys.argv and __main__.__file__."""
    names: list[str] = []
    try:
        if sys.argv:
            for a in sys.argv:
                if isinstance(a, str) and a:
                    # argv may contain flags; only keep file-like entries
                    base = os.path.basename(a).lower()
                    if base:
                        names.append(base)
            # Also include the whole argv string lowercased for substring checks like "generate.py"
            joined = " ".join(str(x) for x in sys.argv).lower()
            if joined:
                names.append(joined)
    except Exception:
        pass
    try:
        main_mod = sys.modules.get("__main__")
        main_file = getattr(main_mod, "__file__", None) if main_mod else None
        if isinstance(main_file, str) and main_file:
            names.append(os.path.basename(main_file).lower())
            names.append(main_file.lower())
    except Exception:
        pass
    return names


def _detect_context() -> str:
    """Input: None. Returns: detected launch context string (one of the constants)."""
    # Frozen takes precedence — exe name is authoritative
    if _is_frozen():
        exe = _exe_basename()
        # exe examples: archipelagogenerate.exe, archipelagolauncher.exe, archipelagoserver.exe
        if exe:
            if any(k in exe for k in _UPLOADER_ALIASES):
                return UPLOADER
            if any(k in exe for k in _GENERATE_ALIASES):
                # "main" not expected in frozen, but handle
                return GENERATE
            if any(k in exe for k in _LAUNCHER_ALIASES):
                return LAUNCHER
            if any(k in exe for k in _HOST_ALIASES):
                return SERVER
            if any(k in exe for k in _OPTIONS_CREATOR_ALIASES):
                return OPTIONS_CREATOR
            if any(k in exe for k in _ADJUSTER_ALIASES):
                return ADJUSTER
            if any(k in exe for k in _CLIENT_ALIASES):
                return CLIENT
        # Fallback for frozen but unknown exe: check argv as well
        # (some frozen launchers still pass script name as argv[1])

    # Non-frozen (or frozen fallback): inspect argv / __main__
    names = _argv_basenames()
    blob = "\n".join(names)

    # Order matters: most specific first
    if any(k in blob for k in _UPLOADER_ALIASES):
        return UPLOADER
    if any(k in blob for k in _OPTIONS_CREATOR_ALIASES):
        return OPTIONS_CREATOR
    if any(k in blob for k in _ADJUSTER_ALIASES):
        return ADJUSTER
    if "generate.py" in blob or "generate" in blob and "archipelagogenerate" in blob:
        return GENERATE
    # Generate.py module name check — handles `python -m Generate` where argv[0] is "-m"
    try:
        if "Generate" in sys.modules:
            # If Generate was imported as __main__ or via Main, consider generate context
            # Only if we haven't already matched launcher/server
            if "launcher" not in blob and "multiserver" not in blob and "server" not in blob:
                # Check if Generate.main is on the stack would be more precise, but module presence + argv hint suffices
                # For safety, require either argv hints or Main being imported
                if "generate" in blob or "main.py" in blob:
                    return GENERATE
    except Exception:
        pass
    if "launcher.py" in blob or "launcher" in blob:
        return LAUNCHER
    if "multiserver.py" in blob or "archipelagoserver" in blob or "server" in blob and "client" not in blob:
        # Avoid misclassifying "server" substring in other names
        if "multiserver" in blob or "archipelagoserver" in blob or "server.py" in blob:
            return SERVER
    if "commonclient" in blob or "textclient" in blob:
        return CLIENT
    if "main.py" in blob:
        # Main.py is the generation worker; treat as GENERATE unless it's the host server path
        # Main is imported by Generate; if we're in Main context outside server, it's generation
        return GENERATE
    if "generate" in blob:
        return GENERATE
    # WebHost / test harness: Main.main called programmatically with no argv hint
    # Heuristic: if we're currently inside Main.main / Generate.main call stack, treat as generate
    # This covers `from Main import main; main(...)` without argv
    try:
        import traceback
        stack = "".join(traceback.format_stack())
        # Only consider if worlds are being loaded for generation — cheap check
        if "Generate.py" in stack or "Main.py" in stack and "Launcher.py" not in stack:
            # Avoid false positive from Launcher importing Generate for templates
            if GENERATE.lower() in stack.lower() or "Main.main" in stack:
                # Extra guard: ensure not launcher importing main for other reasons
                if "Launcher" not in stack or "Generate" in stack:
                    return GENERATE
    except Exception:
        pass
    return UNKNOWN


def get_launch_context(refresh: bool = False) -> str:
    """Input: refresh. Returns: current launch context (one of the GENERATE/LAUNCHER/... constants)."""
    global _cached_context
    if _cached_context is None or refresh:
        _cached_context = _detect_context()
    return _cached_context


def is_generate_context() -> bool:
    """Input: None. Returns: True if current launch is Generate/Main generation."""
    ctx = get_launch_context()
    return ctx == GENERATE


def is_launcher_context() -> bool:
    """Input: None. Returns: True if Launcher."""
    return get_launch_context() == LAUNCHER


def is_server_context() -> bool:
    """Input: None. Returns: True if hosting a server."""
    ctx = get_launch_context()
    return ctx in (SERVER, HOST)


def is_uploader_context() -> bool:
    """Input: None. Returns: True if ArchipelagoUploader."""
    return get_launch_context() == UPLOADER


def is_options_creator_context() -> bool:
    """Input: None. Returns: True if OptionsCreator."""
    return get_launch_context() == OPTIONS_CREATOR


def is_client_context() -> bool:
    """Input: None. Returns: True if a client (Text/ Common)."""
    return get_launch_context() == CLIENT


def should_skip_app_window() -> bool:
    """Input: None. Returns: True if app windows should be suppressed.

    True during generation (Generate/Main) but False for Uploader, Launcher,
    Server, Client, etc. Uploader is explicitly allowed to show its final
    confirmation window even though it runs after generation.
    """
    ctx = get_launch_context()
    if ctx == UPLOADER:
        return False
    return ctx == GENERATE


def should_skip_gui_patch() -> bool:
    """Input: None. Returns: True if GUI patches (kivy) should be skipped.

    Alias for should_skip_app_window — kept for readability at call sites
    that patch OptionsCreator / preset manager.
    """
    return should_skip_app_window()


def invalidate_cache() -> None:
    """Input: None. Returns: None (clears cached context, next call re-detects)."""
    global _cached_context
    _cached_context = None


__all__ = [
    "GENERATE", "LAUNCHER", "SERVER", "HOST", "CLIENT", "UPLOADER",
    "OPTIONS_CREATOR", "ADJUSTER", "UNKNOWN", "ALL_CONTEXTS",
    "get_launch_context", "is_generate_context", "is_launcher_context",
    "is_server_context", "is_uploader_context", "is_options_creator_context",
    "is_client_context", "should_skip_app_window", "should_skip_gui_patch",
    "invalidate_cache",
]
