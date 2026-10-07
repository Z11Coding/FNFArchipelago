from __future__ import annotations

import logging
import os
import pathlib
import re
import shutil
import tempfile
import zipfile
from typing import Any, Dict, List, Tuple

from Options import FreeText

logger = logging.getLogger("APAPI.Updater")


class ApworldVersionWanted(FreeText):
    display_name = "Apworld Version Wanted"
    default = ""

    def verify(self, world: Any, player_name: str, plando_options: Any) -> None:
        if not isinstance(self.value, str):
            raise ValueError(f"apworld_version_wanted must be a string for {player_name}.")
        if self.value and not self.value.strip():
            raise ValueError(f"apworld_version_wanted must be non-empty string for {player_name} if set.")


def _parse_spec(spec: str) -> tuple[str, str]:
    spec = spec.strip()
    if spec.startswith("http://") or spec.startswith("https://"):
        if spec.lower().endswith(".apworld"):
            return "direct", spec
        if "/releases/" in spec or "/releases/tag/" in spec or "/releases/download/" in spec:
            return "release", spec
        return "direct", spec
    if spec.startswith("github:"):
        return "github", spec[len("github:"):].strip()
    if re.match(r"^v?\d+(\.\d+)*$", spec):
        return "index", spec
    if "/" in spec and ("github.com" in spec or "@" in spec or spec.count("/") >= 1):
        return "github", spec
    return "index", spec


def _get_version_from_path(path: pathlib.Path) -> str | None:
    """Return the real world_version for an apworld/folder, or None if unknown.

    Never returns the zip container version: an unknown version must stay
    unknown so registry keys cannot collapse across versions.
    """
    try:
        if path.is_file() and path.suffix.lower() == ".apworld":
            from worlds.Files import APWorldContainer
            ap = APWorldContainer(str(path))
            ap.read()
            v = getattr(ap, "world_version", None)
            if v is not None:
                try:
                    return v.as_simple_string()
                except Exception:
                    return str(v)
        elif path.is_dir():
            arch = path / "archipelago.json"
            if arch.is_file():
                import json
                data = json.loads(arch.read_text(encoding="utf-8"))
                v = data.get("world_version") or data.get("version")
                if v is not None:
                    return str(v)
            # Try to find version via world's __init__? Fallback
            init = path / "__init__.py"
            if init.is_file():
                text = init.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r"world_version\s*=\s*['\"]([^'\"]+)['\"]", text)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None


def _parse_semver(v: str) -> Tuple[int, ...]:
    try:
        v = v.strip().lstrip("v").split("-")[0].split("+")[0]
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(re.match(r"(\d+)", p).group(1) if re.match(r"(\d+)", p) else 0))
            except Exception:
                parts.append(0)
        # Pad to 3
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])
    except Exception:
        return (0,)


# Versioned-instance registry: (game_lower, version_tuple) -> entry.
# Records which loaded world class belongs to which apworld version, so
# roll/generation hooks route each player to the right class. The game name
# itself is never changed: every version keeps the real game, sharing one
# datapackage built from subset-merged ID maps.
_VERSION_REGISTRY: Dict[Tuple[str, Tuple[int, ...]], Dict[str, Any]] = {}
_LOADED_ALIASES: Dict[str, Any] = {}


def _registry_key(game: str, version: str) -> Tuple[str, Tuple[int, ...]]:
    return (str(game).strip().lower(), _parse_semver(str(version)))


def record_versioned_class(game: str, version: str, cls: Any, path: Any, spec: str = "", src: Any = None) -> None:
    """Record that cls implements game at version (loaded from path for spec)."""
    try:
        _VERSION_REGISTRY[_registry_key(game, version)] = {
            "class": cls,
            "path": str(path),
            "version": str(version),
            "spec": str(spec),
            "src": str(src or path),
        }
        logger.info(f"APAPI updater: registered {game} version {version} -> {getattr(cls, '__name__', cls)} ({path})")
    except Exception:
        pass


def lookup_versioned_class(game: str, spec_or_version: str) -> Any | None:
    """Return the recorded class for (game, spec/version), or None."""
    try:
        entry = _VERSION_REGISTRY.get(_registry_key(game, spec_or_version))
        if entry is not None:
            return entry.get("class")
        # URL specs never match semver: try the version embedded in the URL.
        url_ver = _version_from_spec_url(spec_or_version)
        if url_ver:
            entry = _VERSION_REGISTRY.get(_registry_key(game, url_ver))
            if entry is not None:
                return entry.get("class")
        # Direct-URL specs never match semver: fall back to exact spec match.
        for (g, _v), other in _VERSION_REGISTRY.items():
            if g == str(game).strip().lower() and str(other.get("spec", "")) == str(spec_or_version):
                return other.get("class")
    except Exception:
        pass
    return None


def _registered_class_version(game: str) -> str | None:
    """Actual version string of the class currently in world_types[game]."""
    try:
        from worlds.AutoWorld import AutoWorldRegister
        cls = AutoWorldRegister.world_types.get(str(game))
        if cls is None:
            return None
        v = getattr(cls, "world_version", None)
        if v is not None:
            try:
                return v.as_simple_string()
            except Exception:
                return str(v)
    except Exception:
        pass
    return None


def _repack_versioned_apworld(src: pathlib.Path, alias: str, dest_dir: pathlib.Path) -> pathlib.Path:
    """Copy an apworld (or loose folder) renaming its top folder to alias.

    Lets two versions of one game import side-by-side as worlds.<alias>
    while both keep game == the real game name.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{alias}.apworld"
    if dest.is_file():
        return dest
    if src.is_dir():
        names = [p.relative_to(src).as_posix() for p in src.rglob("*") if p.is_file()]
        top = src.name
        reader = None
        from_dir = True
    else:
        reader = zipfile.ZipFile(src, "r")
        names = reader.namelist()
        tops = {n.split("/")[0] for n in names if "/" in n and n.split("/")[0]}
        if len(tops) != 1:
            if reader is not None:
                reader.close()
            raise Exception(f"Cannot version-load {src}: expected one top folder, found {sorted(tops)}")
        top = next(iter(tops))
        from_dir = False
    try:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
            for name in names:
                if not name or name.endswith("/"):
                    continue
                if reader is not None:
                    info = reader.getinfo(name)
                    data = reader.read(name)
                    stamp = info.date_time
                    attr = info.external_attr
                else:
                    data = (src / name).read_bytes()
                    import time as _time
                    stamp = _time.localtime()[:6]
                    attr = 0o644 << 16
                if from_dir:
                    # Directory sources list files relative to the folder
                    # itself: nest everything under the alias top folder.
                    new_name = alias + "/" + name
                elif name == top:
                    new_name = alias
                elif name.startswith(top + "/"):
                    new_name = alias + name[len(top):]
                else:
                    new_name = name
                ni = zipfile.ZipInfo(new_name, date_time=stamp)
                ni.compress_type = zipfile.ZIP_DEFLATED
                ni.external_attr = attr
                zout.writestr(ni, data)
    finally:
        if reader is not None:
            reader.close()
    return dest


def _load_versioned_apworld(game: str, spec: str, src: pathlib.Path, work_dir: pathlib.Path) -> Any | None:
    """Load src as a side-by-side versioned instance of game. Returns class or None."""
    import sys as _sys
    game = str(game).strip()
    stem = re.sub(r"\W", "_", src.stem if src.suffix.lower() == ".apworld" else src.name)
    safe_ver = re.sub(r"[^0-9A-Za-z_]", "_", str(spec).strip().lstrip("v")) or "custom"
    alias = f"{stem}_{safe_ver}"
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", alias):
        alias = f"apworld_{abs(hash((game, spec))) % 10 ** 8}"
    if alias in _LOADED_ALIASES:
        return _LOADED_ALIASES[alias]
    try:
        import worlds
        import bisect
        import zipimport
        import importlib
        dest = _repack_versioned_apworld(src, alias, work_dir)
        if not any(pathlib.Path(s.resolved_path) == dest for s in worlds.world_sources):
            source = worlds.WorldSource(str(dest), is_zip=True, relative=False)
            bisect.insort(worlds.world_sources, source)
        modname = f"worlds.{alias}"
        if modname in _sys.modules:
            try:
                del _sys.modules[modname]
            except Exception:
                pass
        if modname not in _sys.modules:
            importer = zipimport.zipimporter(str(dest))
            spec_obj = importer.find_spec(modname)
            if spec_obj is None or spec_obj.loader is None:
                raise Exception(f"No importable top folder {alias}/ inside {dest}")
            worlds.apworld_module_specs[modname] = spec_obj
            # The registrar rejects a second class for one game, so step the
            # current registration aside during the alias import and restore
            # it after; the new class object is captured from the registry.
            from worlds.AutoWorld import AutoWorldRegister as _Reg
            prev = _Reg.world_types.pop(game, None)
            try:
                importlib.import_module(modname)
            finally:
                new_cls = _Reg.world_types.get(game)
                if prev is not None:
                    _Reg.world_types[game] = prev
                else:
                    _Reg.world_types.pop(game, None)
            if new_cls is None or new_cls is prev:
                raise Exception(f"Alias import {modname} did not register a new class for {game!r}")
            cls = new_cls
            # Alias modules get a bogus settings_key derived from the alias
            # folder name, so host.yaml settings never resolve (settings is
            # None) and worlds misdiagnose it (e.g. TUNIC's duplicate-install
            # guard). Point the class at the real key and make sure the
            # settings cache can resolve it.
            try:
                orig_key = getattr(prev, "settings_key", None) if prev is not None else None
                if not orig_key:
                    if src.suffix.lower() == ".apworld":
                        with zipfile.ZipFile(src, "r") as _zf:
                            _tops = {n.split("/")[0] for n in _zf.namelist() if "/" in n and n.split("/")[0]}
                        orig_top = next(iter(_tops)) if len(_tops) == 1 else src.stem
                    else:
                        orig_top = src.name
                    orig_key = f"{re.sub(r'[^0-9A-Za-z_]', '_', orig_top).lower()}_options"
                cls.settings_key = orig_key
                try:
                    import settings as _settings_mod
                    _cache = getattr(_settings_mod, "_world_settings_name_cache", None)
                    if isinstance(_cache, dict) and orig_key not in _cache:
                        _cache[orig_key] = f"{cls.__module__}.{cls.__name__}"
                except Exception:
                    pass
            except Exception as exc:
                logger.debug(f"APAPI updater: settings_key fixup failed for {modname}: {exc}")
        else:
            from worlds.AutoWorld import AutoWorldRegister
            cls = AutoWorldRegister.world_types.get(game)
            if cls is None:
                raise Exception(f"Versioned apworld {dest} loaded but game {game!r} did not register")
        actual = (_get_version_from_path(dest)
                  or _version_from_spec_url(spec)
                  or str(spec))
        record_versioned_class(game, actual, cls, dest, spec, src=src)
        _LOADED_ALIASES[alias] = cls
        logger.info(f"APAPI updater: loaded {game} {actual} for spec {spec!r} as {modname}")
        return cls
    except Exception as exc:
        try:
            import traceback
            import worlds
            worlds.failed_world_loads[alias] = traceback.format_exc()
        except Exception:
            pass
        logger.warning(f"APAPI updater: failed to load versioned {game} {spec} from {src}: {exc}")
        return None


# Download consent: temporary apworlds are only fetched after asking (or an
# explicit accept_mode=auto). Decisions are cached per process so each
# (game, spec) is asked about at most once.
_CONSENT: Dict[Tuple[str, str], bool] = {}


class ConsentDeniedError(Exception):
    """Raised when a required temp-apworld download was denied."""
    pass


def _consent_key(game: str, spec: str) -> Tuple[str, str]:
    return (str(game).strip().lower(), str(spec).strip())


def _is_interactive() -> bool:
    try:
        import sys as _sys
        return bool(_sys.stdin.isatty()) if hasattr(_sys.stdin, "isatty") else False
    except Exception:
        return False


def _prompt_user(text: str) -> str | None:
    """Prompt on stdin. Returns None when input is unavailable (frozen/headless)."""
    try:
        return input(text)
    except (EOFError, OSError, RuntimeError, ValueError, KeyboardInterrupt):
        return None
    except Exception:
        return None


def _updater_accept_mode() -> str:
    try:
        from .host_config import get_apworld_updater_config
        mode = str(get_apworld_updater_config().get("accept_mode", "each")).lower()
        return mode if mode in ("each", "all", "auto") else "each"
    except Exception:
        return "each"


def _updater_ask_in_terminal() -> bool:
    try:
        from .host_config import get_apworld_updater_config
        return bool(get_apworld_updater_config().get("ask_in_terminal", True))
    except Exception:
        return True


def _spec_satisfiable_without_download(game: str, spec: str) -> bool:
    """True when the wanted version is already usable with no download."""
    try:
        if lookup_versioned_class(game, spec) is not None:
            return True
        want = _parse_semver(spec)
        for _ipath, iver in _find_installed_versions(str(game).strip()):
            try:
                if _parse_semver(iver) == want:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _direct_download_warning(game: str, spec: str) -> str | None:
    """Warn (and gate) non-index downloads: direct file fetches are riskier."""
    try:
        kind, _val = _parse_spec(str(spec))
    except Exception:
        return None
    if kind == "index":
        return None
    try:
        url = resolve_spec_to_url(str(game), str(spec)) or str(spec)
    except Exception:
        url = str(spec)
    return (f"WARNING: direct apworld download for {game} -> {spec}\n"
            f"  URL: {url}\n"
            f"  Direct file downloads can be dangerous (not from the index).")


def consent_to_download(game: str, spec: str) -> bool:
    """Decide (asking once) whether a temp apworld may be downloaded.

    No download is ever needed when the version is already usable: those
    return True without asking. Otherwise accept_mode=auto allows (with an
    interactive warning for non-index sources); without a terminal the
    answer is deny with guidance; with a terminal the user is asked.
    """
    key = _consent_key(game, spec)
    if key in _CONSENT:
        return _CONSENT[key]
    try:
        if _spec_satisfiable_without_download(game, spec):
            _CONSENT[key] = True
            return True
    except Exception:
        pass
    mode = _updater_accept_mode()
    ask = _updater_ask_in_terminal()
    interactive = _is_interactive()
    warning = _direct_download_warning(game, spec)
    if mode == "auto":
        if warning is not None and interactive and ask:
            print(f"\n {warning}")
            ans = _prompt_user(f" Allow direct download for {game} {spec}?\n [y/N]: ")
            allowed = ans is not None and ans.strip().lower() in ("y", "yes")
            _CONSENT[key] = allowed
            if not allowed:
                logger.info(f"APAPI updater: denied direct {game} {spec} (auto mode)")
            return allowed
        _CONSENT[key] = True
        return True
    if not interactive or not ask:
        logger.info(f"APAPI updater: download of {game} {spec} needs approval, "
                    f"but no terminal is available (set accept_mode=auto to allow, "
                    f"or pre-install the apworld). Denying.")
        _CONSENT[key] = False
        return False
    if warning is not None:
        print(f"\n {warning}")
    ans = _prompt_user(f" Allow downloading temp apworld for {game} -> {spec}?\n [y/N]: ")
    allowed = ans is not None and ans.strip().lower() in ("y", "yes")
    _CONSENT[key] = allowed
    if not allowed:
        logger.info(f"APAPI updater: denied download of {game} {spec}")
    return allowed


def precollect_consent(requests: List[Tuple[str, str, str]]) -> None:
    """Ask up front for every not-yet-decided download a generation needs.

    Input: [(player_name, game, spec)]. Raises with a clear message when a
    denied spec cannot be satisfied without downloading (generation could
    not proceed); specs satisfiable from installed/registered copies never
    prompt and never fail.
    """
    todo: List[Tuple[str, str, str]] = []
    for pname, game, spec in requests:
        key = _consent_key(game, spec)
        if key in _CONSENT:
            continue
        try:
            if _spec_satisfiable_without_download(game, spec):
                _CONSENT[key] = True
                logger.info(f"APAPI updater: using already-available {game} {spec} for {pname} (no download)")
                continue
        except Exception:
            pass
        if not any(r[1] == game and r[2] == spec for r in todo):
            todo.append((pname, game, spec))
    if not todo:
        return
    mode = _updater_accept_mode()
    ask = _updater_ask_in_terminal()
    interactive = _is_interactive()
    if mode == "auto":
        for pname, game, spec in todo:
            warning = _direct_download_warning(game, spec)
            if warning is not None and interactive and ask:
                print(f"\n {warning}")
                ans = _prompt_user(f" Allow direct download for {pname} {game} {spec}?\n [y/N]: ")
                allowed = ans is not None and ans.strip().lower() in ("y", "yes")
                _CONSENT[_consent_key(game, spec)] = allowed
                if not allowed:
                    logger.info(f"APAPI updater: denied direct {pname} {game} {spec} even in auto")
            else:
                _CONSENT[_consent_key(game, spec)] = True
        denied = [(p, g, s) for p, g, s in todo if not _CONSENT.get(_consent_key(g, s), False)]
        if denied:
            who = "; ".join(f"{p} wants {g} {s}" for p, g, s in denied)
            raise ConsentDeniedError(f"APAPI updater: download denied but required: {who}. "
                                     f"Set accept_mode=auto or pre-install the apworld to proceed.")
        return
    if not interactive or not ask:
        who = "; ".join(f"{p} wants {g} {s}" for p, g, s in todo)
        raise ConsentDeniedError(f"APAPI updater: temp apworld downloads require approval ({who}), "
                                 f"but no terminal is available. Set accept_mode=auto to allow, "
                                 f"or pre-install the apworlds.")
    if mode == "all":
        print("\n APAPI temp apworld downloads requested:")
        for pname, game, spec in todo:
            warning = _direct_download_warning(game, spec)
            print(f"  Player {pname} wants {game} -> {spec}")
            if warning is not None:
                print(f"  {warning}")
        ans = _prompt_user("Allow all temp apworld downloads?\n [y/N]: ")
        allowed = ans is not None and ans.strip().lower() in ("y", "yes", "all", "a")
        for _p, game, spec in todo:
            _CONSENT[_consent_key(game, spec)] = allowed
        if not allowed:
            who = "; ".join(f"{p} wants {g} {s}" for p, g, s in todo)
            raise ConsentDeniedError(f"APAPI updater: downloads denied but required: {who}.")
        return
    # each: per game, allow all versions / deny / pick individually.
    by_game: Dict[str, List[Tuple[str, str, str]]] = {}
    for pname, game, spec in todo:
        by_game.setdefault(game, []).append((pname, game, spec))
    for game, entries in by_game.items():
        print(f"\n APAPI temp apworld downloads for {game}:")
        for pname, _g, spec in entries:
            warning = _direct_download_warning(game, spec)
            print(f"  Player {pname} wants {spec}")
            if warning is not None:
                print(f"  {warning}")
        ans = _prompt_user(f" Allow all {len(entries)} download(s) for {game}?\n"
                           f" ([y]es / [n]o / [s]elect individually): ")
        choice = (ans or "").strip().lower()
        if choice in ("y", "yes", "all", "a"):
            for _p, g, s in entries:
                _CONSENT[_consent_key(g, s)] = True
        elif choice in ("s", "select"):
            for pname, g, s in entries:
                ans2 = _prompt_user(f"  Allow download for {pname} {g} {s}?\n  [y/N]: ")
                _CONSENT[_consent_key(g, s)] = ans2 is not None and ans2.strip().lower() in ("y", "yes")
        else:
            for _p, g, s in entries:
                _CONSENT[_consent_key(g, s)] = False
    denied = [(p, g, s) for p, g, s in todo if not _CONSENT.get(_consent_key(g, s), False)]
    if denied:
        who = "; ".join(f"{p} wants {g} {s}" for p, g, s in denied)
        raise ConsentDeniedError(f"APAPI updater: downloads denied but required: {who}. "
                                 f"Generation cannot proceed without these versions.")


def _scan_apworld_specs_from_yamls() -> List[Tuple[str, str, str]]:
    """Collect [(player_name, game, spec)] apworld_version_wanted requests.

    Reads player yaml files (top-level key or game-section key) from the
    settings player dir plus any CLI-overridden weights/player/meta paths,
    so up-front consent covers what Generate will actually read. Used both
    before MultiWorld creation and at Generate.main start for up-front
    download consent. Failures scan as empty (later stages re-collect).
    """
    out: List[Tuple[str, str, str]] = []

    def _collect_doc(doc: Any, fallback_name: str) -> None:
        try:
            if not isinstance(doc, dict):
                return
            game = str(doc.get("game", "")).strip()
            player_name = str(doc.get("name", "")).strip() or fallback_name
            if not game:
                return
            spec = None
            if "apworld_version_wanted" in doc:
                spec = str(doc["apworld_version_wanted"]).strip()
            else:
                game_opts = doc.get(game, {})
                if isinstance(game_opts, dict) and "apworld_version_wanted" in game_opts:
                    spec = str(game_opts["apworld_version_wanted"]).strip()
            if not spec:
                # Version implied by an earlier official-source load.
                try:
                    spec = _implied_spec(game, player_name) or None
                except Exception:
                    spec = None
            if not spec:
                return
            entry = (player_name, game, spec)
            if entry not in out:
                out.append(entry)
        except Exception:
            pass

    try:
        from worlds.APAPI.yaml_tools import resolve_player_files_dir, iter_player_yaml_files, read_yaml_documents_file
        seen: set = set()
        try:
            pdir = resolve_player_files_dir()
            if pdir and pdir.is_dir():
                seen.add(str(pdir))
                for yf in iter_player_yaml_files(pdir):
                    try:
                        for doc in read_yaml_documents_file(yf):
                            _collect_doc(doc, yf.stem)
                    except Exception:
                        continue
        except Exception:
            pass
        # CLI overrides Generate honors (--player_files_path, --weights_file_path,
        # --meta_file_path): peek at sys.argv before Generate parses it.
        try:
            import sys as _sys
            argv = list(getattr(_sys, "argv", []) or [])[1:]
            extra: List[str] = []
            i = 0
            while i < len(argv):
                arg = argv[i]
                val = None
                if arg.startswith("--player_files_path="):
                    val = ("dir", arg.split("=", 1)[1])
                elif arg.startswith("--weights_file_path="):
                    val = ("file", arg.split("=", 1)[1])
                elif arg.startswith("--meta_file_path="):
                    val = ("file", arg.split("=", 1)[1])
                elif arg in ("--player_files_path", "--weights_file_path", "--meta_file_path"):
                    if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                        kind = "dir" if arg == "--player_files_path" else "file"
                        val = (kind, argv[i + 1])
                        i += 1
                if val is not None:
                    extra.append(val)
                i += 1
            for kind, raw in extra:
                try:
                    if raw.startswith(("http://", "https://")):
                        continue
                    p = pathlib.Path(raw)
                    if not p.is_absolute():
                        try:
                            import os as _os
                            p = pathlib.Path(_os.getcwd()) / p
                        except Exception:
                            continue
                    key = str(p)
                    if key in seen:
                        continue
                    seen.add(key)
                    if kind == "dir" and p.is_dir():
                        for yf in iter_player_yaml_files(p):
                            try:
                                for doc in read_yaml_documents_file(yf):
                                    _collect_doc(doc, yf.stem)
                            except Exception:
                                continue
                    elif kind == "file" and p.is_file():
                        try:
                            for doc in read_yaml_documents_file(p):
                                _collect_doc(doc, p.stem)
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            pass
    except Exception:
        pass
    return out


def ensure_versioned_class(game: str, spec: str, work_dir: pathlib.Path | None = None) -> Any | None:
    """Return the world class for (game, spec), downloading/loading if needed.

    Reuses registry hits and already-installed matching versions before
    downloading. Returns None (with a warning logged) when unobtainable.
    """
    game_s = str(game).strip()
    spec_s = str(spec).strip()
    hit = lookup_versioned_class(game_s, spec_s)
    if hit is not None:
        return hit
    work = work_dir or (get_run_temp_dir() / f"ver_{re.sub(r'[^0-9A-Za-z_]', '_', game_s)}")
    try:
        work.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    # Reuse an already-installed copy with the wanted version.
    try:
        for ipath, iver in _find_installed_versions(game_s):
            try:
                if _parse_semver(iver) != _parse_semver(spec_s):
                    continue
                reg_v = _registered_class_version(game_s)
                if reg_v is not None and _parse_semver(reg_v) == _parse_semver(iver):
                    from worlds.AutoWorld import AutoWorldRegister
                    cls = AutoWorldRegister.world_types[game_s]
                    record_versioned_class(game_s, iver, cls, ipath, spec_s)
                    logger.info(f"APAPI updater: reusing installed {game_s} {iver} at {ipath}")
                    return cls
                cls = _load_versioned_apworld(game_s, spec_s, ipath, work)
                if cls is not None:
                    return cls
            except Exception:
                continue
    except Exception:
        pass
    # Download and side-load (only after asking, unless already decided).
    if not consent_to_download(game_s, spec_s):
        logger.warning(f"APAPI updater: download of {game_s} {spec_s} was not approved; cannot obtain it")
        return None
    dest = None
    try:
        dest = download_apworld_for_spec(game_s, spec_s, work)
    except Exception as exc:
        logger.warning(f"APAPI updater: could not resolve/download {game_s} {spec_s}: {exc}")
        dest = None
    if dest is not None and dest.is_file():
        return _load_versioned_apworld(game_s, spec_s, dest, work)
    # Last resort: official Archipelago source when it carries exactly the
    # requested version (supported per index).
    try:
        _cls, _ver = _ensure_official_apworld(game_s, spec_s, work)
        if _cls is not None:
            return _cls
    except Exception as exc:
        logger.debug(f"APAPI updater: official fallback failed for {game_s} {spec_s}: {exc}")
    logger.warning(f"APAPI updater: could not obtain {game_s} {spec_s} (download failed)")
    return None


def merge_version_maps(game: str, labeled: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Union item/location ID maps across versioned classes (subset semantics).

    Shared keys must map to the same ID in every version; additions or
    omissions are fine. True conflicts raise, naming the versions.
    """
    merged_items: Dict[str, int] = {}
    item_sources: Dict[str, str] = {}
    merged_locs: Dict[str, int] = {}
    loc_sources: Dict[str, str] = {}
    for label, cls in labeled.items():
        try:
            items = dict(getattr(cls, "item_name_to_id", {}) or {})
        except Exception:
            items = {}
        try:
            locs = dict(getattr(cls, "location_name_to_id", {}) or {})
        except Exception:
            locs = {}
        for name, nid in items.items():
            if name in merged_items and merged_items[name] != nid:
                raise Exception(
                    f"APAPI updater: {game} versions {item_sources[name]} and {label} "
                    f"conflict on item {name!r}: {merged_items[name]} vs {nid}. "
                    f"Use subset-compatible apworld versions (shared entries must keep the same IDs).")
            if name not in merged_items:
                merged_items[name] = nid
                item_sources[name] = label
        for name, nid in locs.items():
            if name in merged_locs and merged_locs[name] != nid:
                raise Exception(
                    f"APAPI updater: {game} versions {loc_sources[name]} and {label} "
                    f"conflict on location {name!r}: {merged_locs[name]} vs {nid}. "
                    f"Use subset-compatible apworld versions (shared entries must keep the same IDs).")
            if name not in merged_locs:
                merged_locs[name] = nid
                loc_sources[name] = label
    return merged_items, merged_locs


def apply_merged_maps(cls: Any, items: Dict[str, int], locs: Dict[str, int]) -> None:
    """Give one versioned class the merged ID maps (same formulas as class creation)."""
    try:
        item_groups: Dict[str, Any] = {}
        for other in (getattr(cls, "item_name_groups", {}) or {}).items():
            try:
                item_groups[other[0]] = set(other[1])
            except Exception:
                continue
        loc_groups: Dict[str, Any] = {}
        for other in (getattr(cls, "location_name_groups", {}) or {}).items():
            try:
                loc_groups[other[0]] = set(other[1])
            except Exception:
                continue
        cls.item_name_to_id = dict(items)
        cls.location_name_to_id = dict(locs)
        cls.item_id_to_name = {v: k for k, v in items.items()}
        cls.location_id_to_name = {v: k for k, v in locs.items()}
        cls.item_names = frozenset(items)
        cls.location_names = frozenset(locs)
        item_groups["Everything"] = cls.item_names
        cls.item_name_groups = item_groups
        loc_groups["Everywhere"] = cls.location_names
        cls.location_name_groups = loc_groups
        try:
            cls.all_item_and_group_names = frozenset(cls.item_names | set(item_groups))
        except Exception:
            pass
    except Exception as exc:
        raise Exception(f"APAPI updater: failed to apply merged maps to {getattr(cls, '__name__', cls)}: {exc}") from exc


def _cls_version_tuple(cls: Any) -> Tuple[int, ...]:
    try:
        v = getattr(cls, "world_version", None)
        if v is None:
            return (0,)
        try:
            return _parse_semver(v.as_simple_string())
        except Exception:
            pass
        if isinstance(v, (tuple, list)):
            return tuple(int(x) for x in list(v)[:3])
        return _parse_semver(str(v))
    except Exception:
        return (0,)


def _version_label(game: str, spec: str, cls: Any) -> str:
    try:
        for (g, _v), entry in _VERSION_REGISTRY.items():
            if g == str(game).strip().lower() and entry.get("class") is cls:
                return str(entry.get("version") or spec)
    except Exception:
        pass
    return str(spec)


def apply_version_routing(multiworld: Any, allowed: List[Tuple[int, str, str, str]] | None) -> Dict[int, Any]:
    """Ensure versioned classes, subset-merge maps, write one datapackage, record routes.

    Input: multiworld + [(pid, pname, game, spec)] (or None to derive from the
    pre-MultiWorld yaml scan). Returns {pid: world class}. Same game name and
    one datapackage throughout; true ID conflicts raise.
    """
    existing = getattr(multiworld, "_apapi_version_classes", None)
    if isinstance(existing, dict) and existing:
        return existing
    if allowed is None:
        allowed = []
        pending = getattr(multiworld, "_apapi_pending_specs", None) or {}
        names = getattr(multiworld, "player_name", {}) or {}
        pid_by_name: Dict[str, int] = {}
        for pid, pname in names.items():
            pid_by_name.setdefault(str(pname), pid)
        for pname, gs in pending.items():
            pid = pid_by_name.get(str(pname))
            if pid is None:
                continue
            game, spec = gs
            allowed.append((pid, str(pname), game, spec))
    if not allowed:
        return {}
    from worlds.AutoWorld import AutoWorldRegister, data_package_checksum
    import worlds
    try:
        missing_before = {str(game) for _p, _n, game, _s in (allowed or [])
                          if str(game) not in AutoWorldRegister.world_types}
    except Exception:
        missing_before = set()
    temp_dir = get_run_temp_dir()
    pid_classes: Dict[int, Any] = {}
    per_game: Dict[str, Dict[str, Any]] = {}
    sweep_stale_temp_apworlds()
    for pid, pname, game, spec in allowed:
        work = temp_dir / f"pid_{pid}_{re.sub(r'[^0-9A-Za-z_]', '_', str(game))}"
        cls = ensure_versioned_class(game, spec, work)
        if cls is None:
            raise Exception(
                f"APAPI updater: could not obtain {game} {spec} for {pname} (P{pid}). "
                f"Check the version exists and the download URL resolves.")
        label = _version_label(game, spec, cls)
        per_game.setdefault(game, {}).setdefault(label, cls)
        pid_classes[pid] = cls
        logger.info(f"APAPI updater: P{pid} {pname} -> {game} {label} "
                    f"({getattr(cls, '__module__', '?')}.{getattr(cls, '__name__', '?')})")
    for game, labeled in per_game.items():
        # Players without a spec ride the newest version (merge-checked below).
        canonical = max(labeled.values(), key=_cls_version_tuple)
        for pid in getattr(multiworld, "game", {}):
            if getattr(multiworld, "game", {}).get(pid) == game and pid not in pid_classes:
                pid_classes[pid] = canonical
                logger.info(f"APAPI updater: player {pid} has no version spec for {game}, using newest routed version")
        if len(labeled) == 1:
            AutoWorldRegister.world_types[game] = canonical
            merged = canonical.get_data_package_data()
        else:
            items, locs = merge_version_maps(game, labeled)
            ig: Dict[str, set] = {}
            lg: Dict[str, set] = {}
            for cls in labeled.values():
                for gname, members in (getattr(cls, "item_name_groups", {}) or {}).items():
                    if gname == "Everything":
                        continue
                    try:
                        ig.setdefault(gname, set()).update(members)
                    except Exception:
                        continue
                for gname, members in (getattr(cls, "location_name_groups", {}) or {}).items():
                    if gname == "Everywhere":
                        continue
                    try:
                        lg.setdefault(gname, set()).update(members)
                    except Exception:
                        continue
            for cls in labeled.values():
                apply_merged_maps(cls, items, locs)
                try:
                    for gname, members in ig.items():
                        cls.item_name_groups.setdefault(gname, set()).update(members)
                    for gname, members in lg.items():
                        cls.location_name_groups.setdefault(gname, set()).update(members)
                except Exception:
                    pass
            AutoWorldRegister.world_types[game] = canonical
            merged = {
                "item_name_groups": {k: sorted(v) for k, v in sorted(canonical.item_name_groups.items())},
                "item_name_to_id": dict(canonical.item_name_to_id),
                "location_name_groups": {k: sorted(v) for k, v in sorted(canonical.location_name_groups.items())},
                "location_name_to_id": dict(canonical.location_name_to_id),
            }
            merged["checksum"] = data_package_checksum(merged)
        worlds.network_data_package["games"][game] = merged
        logger.info(f"APAPI updater: {game} routing {len(labeled)} version(s) "
                    f"({', '.join(sorted(labeled))}) to {len([p for p in pid_classes])} player(s), "
                    f"datapackage {len(merged.get('item_name_to_id', {}))} items / "
                    f"{len(merged.get('location_name_to_id', {}))} locations")
    multiworld._apapi_version_classes = pid_classes  # type: ignore
    # Option schema union per game + version label per player, so the
    # set_options loops can mark version-absent options NotImplemented
    # instead of silently defaulting them (and report them below).
    try:
        unions: Dict[str, Any] = {}
        labels: Dict[int, str] = {}
        for game, labeled in per_game.items():
            keys: set = set()
            for cls in labeled.values():
                try:
                    keys.update(getattr(cls.options_dataclass, "type_hints", {}) or {})
                except Exception:
                    continue
            unions[game] = frozenset(keys)
        for pid, cls in pid_classes.items():
            game = getattr(multiworld, "game", {}).get(pid, "")
            for label, lcls in per_game.get(game, {}).items():
                if lcls is cls:
                    labels[pid] = label
                    break
        multiworld._apapi_option_union = unions  # type: ignore
        multiworld._apapi_version_labels = labels  # type: ignore
        for pid in sorted(pid_classes):
            game = getattr(multiworld, "game", {}).get(pid, "")
            union = unions.get(game, frozenset())
            cls = pid_classes[pid]
            try:
                schema = set(getattr(cls.options_dataclass, "type_hints", {}) or {})
            except Exception:
                schema = set()
            missing = sorted(set(union) - schema)
            if missing:
                logger.info(f"APAPI updater: P{pid} {game} {labels.get(pid, '?')} "
                            f"lacks options marked NotImplemented: {', '.join(missing)}")
    except Exception as exc:
        logger.debug(f"APAPI updater: option union failed: {exc}")
    # Offer to persist downloads for games with no installed copy: latest
    # downloaded version only, kept under its original apworld filename.
    try:
        from Utils import user_path
        import shutil
        import sys as _sys2
        import tempfile as _tempfile
        try:
            from .host_config import get_apworld_updater_config as _get_cfg2
            _ask = bool(_get_cfg2().get("ask_in_terminal", True))
        except Exception:
            _ask = True
        try:
            _is_term = _sys2.stdin.isatty() if hasattr(_sys2.stdin, "isatty") else False
        except Exception:
            _is_term = False
        try:
            _temp_root = pathlib.Path(_tempfile.gettempdir()) / "apapi_temp_apworlds"
        except Exception:
            _temp_root = None
        for game in sorted(per_game):
            try:
                if _find_installed_versions(game):
                    continue
            except Exception:
                pass
            candidates = []
            for (_g, _v), entry in list(_VERSION_REGISTRY.items()):
                if _g != str(game).strip().lower():
                    continue
                try:
                    src = pathlib.Path(str(entry.get("src", "")))
                except Exception:
                    continue
                if not src.is_file():
                    continue
                if _temp_root is not None:
                    try:
                        src.relative_to(_temp_root)
                    except Exception:
                        continue
                try:
                    key = _parse_semver(str(entry.get("version", "")))
                except Exception:
                    key = (0,)
                candidates.append((key, entry, src))
            if not candidates:
                continue
            candidates.sort(key=lambda t: t[0])
            _key, entry, src = candidates[-1]
            target = pathlib.Path(user_path("custom_worlds")) / src.name
            if target.is_file():
                try:
                    if target.read_bytes() == src.read_bytes():
                        logger.info(f"APAPI updater: {game} {entry.get('version')} already saved at {target}")
                        continue
                except Exception:
                    pass
                if _is_term and _ask:
                    ans = (_prompt_user(f" {target.name} already exists in custom_worlds with different content. "
                                        f"Overwrite with downloaded {game} {entry.get('version')}?\n [y/N]: ") or "")
                    if ans.strip().lower() not in ("y", "yes"):
                        logger.info(f"APAPI updater: keeping existing {target.name}")
                        continue
                else:
                    logger.info(f"APAPI updater: {target.name} already exists with different content; keeping it")
                    continue
            save = False
            if _is_term and _ask:
                ans = (_prompt_user(f" {game} is not installed. Save downloaded {src.name} "
                                    f"({entry.get('version')}) to custom_worlds permanently?\n [y/N]: ") or "")
                save = ans.strip().lower() in ("y", "yes")
            else:
                save = True
            if save:
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, target)
                    print(f"  Saved {game} {entry.get('version')} to {target}")
                    logger.info(f"APAPI updater: saved {game} {entry.get('version')} to custom_worlds")
                except Exception as exc:
                    logger.debug(f"APAPI updater: save failed for {game}: {exc}")
    except Exception as exc:
        logger.debug(f"APAPI updater: save prompt failed: {exc}")
    print(f" APAPI: version routing complete ({len(pid_classes)} player(s) across {len(per_game)} game(s))")
    return pid_classes


def _set_options_wrapper(next_callable: Any, self: Any, args: Any) -> Any:
    """Route each player to their versioned world class at creation (same game name)."""
    pending = getattr(self, "_apapi_pending_specs", None)
    routed = getattr(self, "_apapi_version_classes", None)
    if not pending and not routed:
        return next_callable(self, args)
    try:
        wanted = routed or apply_version_routing(self, None)
    except Exception as exc:
        logger.error(f"APAPI updater: version routing failed: {exc}", exc_info=True)
        raise
    if not wanted:
        return next_callable(self, args)
    from worlds import AutoWorld
    reg = AutoWorld.AutoWorldRegister.world_types
    try:
        from .options_api import build_player_options
    except Exception:
        build_player_options = None  # type: ignore
    unions = getattr(self, "_apapi_option_union", None) or {}
    labels = getattr(self, "_apapi_version_labels", None) or {}
    saved: Dict[str, Any] = {}
    try:
        for player in self.player_ids:
            game = self.game[player]
            cls = wanted.get(player) or reg.get(game)
            if cls is None:
                raise Exception(f"No world class for game {game!r} (player {player})")
            if game not in saved:
                saved[game] = reg.get(game)
            self.worlds[player] = cls(self, player)
            if build_player_options is not None:
                self.worlds[player].options = build_player_options(
                    cls, args, player, option_union=unions.get(game),
                    game=game, version=labels.get(player, ""))
            else:
                odc = cls.options_dataclass
                hints = getattr(odc, "type_hints", {}) or {}
                kwargs: Dict[str, Any] = {}
                for key in hints:
                    vals = getattr(args, key, None)
                    if vals is None:
                        continue
                    try:
                        kwargs[key] = vals[player]
                    except Exception:
                        continue
                self.worlds[player].options = odc(**kwargs)
    except Exception:
        try:
            for game, cls in saved.items():
                if cls is None:
                    reg.pop(game, None)
                else:
                    reg[game] = cls
        except Exception:
            pass
        raise
    try:
        for game, cls in saved.items():
            if cls is None:
                reg.pop(game, None)
            else:
                reg[game] = cls
    except Exception:
        pass
    return None


def _version_from_spec_url(spec: str) -> str | None:
    """Extract a version from a release tag/download URL (e.g. .../tag/4.2.1).

    Lets URL specs share registry keys with bare version specs even when the
    apworld itself carries no readable manifest (pre-0.6.0 apworld format).
    """
    try:
        s = str(spec).strip()
        m = re.search(r"/releases/tag/([^/?#]+)", s)
        if m:
            v = m.group(1).strip()
            if v:
                return v
        m = re.search(r"/releases/download/([^/?#]+)/", s)
        if m:
            v = m.group(1).strip()
            if v:
                return v
    except Exception:
        pass
    return None


def _find_installed_versions(game: str) -> List[Tuple[pathlib.Path, str]]:
    results: List[Tuple[pathlib.Path, str]] = []
    try:
        import worlds
        from Utils import user_path, local_path
        candidates: List[pathlib.Path] = []
        # Check worlds folder (loose folders)
        try:
            worlds_root = pathlib.Path(local_path("worlds"))
            if worlds_root.is_dir():
                for child in worlds_root.iterdir():
                    if child.is_dir() and (child / "archipelago.json").is_file():
                        # Check if this folder's game matches
                        try:
                            import json
                            data = json.loads((child / "archipelago.json").read_text(encoding="utf-8"))
                            if str(data.get("game", "")).strip().lower() == game.strip().lower():
                                v = _get_version_from_path(child)
                                if v:
                                    results.append((child, v))
                        except Exception:
                            continue
        except Exception:
            pass
        # Check custom_worlds for .apworld files
        try:
            folder = getattr(worlds, "user_folder", None)
            if not folder:
                folder = user_path("custom_worlds")
            base = pathlib.Path(folder)
            if base.is_dir():
                for p in base.iterdir():
                    if p.is_file() and p.suffix.lower() == ".apworld":
                        try:
                            from worlds.Files import APWorldContainer
                            ap = APWorldContainer(str(p))
                            ap.read()
                            g = ap.game
                            if g and str(g).strip().lower() == game.strip().lower():
                                v = _get_version_from_path(p)
                                if v:
                                    results.append((p, v))
                        except Exception:
                            continue
        except Exception:
            pass
    except Exception:
        pass
    return results


def _get_index_url() -> str:
    try:
        from .host_config import get_apworld_updater_config
        cfg = get_apworld_updater_config()
        return str(cfg.get("index_url", "https://raw.githubusercontent.com/dowlle/Archipelago-index/main/index.json"))
    except Exception:
        return "https://raw.githubusercontent.com/dowlle/Archipelago-index/main/index.json"


def _fetch_index(index_url: str | None = None) -> Dict[str, Any]:
    """Legacy single-JSON index fetch (custom .json URLs only).

    Repo URLs are served by the TOML client instead; anything that is not
    JSON returns {} quietly (debug, not warning) so a misconfigured URL
    cannot spam the log on every resolve.
    """
    import json
    import urllib.request
    url = index_url or _get_index_url()
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = resp.read().decode("utf-8")
            try:
                return json.loads(data)
            except Exception:
                if data.lstrip()[:1] in ("{", "["):
                    raise
                logger.debug(f"APAPI updater: index at {url} is not JSON; skipping legacy fetch")
                return {}
    except Exception as exc:
        logger.warning(f"APAPI updater: failed to fetch index {url}: {exc}")
        return {}


_TOML_TREE_CACHE: Dict[str, Any] = {}
_TOML_GAME_CACHE: Dict[str, Any] = {}


_STALE_INDEX_URLS = frozenset({
    "https://raw.githubusercontent.com/dowlle/Archipelago-index/main/index.json",
})


def _index_repo_parts() -> Any:
    """(owner, repo, branch) for TOML index lookups, or None for JSON index URLs."""
    try:
        url = (_get_index_url() or "").strip()
        if url.lower().endswith(".json") and url not in _STALE_INDEX_URLS:
            return None
        if not url or url in _STALE_INDEX_URLS:
            return ("dowlle", "Archipelago-index", "main")
        m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
        if m:
            return (m.group(1), m.group(2), "main")
    except Exception:
        pass
    return None


def _index_repos() -> List[Tuple[str, str, str]]:
    """Index repos to consult: configured repo, then the archived upstream.

    The default config points at dowlle's downstream fork; mooinglemur's
    archived upstream is consulted as fallback since entries may exist in
    only one of them.
    """
    repos: List[Tuple[str, str, str]] = []
    try:
        parts = _index_repo_parts()
        if parts is not None:
            repos.append(parts)
    except Exception:
        pass
    fallback = ("mooinglemur", "Archipelago-index", "main")
    if fallback not in repos:
        repos.append(fallback)
    return repos


def _index_toml_files() -> Dict[str, List[Any]]:
    """Normalized stem -> [(owner, repo, branch, path)] (cached per process)."""
    global _TOML_TREE_CACHE
    try:
        if "files" in _TOML_TREE_CACHE:
            return _TOML_TREE_CACHE["files"]
        import json
        import urllib.request
        files: Dict[str, List[Any]] = {}
        for owner, repo, branch in _index_repos():
            try:
                api = (f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}"
                       f"?recursive=1")
                req = urllib.request.Request(api, headers={"User-Agent": "APAPI-updater",
                                                           "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    tree = json.loads(resp.read().decode("utf-8"))
                for node in tree.get("tree", []):
                    try:
                        path = node.get("path", "")
                        if not path.startswith("index/") or not path.endswith(".toml"):
                            continue
                        stem = path[len("index/"):-len(".toml")]
                        norm = re.sub(r"[^0-9a-z]", "", stem.lower())
                        if norm:
                            files.setdefault(norm, []).append((owner, repo, branch, path))
                    except Exception:
                        continue
            except Exception as exc:
                logger.debug(f"APAPI updater: index tree listing failed for {owner}/{repo}: {exc}")
                continue
        _TOML_TREE_CACHE["files"] = files
        return files
    except Exception as exc:
        logger.debug(f"APAPI updater: index tree listing failed: {exc}")
        return {}


def _fetch_game_toml(game: str) -> Any:
    """Parsed per-game TOML + repo parts, name-verified (cached per process).

    Returns (toml_dict, (owner, repo, branch)) or (None, None). Entries whose
    TOML `name` contradicts the requested game are skipped, per the index
    filename rule (stem is the apworld name, game name lives inside).
    """
    try:
        key = str(game).strip().lower()
        if key in _TOML_GAME_CACHE:
            return _TOML_GAME_CACHE[key]
        norm = re.sub(r"[^0-9a-z]", "", key)
        files = _index_toml_files()
        candidates: List[Any] = list(files.get(norm, []))
        for cand in (f"index/{key}.toml", f"index/{str(game).strip()}.toml"):
            for owner, repo, branch in _index_repos():
                entry = (owner, repo, branch, cand)
                if entry not in candidates:
                    candidates.append(entry)
        import urllib.request
        try:
            import tomllib
        except Exception:
            logger.debug("APAPI updater: tomllib unavailable, cannot parse index TOML")
            _TOML_GAME_CACHE[key] = (None, None)
            return (None, None)
        for owner, repo, branch, path in candidates:
            try:
                raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
                req = urllib.request.Request(raw, headers={"User-Agent": "APAPI-updater"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    text = resp.read().decode("utf-8", errors="replace")
                data = tomllib.loads(text)
                if not isinstance(data, dict):
                    continue
                declared = data.get("name")
                if isinstance(declared, str) and declared.strip() \
                        and declared.strip().lower() != key:
                    logger.debug(f"APAPI updater: {path} declares game {declared!r}, "
                                 f"not {game!r}; skipping")
                    continue
                result = (data, (owner, repo, branch))
                _TOML_GAME_CACHE[key] = result
                return result
            except Exception:
                continue
        _TOML_GAME_CACHE[key] = (None, None)
        return (None, None)
    except Exception as exc:
        logger.debug(f"APAPI updater: game TOML fetch failed for {game}: {exc}")
        return (None, None)


def _toml_versions(toml: Dict[str, Any], repo_parts: Any = None) -> Dict[str, str]:
    """version -> download url from a game TOML ([versions] + default_url).

    Supports url/download_url/browser_download_url/apworld_url entries and
    `local` entries (resolved against the index repo's apworlds/ dir).
    """
    out: Dict[str, str] = {}
    try:
        if not isinstance(toml, dict):
            return out
        versions = toml.get("versions")
        if not isinstance(versions, dict):
            return out
        default_url = toml.get("default_url")
        if not isinstance(default_url, str):
            default_url = None
        raw_base = None
        try:
            if repo_parts is not None:
                _o, _r, _b = repo_parts
                raw_base = f"https://raw.githubusercontent.com/{_o}/{_r}/{_b}"
        except Exception:
            raw_base = None
        for ver, entry in versions.items():
            ver = str(ver)
            url = None
            if isinstance(entry, dict):
                for k in ("url", "download_url", "browser_download_url", "apworld_url"):
                    if isinstance(entry.get(k), str) and entry[k]:
                        url = entry[k]
                        break
                if url is None and raw_base is not None:
                    local = entry.get("local")
                    if isinstance(local, str) and local:
                        url = raw_base + "/" + local.lstrip("/").replace("../", "")
            elif isinstance(entry, str) and entry:
                url = entry
            if url is None and default_url:
                template = default_url
                v = ver
                # Avoid doubling a literal v (template "v{{version}}" + "v1.0").
                if "v{{version}}" in template and v.lower().startswith("v"):
                    v = v[1:]
                url = template.replace("{{version}}", v)
            if url:
                out[ver] = url
    except Exception as exc:
        logger.debug(f"APAPI updater: TOML version parse failed: {exc}")
    return out


_OFFICIAL_TREE_CACHE: Dict[str, Any] = {}
_IMPLIED_SPECS: Dict[Tuple[str, str], str] = {}


def _record_implied_spec(game: str, player_name: str, version: str) -> None:
    """Remember a version for a (game, player) that has no explicit spec."""
    try:
        _IMPLIED_SPECS[(str(game).strip().lower(), str(player_name).strip())] = str(version)
    except Exception:
        pass


def _implied_spec(game: str, player_name: str) -> str | None:
    try:
        return _IMPLIED_SPECS.get((str(game).strip().lower(), str(player_name).strip()))
    except Exception:
        return None


def _official_world_info(game: str) -> Any:
    """(folder, manifest) for game in official Archipelago source, or (None, None).

    Only when the index TOML marks the game supported. Manifest (with
    world_version) is required, and core min/max bounds are enforced.
    """
    try:
        toml, _parts = _fetch_game_toml(game)
        if not isinstance(toml, dict) or toml.get("supported") is not True:
            return (None, None)
        import json
        import urllib.request
        owner, repo, branch = ("ArchipelagoMW", "Archipelago", "main")
        cache_key = f"{owner}/{repo}/{branch}/worlds"
        if cache_key not in _OFFICIAL_TREE_CACHE:
            api = (f"https://api.github.com/repos/{owner}/{repo}/contents/worlds?ref={branch}")
            req = urllib.request.Request(api, headers={"User-Agent": "APAPI-updater",
                                                       "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                entries = json.loads(resp.read().decode("utf-8"))
            folders = sorted({e.get("name", "") for e in entries if isinstance(e, dict) and e.get("type") == "dir"})
            _OFFICIAL_TREE_CACHE[cache_key] = folders
        folders = _OFFICIAL_TREE_CACHE.get(cache_key) or []
        want = re.sub(r"[^0-9a-z]", "", str(game).strip().lower())
        folder = None
        if want in [f.lower() for f in folders]:
            folder = next(f for f in folders if f.lower() == want)
        else:
            for f in sorted(folders):
                if re.sub(r"[^0-9a-z]", "", f.lower()) == want:
                    folder = f
                    break
        if folder is None:
            logger.debug(f"APAPI updater: no official worlds/ folder for {game}")
            return (None, None)
        raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/worlds/{folder}/archipelago.json"
        req = urllib.request.Request(raw, headers={"User-Agent": "APAPI-updater"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            manifest = json.loads(resp.read().decode("utf-8", errors="replace"))
        if not isinstance(manifest, dict) or not manifest.get("world_version"):
            logger.debug(f"APAPI updater: official {game} manifest lacks world_version")
            return (None, None)
        try:
            from Utils import version_tuple as _core_version
            for bound_key, cmp in (("minimum_ap_version", "min"), ("maximum_ap_version", "max")):
                bound = manifest.get(bound_key)
                if not bound:
                    continue
                try:
                    from Utils import tuplize_version as _tuplize
                    bver = _tuplize(str(bound))
                except Exception:
                    continue
                if cmp == "min" and tuple(_core_version) < tuple(bver):
                    logger.info(f"APAPI updater: official {game} needs core {bound}, have core; skipping")
                    return (None, None)
                if cmp == "max" and tuple(_core_version) > tuple(bver):
                    logger.info(f"APAPI updater: official {game} caps core at {bound}; skipping")
                    return (None, None)
        except Exception:
            pass
        return (folder, manifest)
    except Exception as exc:
        logger.debug(f"APAPI updater: official info failed for {game}: {exc}")
        return (None, None)


def _fetch_official_tree(game: str, folder: str, work_dir: pathlib.Path,
                         branch: str = "main") -> pathlib.Path | None:
    """Download official worlds/<folder>/ into staging. Returns staging dir or None."""
    import urllib.request
    owner, repo = "ArchipelagoMW", "Archipelago"
    staging = work_dir / f"official_{re.sub(r'[^0-9A-Za-z_]', '_', str(game))}"
    try:
        staging.mkdir(parents=True, exist_ok=True)

        def _walk(remote_dir: str, local_dir: pathlib.Path) -> bool:
            api = (f"https://api.github.com/repos/{owner}/{repo}/contents/{remote_dir}?ref={branch}")
            req = urllib.request.Request(api, headers={"User-Agent": "APAPI-updater",
                                                       "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                import json
                entries = json.loads(resp.read().decode("utf-8"))
            ok = True
            for entry in entries:
                try:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("type") == "dir":
                        sub = local_dir / entry.get("name", "")
                        sub.mkdir(parents=True, exist_ok=True)
                        if not _walk(entry.get("path", ""), sub):
                            ok = False
                    elif entry.get("type") == "file":
                        raw = (f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/"
                               f"{entry.get('path', '')}")
                        req2 = urllib.request.Request(raw, headers={"User-Agent": "APAPI-updater"})
                        with urllib.request.urlopen(req2, timeout=60) as resp2:
                            (local_dir / entry.get("name", "")).write_bytes(resp2.read())
                    else:
                        continue
                except Exception as exc:
                    logger.debug(f"APAPI updater: official fetch failed for {entry}: {exc}")
                    ok = False
            return ok

        target = staging / folder
        target.mkdir(parents=True, exist_ok=True)
        if not _walk(f"worlds/{folder}", target):
            logger.warning(f"APAPI updater: official fetch incomplete for {game}; skipping")
            return None
        return staging
    except Exception as exc:
        logger.debug(f"APAPI updater: official tree fetch failed for {game}: {exc}")
        return None


def _ensure_official_apworld(game: str, version_hint: str | None,
                             work_dir: pathlib.Path | None = None) -> Any:
    """Load the official-source world for game. Returns (cls, version) or (None, None).

    Only when the index marks the game supported. An explicit numeric hint
    must semver-match the official manifest version; otherwise it is only
    used for spec-less (missing-game) flows. Consent applies normally.
    """
    try:
        game_s = str(game).strip()
        folder, manifest = _official_world_info(game_s)
        if folder is None or manifest is None:
            return (None, None)
        version = str(manifest.get("world_version", "")).strip()
        if not version:
            return (None, None)
        if version_hint:
            try:
                if _parse_semver(version_hint) != _parse_semver(version):
                    logger.info(f"APAPI updater: official {game_s} is {version}, "
                                f"not requested {version_hint}; skipping")
                    return (None, None)
            except Exception:
                pass
        if not consent_to_download(game_s, version):
            logger.info(f"APAPI updater: official {game_s} {version} download not approved")
            return (None, None)
        work = work_dir or (get_run_temp_dir() / f"official_{re.sub(r'[^0-9A-Za-z_]', '_', game_s)}")
        try:
            work.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        staging = _fetch_official_tree(game_s, folder, work)
        if staging is None:
            return (None, None)
        cls = _load_versioned_apworld(game_s, version, staging / folder, work)
        if cls is None:
            return (None, None)
        logger.info(f"APAPI updater: using official Archipelago {game_s} {version} "
                    f"(supported per index)")
        return (cls, version)
    except Exception as exc:
        logger.debug(f"APAPI updater: official ensure failed for {game}: {exc}")
        return (None, None)


def _resolve_latest_from_index(game: str) -> str | None:
    """Best-effort latest version string for game from the apworld index."""
    # Repo TOML layout first (current index format).
    try:
        toml, parts = _fetch_game_toml(game)
        versions = _toml_versions(toml or {}, parts)
        if versions:
            cands = sorted(versions.keys(), key=_parse_semver)
            if cands:
                return cands[-1]
    except Exception as exc:
        logger.debug(f"APAPI updater: TOML latest resolve failed for {game}: {exc}")
    try:
        index_data = _fetch_index()
        if not index_data:
            return None
        games = index_data.get("games", index_data)
        if not isinstance(games, dict):
            return None
        entry = None
        for key, value in games.items():
            try:
                if str(key).strip().lower() == str(game).strip().lower():
                    entry = value
                    break
            except Exception:
                continue
        if entry is None:
            return None
        versions = None
        if isinstance(entry, dict):
            versions = entry.get("versions", entry.get("releases", None))
        elif isinstance(entry, list):
            versions = entry
        candidates: List[str] = []
        if isinstance(versions, dict):
            candidates = [str(k) for k in versions.keys() if re.search(r"\d", str(k))]
        elif isinstance(versions, list):
            for v in versions:
                if isinstance(v, dict) and v.get("version"):
                    candidates.append(str(v["version"]))
                elif isinstance(v, str) and re.search(r"\d", v):
                    candidates.append(v)
        if not candidates:
            return None
        candidates.sort(key=_parse_semver)
        return candidates[-1]
    except Exception as exc:
        logger.debug(f"APAPI updater: latest-index resolve failed for {game}: {exc}")
        return None


def _install_missing_from_index_enabled() -> bool:
    try:
        from .host_config import get_apworld_updater_config
        return bool(get_apworld_updater_config().get("install_missing_from_index", False))
    except Exception:
        return False


def _resolve_index_spec(game: str, spec: str, index_data: Dict[str, Any] | None = None) -> str | None:
    # Repo TOML layout first (current index format): exact version, plus
    # v-prefixed variants in both directions.
    try:
        toml, parts = _fetch_game_toml(game)
        versions = _toml_versions(toml or {}, parts)
        if versions:
            for cand in (spec, spec.lstrip("v"), f"v{spec}"):
                if cand in versions:
                    return versions[cand]
    except Exception as exc:
        logger.debug(f"APAPI updater: TOML resolve failed for {game} {spec}: {exc}")
    if index_data is None:
        index_data = _fetch_index()
    # Index format is not fully documented, try common patterns
    # Try game -> versions dict
    try:
        games = index_data.get("games", index_data)
        if isinstance(games, dict) and game in games:
            entry = games[game]
            if isinstance(entry, dict):
                versions = entry.get("versions", entry.get("releases", {}))
                if isinstance(versions, dict) and spec in versions:
                    v = versions[spec]
                    if isinstance(v, dict):
                        for k in ("apworld_url", "download_url", "url", "browser_download_url"):
                            if k in v and isinstance(v[k], str):
                                return v[k]
                    elif isinstance(v, str):
                        return v
                # Try list
                if isinstance(entry, list):
                    for v in entry:
                        if isinstance(v, dict) and v.get("version") == spec:
                            for k in ("apworld_url", "download_url", "url"):
                                if k in v:
                                    return v[k]
        # Fallback: try top-level
        if spec in index_data and isinstance(index_data[spec], str):
            return index_data[spec]
    except Exception as exc:
        logger.debug(f"APAPI updater: index resolve failed for {game} {spec}: {exc}")
    return None


def _download_to_temp(url: str, dest_dir: pathlib.Path | None = None) -> pathlib.Path:
    import urllib.request
    if dest_dir is None:
        dest_dir = pathlib.Path(tempfile.gettempdir()) / "apapi_temp_apworlds"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Determine filename from URL
    fname = url.split("/")[-1].split("?")[0]
    if not fname.lower().endswith(".apworld"):
        fname = fname + ".apworld" if fname else "temp.apworld"
    dest = dest_dir / fname
    # Avoid overwrite collisions
    counter = 1
    base = dest
    while dest.exists():
        dest = base.parent / f"{base.stem}_{counter}{base.suffix}"
        counter += 1
    logger.info(f"APAPI updater: downloading {url} -> {dest}")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp, open(dest, "wb") as out:
            shutil.copyfileobj(resp, out)
    except Exception as exc:
        raise Exception(f"Failed to download {url}: {exc}") from exc
    if not zipfile.is_zipfile(dest):
        # Might be a github release page redirect or html
        try:
            text = dest.read_text(encoding="utf-8", errors="ignore")[:500]
            if "<html" in text.lower():
                raise Exception(f"Downloaded file from {url} appears to be HTML, not an apworld")
        except Exception:
            pass
        raise Exception(f"Downloaded file from {url} is not a valid apworld zip")
    return dest


def _resolve_github_spec(spec: str) -> str | None:
    spec = spec.strip()
    # Remove github: prefix
    if spec.startswith("github:"):
        spec = spec[len("github:"):].strip()
    # Handle user/repo@branch or user/repo
    if "@" in spec:
        repo, branch = spec.split("@", 1)
        repo = repo.strip().rstrip("/")
        branch = branch.strip()
        # Try raw apworld from repo
        # Guess apworld name from repo
        # We need to try to find apworld via GitHub API or raw
        # For now, try https://raw.githubusercontent.com/{repo}/{branch}/<game>.apworld or generic
        # Actually, the spec for github main should download the apworld from the repo's releases or raw
        # We will try to use GitHub API to get latest release
        return None
    # Handle full github URL
    if "github.com" in spec:
        # e.g. https://github.com/user/repo or https://github.com/user/repo/releases/tag/v1.0
        # For release tag, try API
        m = re.match(r"https://github\.com/([^/]+)/([^/]+)/releases/tag/([^/]+)", spec)
        if m:
            user, repo, tag = m.groups()
            api_url = f"https://api.github.com/repos/{user}/{repo}/releases/tags/{tag}"
            try:
                import json, urllib.request
                with urllib.request.urlopen(api_url, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    assets = data.get("assets", [])
                    for asset in assets:
                        name = asset.get("name", "")
                        if name.lower().endswith(".apworld"):
                            return asset.get("browser_download_url")
                    # Fallback to zipball
                    return data.get("zipball_url")
            except Exception as exc:
                logger.warning(f"APAPI updater: failed to resolve github release {spec}: {exc}")
                return None
        # For direct repo, try to get latest release
        m2 = re.match(r"https://github\.com/([^/]+)/([^/]+)/?$", spec)
        if m2:
            user, repo = m2.groups()
            api_url = f"https://api.github.com/repos/{user}/{repo}/releases/latest"
            try:
                import json, urllib.request
                with urllib.request.urlopen(api_url, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    assets = data.get("assets", [])
                    for asset in assets:
                        if asset.get("name", "").lower().endswith(".apworld"):
                            return asset.get("browser_download_url")
            except Exception as exc:
                logger.debug(f"APAPI updater: failed to resolve github repo {spec}: {exc}")
                return None
    return None


def resolve_spec_to_url(game: str, spec: str) -> str | None:
    kind, val = _parse_spec(spec)
    if kind == "direct":
        return val
    if kind == "release":
        # Try to resolve release link to direct apworld url
        resolved = _resolve_github_spec(val)
        return resolved or val
    if kind == "github":
        resolved = _resolve_github_spec(val)
        return resolved
    if kind == "index":
        return _resolve_index_spec(game, val)
    return None


def download_apworld_for_spec(game: str, spec: str, temp_dir: pathlib.Path | None = None) -> pathlib.Path | None:
    url = resolve_spec_to_url(game, spec)
    if not url:
        logger.warning(f"APAPI updater: could not resolve {game} -> {spec} to URL")
        return None
    try:
        return _download_to_temp(url, temp_dir)
    except Exception as exc:
        logger.warning(f"APAPI updater: download failed for {game} {spec} ({url}): {exc}")
        return None


def get_temp_apworld_dir() -> pathlib.Path:
    d = pathlib.Path(tempfile.gettempdir()) / "apapi_temp_apworlds"
    d.mkdir(parents=True, exist_ok=True)
    return d


_RUN_DIR: pathlib.Path | None = None
STALE_GRACE_SECONDS = 3600


def get_run_temp_dir() -> pathlib.Path:
    """Per-process run dir for temp apworlds (created once)."""
    global _RUN_DIR
    if _RUN_DIR is None:
        import time as _time
        _RUN_DIR = get_temp_apworld_dir() / f"run_{os.getpid()}_{int(_time.time())}"
        _RUN_DIR.mkdir(parents=True, exist_ok=True)
    return _RUN_DIR


def _pid_alive(pid: Any) -> bool:
    """Best-effort process-liveness check. Unknown -> True (never delete)."""
    try:
        pid = int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            # 87 (invalid parameter) means no such process.
            return kernel32.GetLastError() != 87
        except Exception:
            pass
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        import errno
        if exc.errno == errno.ESRCH:
            return False
        if exc.errno in (errno.EPERM, errno.EACCES):
            return True
        if getattr(exc, "winerror", None) == 87:
            return False
        return True
    except Exception:
        return True


def _remove_temp_entry(path: pathlib.Path) -> None:
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def sweep_stale_temp_apworlds(grace_seconds: int = STALE_GRACE_SECONDS) -> None:
    """Delete orphaned temp apworlds: previous crashes plus old shared layout.

    Keeps this run's dir, live runs' dirs, and anything younger than the
    grace period (shields concurrent runs, including older APAPI layouts).
    Idempotent; safe to call at generation start and anywhere temp use begins.
    """
    try:
        import time as _time
        base = get_temp_apworld_dir()
        mine = get_run_temp_dir()
        now = _time.time()
        try:
            children = list(base.iterdir())
        except Exception:
            return
        for child in children:
            try:
                if child == mine:
                    continue
                try:
                    age = now - child.stat().st_mtime
                except Exception:
                    continue
                name = child.name
                if name.startswith("run_"):
                    try:
                        pid = int(name.split("_")[1])
                    except Exception:
                        pid = None
                    if pid is not None and _pid_alive(pid):
                        continue
                    if age < grace_seconds:
                        continue
                else:
                    # Legacy shared layout (ver_*/pid_*/pre_*/roll_*/loose files).
                    if age < grace_seconds:
                        continue
                _remove_temp_entry(child)
                logger.info(f"APAPI updater: swept stale temp entry {child}")
            except Exception:
                continue
    except Exception:
        pass


def cleanup_temp_apworlds() -> None:
    """Best-effort removal of this run's temp dir (atexit after generation)."""
    try:
        target = _RUN_DIR
        if target is not None and target.is_dir():
            _remove_temp_entry(target)
    except Exception:
        pass


try:
    from .injection import inject_option
    inject_option("apworld_version_wanted", ApworldVersionWanted, games=None, group_name="APWorld Updater")
except Exception:
    try:
        from .options_api import register_global_option
        register_global_option("apworld_version_wanted", ApworldVersionWanted, group_name="APWorld Updater")
    except Exception:
        pass


try:
    from .generation import on_stage
    from .host_config import get_apworld_updater_config
    import atexit

    def _on_generate_early(multiworld: Any, *args: Any, **kwargs: Any) -> None:
        try:
            from worlds.AutoWorld import AutoWorldRegister
            from .generation import get_current_stage
            cfg = get_apworld_updater_config()
            accept_mode = str(cfg.get("accept_mode", "each")).lower()
            if accept_mode not in ("each", "all", "auto"):
                accept_mode = "each"
            logger.info(f"APAPI updater: _on_generate_early called for {len(getattr(multiworld, 'worlds', {}))} worlds, stage={get_current_stage()}, game_ids={list(getattr(multiworld, 'game', {}).keys())}")
            # Collect all apworld_version_wanted requests – now just a string, game derived from YAML's game field
            requests: List[Tuple[int, str, str, str]] = []
            for pid, world in list(getattr(multiworld, "worlds", {}).items()):
                try:
                    opt = getattr(getattr(world, "options", None), "apworld_version_wanted", None)
                    logger.info(f"APAPI updater: pid {pid} world {getattr(world, 'game', '?')} opt={opt} val={getattr(opt, 'value', None) if opt else None}")
                    if opt is None:
                        continue
                    val = getattr(opt, "value", None)
                    if val is None:
                        continue
                    player_name = getattr(multiworld, "player_name", {}).get(pid, f"Player {pid}")
                    if isinstance(val, str):
                        spec = val.strip()
                        if not spec:
                            try:
                                _game0 = getattr(world, "game", None) or getattr(multiworld, "game", {}).get(pid, "")
                                spec = _implied_spec(_game0, str(player_name)) or ""
                            except Exception:
                                spec = ""
                            if not spec:
                                continue
                        game = getattr(world, "game", None) or getattr(multiworld, "game", {}).get(pid, "")
                        if not isinstance(game, str) or not game.strip():
                            continue
                        game = game.strip()
                        requests.append((pid, str(player_name), game, spec))
                    elif isinstance(val, dict):
                        for game, spec in val.items():
                            if not isinstance(game, str) or not isinstance(spec, str):
                                continue
                            game = game.strip()
                            spec = spec.strip()
                            if not game or not spec:
                                continue
                            requests.append((pid, str(player_name), game, spec))
                except Exception:
                    continue
            # Also check for players whose game is not installed at all (missing from AutoWorldRegister)
            # These won't be in multiworld.worlds, but are in multiworld.game / player_name
            try:
                from worlds.AutoWorld import AutoWorldRegister
                for pid in list(getattr(multiworld, "player_ids", [])):
                    if pid in getattr(multiworld, "worlds", {}):
                        continue
                    game = getattr(multiworld, "game", {}).get(pid, "")
                    if not isinstance(game, str) or not game.strip() or game in AutoWorldRegister.world_types:
                        continue
                    # Try to find apworld_version_wanted from raw YAML via player files
                    # Check if any already collected request for this pid
                    if any(r[0] == pid for r in requests):
                        continue
                    # Try to read from slot data or options via world's yaml
                    # Fallback: check if multiworld has plando or other
                    # For now, try to get from the player's yaml file if available
                    try:
                        from worlds.APAPI.yaml_tools import resolve_player_files_dir, iter_player_yaml_files, read_yaml_documents_file
                        player_name = getattr(multiworld, "player_name", {}).get(pid, f"Player {pid}")
                        # Search for yaml file matching player_name
                        pdir = resolve_player_files_dir()
                        if pdir and pdir.is_dir():
                            for yf in iter_player_yaml_files(pdir):
                                try:
                                    docs = read_yaml_documents_file(yf)
                                    for doc in docs:
                                        if isinstance(doc, dict) and str(doc.get("name", "")).strip() == str(player_name).strip():
                                            # Check for apworld_version_wanted in this doc
                                            # It could be at top level or under game options?
                                            # Check top level
                                            if "apworld_version_wanted" in doc:
                                                spec = str(doc["apworld_version_wanted"]).strip()
                                                if spec:
                                                    requests.append((pid, str(player_name), str(game).strip(), spec))
                                                    break
                                            # Check under game-specific options?
                                            game_opts = doc.get(str(game), {})
                                            if isinstance(game_opts, dict) and "apworld_version_wanted" in game_opts:
                                                spec = str(game_opts["apworld_version_wanted"]).strip()
                                                if spec:
                                                    requests.append((pid, str(player_name), str(game).strip(), spec))
                                                    break
                                except Exception:
                                    continue
                    except Exception:
                        pass
            except Exception:
                pass
            if not requests:
                return
            # Anything already decided up front (Generate.main pre-collect)
            # keeps its decision: approved specs route without re-prompting.
            decided_allowed = [r for r in requests
                               if _CONSENT.get(_consent_key(r[2], r[3]), None) is True]
            requests = [r for r in requests
                        if _consent_key(r[2], r[3]) not in _CONSENT]
            # Prompt handling (only for not-yet-decided requests)
            allow_all = accept_mode == "auto"
            allowed: List[Tuple[int, str, str, str]] = list(decided_allowed)
            if allow_all:
                # Even in auto, warn for non-index downloads (direct, github, release) – potentially dangerous
                filtered: List[Tuple[int, str, str, str]] = []
                for pid, pname, game, spec in requests:
                    kind, _ = _parse_spec(spec)
                    if kind != "index":
                        try:
                            import sys
                            is_term = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
                            url = resolve_spec_to_url(game, spec) or spec
                            if is_term and bool(cfg.get("ask_in_terminal", True)):
                                print(f"\n WARNING: Direct apworld download for {pname} (P{pid}) {game} -> {spec}")
                                print(f"  URL: {url}")
                                print(f"  Direct file downloads can be dangerous (not from index).")
                                ans = (_prompt_user(f" Allow direct download for {pname} {game} {spec}?\n [y/N]: ") or "").strip().lower()
                                if ans in ("y", "yes"):
                                    filtered.append((pid, pname, game, spec))
                                else:
                                    logger.info(f"APAPI updater: denied direct {pname} {game} {spec} even in auto")
                                    print(f"  Denied direct download for {pname}")
                                continue
                        except Exception:
                            pass
                    filtered.append((pid, pname, game, spec))
                allowed = filtered
                if not allowed:
                    logger.info("APAPI updater: no apworld requests allowed after direct-file warning (auto mode)")
                    return
                logger.info(f"APAPI updater: auto-accepting {len(allowed)}/{len(requests)} apworld requests (accept_mode=auto, direct files filtered)")
            elif accept_mode == "all":
                try:
                    import sys
                    is_term = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
                    if not is_term or str(cfg.get("ask_in_terminal", True)).lower() == "false":
                        allowed = requests
                    else:
                        print("\n APAPI apworld_version_wanted requests:")
                        for pid, pname, game, spec in requests:
                            url = resolve_spec_to_url(game, spec) or spec
                            print(f"  Player {pname} (P{pid}) wants {game} -> {spec} ({url})")
                        ans = (_prompt_user("Allow all apworld installs?\n [y/N/all]: ") or "").strip().lower()
                        if ans in ("y", "yes", "all", "a"):
                            allowed = requests
                        else:
                            logger.info("APAPI updater: user denied all apworld requests")
                            return
                except Exception:
                    allowed = requests
            else:  # each
                try:
                    import sys
                    is_term = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
                    ask = bool(cfg.get("ask_in_terminal", True))
                    if not is_term or not ask:
                        # If not terminal or not asking, deny unless auto
                        logger.info("APAPI updater: terminal not available, denying apworld requests (set accept_mode=auto to allow)")
                        return
                    for pid, pname, game, spec in requests:
                        url = resolve_spec_to_url(game, spec) or spec
                        print(f"\n Player {pname} (P{pid}) wants {game} -> {spec}")
                        print(f"  Resolved URL: {url}")
                        ans = (_prompt_user(f" Allow install for {pname} {game} {spec}?\n [y/N]: ") or "").strip().lower()
                        if ans in ("y", "yes"):
                            allowed.append((pid, pname, game, spec))
                        else:
                            logger.info(f"APAPI updater: denied {pname} {game} {spec}")
                except Exception as exc:
                    logger.debug(f"APAPI updater per-request prompt failed: {exc}")
                    return
            if not allowed:
                return
            # Resolve every requested version, subset-merge ID maps, write one
            # datapackage per game, and record per-player routes (same game name
            # throughout; true ID conflicts raise inside apply_version_routing).
            routed = apply_version_routing(multiworld, allowed)
            if routed:
                print(f" APAPI: version routing installed for {len(routed)} player(s), "
                      f"continuing generation with merged datapackages")
            uncovered = [(pid, pname, game, spec) for pid, pname, game, spec in requests
                         if pid not in (routed or {})]
            if uncovered:
                who = "; ".join(f"{pname} (P{pid}) wants {game} {spec}" for pid, pname, game, spec in uncovered)
                raise ConsentDeniedError(
                    f"APAPI updater: no versioned class for {who} (download denied or failed). "
                    f"Generation cannot proceed without these versions.")
        except Exception as exc:
            logger.error(f"APAPI updater generate_early hook failed: {exc}", exc_info=True)
            raise

    try:
        on_stage("assert_generate", _on_generate_early)
        on_stage("generate_early", _on_generate_early)
        try:
            from .hard_patch import hard_patches
            hard_patches.add_wrapper("BaseClasses.MultiWorld.set_options", _set_options_wrapper, load_missing=True)
        except Exception as exc:
            logger.debug(f"APAPI updater: failed to wrap MultiWorld.set_options: {exc}")
        # Also patch MultiWorld creation to handle apworld_version_wanted before worlds are made
        try:
            from BaseClasses import MultiWorld as _MW
            _orig_mw_init = _MW.__init__
            def _patched_mw_init(self, *args, **kwargs):
                # Before any world is made, handle apworld_version_wanted for missing games and versioned installs
                # This ensures the correct apworld version is available before MultiWorld validates games
                try:
                    from worlds.AutoWorld import AutoWorldRegister
                    import pathlib
                    # Collect all requests from YAML files before MultiWorld creation
                    early_requests = _scan_apworld_specs_from_yamls()
                    if early_requests:
                        logger.info(f"APAPI updater: pre-MultiWorld found {len(early_requests)} apworld_version_wanted requests before world creation")
                        # Remember specs per player for the set_options routing step.
                        try:
                            pending: Dict[str, Tuple[str, str]] = {}
                            for player_name, game, spec in early_requests:
                                pending.setdefault(str(player_name), (game, spec))
                            self._apapi_pending_specs = pending  # type: ignore
                        except Exception:
                            pass
                        # Ensure every requested version is loaded (side-by-side
                        # instances share one game name). Routing happens later.
                        for player_name, game, spec in early_requests:
                            try:
                                temp_dir = get_run_temp_dir()
                                work = temp_dir / f"pre_{game.replace(' ', '_').replace('/', '_')}"
                                cls = ensure_versioned_class(game, spec, work)
                                if cls is None:
                                    logger.warning(f"APAPI updater: pre-MultiWorld failed to obtain {game} {spec} for {player_name}")
                                    continue
                                logger.info(f"APAPI updater: pre-MultiWorld ensured {game} {spec} for {player_name}")
                            except Exception as e:
                                logger.warning(f"APAPI updater: pre-MultiWorld handling failed for {player_name} {game} {spec}: {e}")
                                continue
                except Exception as e:
                    logger.debug(f"APAPI updater: pre-MultiWorld check failed: {e}")
                return _orig_mw_init(self, *args, **kwargs)
            _MW.__init__ = _patched_mw_init
        except Exception as e:
            logger.debug(f"APAPI updater: failed to patch MultiWorld.__init__ for pre-world handling: {e}")
    except Exception:
        pass

    atexit.register(cleanup_temp_apworlds)
except Exception:
    pass

try:
    from .host_config import get_apworld_updater_config
    import sys

    def _prompt_auto_updates(updates: List[Tuple[str, str, str, str]]) -> List[Tuple[str, str, str, str]]:
        cfg = get_apworld_updater_config()
        accept_mode = str(cfg.get("accept_mode", "each")).lower()
        ask_in_term = bool(cfg.get("ask_in_terminal", True))
        is_term = False
        try:
            is_term = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
        except Exception:
            is_term = False
        if accept_mode == "auto":
            return updates
        if not ask_in_term or not is_term:
            logger.info("APAPI updater: auto-update terminal not available or ask disabled, skipping")
            return []
        if accept_mode == "all":
            print("\n APAPI auto-updates available:")
            for game, cur, new, url in updates:
                print(f"  {game}: {cur} -> {new} ({url})")
            ans = (_prompt_user(" Apply all auto-updates?\n [y/N]: ") or "").strip().lower()
            if ans in ("y", "yes", "all", "a"):
                return updates
            return []
        # each
        allowed: List[Tuple[str, str, str, str]] = []
        for game, cur, new, url in updates:
            print(f"\n APWorld update for {game}: {cur} -> {new}")
            print(f"  URL: {url}")
            ans = (_prompt_user(f" Update {game}?\n [y/N]: ") or "").strip().lower()
            if ans in ("y", "yes"):
                allowed.append((game, cur, new, url))
        return allowed

    def handle_launcher_auto_updates() -> None:
        try:
            cfg = get_apworld_updater_config()
            if not bool(cfg.get("auto_update_enabled", False)):
                return
            index_data = _fetch_index()
            if not index_data:
                return
            import pathlib
            from Utils import user_path
            try:
                import worlds
                folder = getattr(worlds, "user_folder", None)
                if not folder:
                    folder = user_path("custom_worlds")
                base = pathlib.Path(folder)
            except Exception:
                base = pathlib.Path(user_path("custom_worlds"))
            if not base.is_dir():
                return
            # Find installed apworlds
            installed: List[Tuple[str, pathlib.Path, str]] = []
            for p in base.iterdir():
                if p.is_file() and p.suffix.lower() == ".apworld":
                    try:
                        from worlds.Files import APWorldContainer
                        ap = APWorldContainer(str(p))
                        ap.read()
                        game = ap.game or p.stem
                        ver = str(ap.version) if hasattr(ap, "version") else "unknown"
                        # Try to get world_version from manifest
                        try:
                            manifest = ap.manifest or {}
                            ver = str(manifest.get("world_version") or manifest.get("version") or ver)
                        except Exception:
                            pass
                        installed.append((game, p, ver))
                    except Exception:
                        continue
            # Compare to index
            updates: List[Tuple[str, str, str, str]] = []
            for game, path, cur_ver in installed:
                try:
                    # Find latest in index
                    games = index_data.get("games", index_data)
                    if isinstance(games, dict) and game in games:
                        entry = games[game]
                        latest = None
                        url = None
                        if isinstance(entry, dict):
                            latest = entry.get("latest_version") or entry.get("version") or entry.get("latest")
                            url = entry.get("apworld_url") or entry.get("download_url") or entry.get("url")
                            # Try versions dict
                            if not latest and isinstance(entry.get("versions"), dict):
                                vers = entry["versions"]
                                if vers:
                                    latest = sorted(vers.keys())[-1]
                                    v = vers[latest]
                                    if isinstance(v, dict):
                                        url = v.get("apworld_url") or v.get("download_url") or v.get("url")
                                    elif isinstance(v, str):
                                        url = v
                        if latest and url and str(latest) != str(cur_ver):
                            updates.append((game, cur_ver, str(latest), url))
                except Exception:
                    continue
            if not updates:
                return
            allowed = _prompt_auto_updates(updates)
            if not allowed:
                return
            for game, cur, new, url in allowed:
                try:
                    print(f" APAPI: Auto-updating {game} {cur} -> {new} from {url}")
                    dest = _download_to_temp(url)
                    # Install to custom_worlds (overwrite)
                    import shutil, pathlib as pl
                    target = base / f"{game}.apworld"
                    # Try to find correct target name from download
                    # Use installed apworld's name if game contains it
                    # For now, use dest's name if it matches game
                    # Actually, use the installed path's name
                    for g2, p2, v2 in installed:
                        if g2 == game:
                            target = p2
                            break
                    shutil.move(str(dest), str(target))
                    logger.info(f"APAPI updater: auto-updated {game} to {new} at {target}")
                    print(f"  Updated {game} to {new}")
                except Exception as exc:
                    logger.warning(f"APAPI updater: auto-update failed for {game}: {exc}")
                    print(f"  Failed to update {game}: {exc}")
            # After auto-updates, restart launcher/generation if needed
            # For launcher, just continue; for generation, caller will handle restart
        except Exception as exc:
            logger.debug(f"APAPI updater: launcher auto-update check failed: {exc}")

    # Hook launcher auto-updates to run on import (frozen) and on generate_early
    try:
        from .launch_context import is_launcher_context, is_generate_context
        if is_launcher_context():
            try:
                handle_launcher_auto_updates()
            except Exception:
                pass
    except Exception:
        pass

    # Also handle auto-updates during generation with restart
    try:
        from .generation import on_stage as _on_stage2
        def _on_generate_early_auto_update(multiworld: Any, *args: Any, **kwargs: Any) -> None:
            try:
                cfg = get_apworld_updater_config()
                if not bool(cfg.get("auto_update_enabled", False)):
                    return
                # Reuse same logic but with restart
                import pathlib
                from Utils import user_path
                import worlds
                index_data = _fetch_index()
                if not index_data:
                    return
                try:
                    folder = getattr(worlds, "user_folder", None)
                    if not folder:
                        folder = user_path("custom_worlds")
                    base = pathlib.Path(folder)
                except Exception:
                    base = pathlib.Path(user_path("custom_worlds"))
                if not base.is_dir():
                    return
                installed = []
                for p in base.iterdir():
                    if p.is_file() and p.suffix.lower() == ".apworld":
                        try:
                            from worlds.Files import APWorldContainer
                            ap = APWorldContainer(str(p))
                            ap.read()
                            game = ap.game or p.stem
                            ver = str(getattr(ap, "version", "unknown"))
                            try:
                                manifest = ap.manifest or {}
                                ver = str(manifest.get("world_version") or manifest.get("version") or ver)
                            except Exception:
                                pass
                            installed.append((game, p, ver))
                        except Exception:
                            continue
                updates = []
                for game, path, cur_ver in installed:
                    try:
                        games = index_data.get("games", index_data)
                        if isinstance(games, dict) and game in games:
                            entry = games[game]
                            latest = None
                            url = None
                            if isinstance(entry, dict):
                                latest = entry.get("latest_version") or entry.get("version") or entry.get("latest")
                                url = entry.get("apworld_url") or entry.get("download_url") or entry.get("url")
                                if not latest and isinstance(entry.get("versions"), dict):
                                    vers = entry["versions"]
                                    if vers:
                                        latest = sorted(vers.keys())[-1]
                                        v = vers[latest]
                                        if isinstance(v, dict):
                                            url = v.get("apworld_url") or v.get("download_url") or v.get("url")
                                        elif isinstance(v, str):
                                            url = v
                            if latest and url and str(latest) != str(cur_ver):
                                updates.append((game, cur_ver, str(latest), url))
                    except Exception:
                        continue
                if not updates:
                    return
                allowed = _prompt_auto_updates(updates)
                if not allowed:
                    return
                for game, cur, new, url in allowed:
                    try:
                        dest = _download_to_temp(url)
                        import shutil
                        target = None
                        for g2, p2, v2 in installed:
                            if g2 == game:
                                target = p2
                                break
                        if target is None:
                            target = base / f"{game}.apworld"
                        shutil.move(str(dest), str(target))
                        logger.info(f"APAPI updater: auto-updated {game} to {new} at {target}")
                    except Exception as exc:
                        logger.warning(f"APAPI updater: auto-update failed for {game}: {exc}")
                        continue
                # Restart generation
                print(" APAPI: Auto-updates installed, restarting generation...")
                logger.info("APAPI updater: restarting generation after auto-updates")
                import sys, os
                # Use exec to restart with same args
                try:
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                except Exception as exc:
                    logger.warning(f"APAPI updater: restart failed: {exc}")
                    # Fallback: raise to abort and let user restart
                    raise SystemExit(f"APAPI auto-updates installed, please restart generation manually: {exc}")
            except Exception as exc:
                logger.debug(f"APAPI updater: generate auto-update check failed: {exc}")
        try:
            _on_stage2("generate_early", _on_generate_early_auto_update)
        except Exception:
            pass
    except Exception:
        pass
except Exception:
    pass
