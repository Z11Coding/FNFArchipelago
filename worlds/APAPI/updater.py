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
    try:
        if path.is_file() and path.suffix.lower() == ".apworld":
            from worlds.Files import APWorldContainer
            ap = APWorldContainer(str(path))
            ap.read()
            try:
                manifest = ap.manifest or {}
                v = manifest.get("world_version") or manifest.get("version")
                if v is not None:
                    return str(v)
            except Exception:
                pass
            try:
                v = getattr(ap, "version", None)
                if v is not None:
                    return str(v)
            except Exception:
                pass
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
    import json
    import urllib.request
    url = index_url or _get_index_url()
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except Exception as exc:
        logger.warning(f"APAPI updater: failed to fetch index {url}: {exc}")
        return {}


def _resolve_index_spec(game: str, spec: str, index_data: Dict[str, Any] | None = None) -> str | None:
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


def cleanup_temp_apworlds() -> None:
    try:
        d = get_temp_apworld_dir()
        if d.is_dir():
            for p in d.iterdir():
                try:
                    if p.is_file():
                        p.unlink()
                    elif p.is_dir():
                        shutil.rmtree(p)
                except Exception:
                    pass
    except Exception:
        pass


def _merge_datapackages(old_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("item_name_to_id", "location_name_to_id"):
        old_map = old_data.get(key, {}) if isinstance(old_data, dict) else {}
        new_map = new_data.get(key, {}) if isinstance(new_data, dict) else {}
        if not isinstance(old_map, dict) or not isinstance(new_map, dict):
            continue
        for name, nid in new_map.items():
            if name in old_map and old_map[name] != nid:
                raise Exception(f"Datapackage conflict for {key} {name!r}: {old_map[name]} vs {nid} (Ice:20 vs Ice:40)")
        for name, nid in old_map.items():
            if name in new_map and new_map[name] != nid:
                raise Exception(f"Datapackage conflict for {key} {name!r}: {old_map[name]} vs {new_map[name]}")
    merged = dict(old_data) if isinstance(old_data, dict) else {}
    for k, v in new_data.items():
        if k in ("item_name_to_id", "location_name_to_id") and isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        elif isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            if k not in merged:
                merged[k] = v
    return merged


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
            # If this is generate_early and we previously set per-pid unique games at assert_generate, restore original game names but keep per-pid class
            try:
                orig_map = getattr(multiworld, "_apapi_original_game", None)
                if isinstance(orig_map, dict) and orig_map:
                    for pid, orig_game in list(orig_map.items()):
                        try:
                            # If world already created with unique game, fix its game back to original
                            w = multiworld.worlds.get(pid)
                            if w is not None and getattr(w, "game", None) != orig_game:
                                # Keep the per-pid class (already swapped or unique), but restore game name for server/datapackage
                                w.game = orig_game  # type: ignore
                                multiworld.game[pid] = orig_game
                                logger.info(f"APAPI updater: restored {orig_game} for P{pid} after per-pid unique creation")
                        except Exception:
                            pass
                    # Clear after handling
                    try:
                        delattr(multiworld, "_apapi_original_game")
                    except Exception:
                        pass
            except Exception:
                pass
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
            # Prompt handling
            allow_all = accept_mode == "auto"
            allowed: List[Tuple[int, str, str, str]] = []
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
                                ans = input(f" Allow direct download for {pname} {game} {spec}? [y/N]: ").strip().lower()
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
                        ans = input("Allow all apworld installs? [y/N/all]: ").strip().lower()
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
                        ans = input(f" Allow install for {pname} {game} {spec}? [y/N]: ").strip().lower()
                        if ans in ("y", "yes"):
                            allowed.append((pid, pname, game, spec))
                        else:
                            logger.info(f"APAPI updater: denied {pname} {game} {spec}")
                except Exception as exc:
                    logger.debug(f"APAPI updater per-request prompt failed: {exc}")
                    return
            if not allowed:
                return
            # Download and temp-install with per-pid unique handling and version check for installed folders/custom_worlds
            temp_dir = get_temp_apworld_dir()
            temp_worlds: List[Tuple[str, pathlib.Path, Dict[str, Any]]] = []
            merged_datapackages: Dict[str, Dict[str, Any]] = {}
            for pid, pname, game, spec in allowed:
                try:
                    from worlds.AutoWorld import AutoWorldRegister
                    is_missing = game not in AutoWorldRegister.world_types
                    if is_missing:
                        print(f" APAPI: {game} not installed locally, will download {spec} for {pname} from index...")
                    installed_versions = _find_installed_versions(game)
                    spec_ver = spec.strip().lstrip("v")
                    found_installed = None
                    for ipath, iver in installed_versions:
                        try:
                            if _parse_semver(iver) == _parse_semver(spec_ver):
                                found_installed = (ipath, iver)
                                break
                        except Exception:
                            continue
                    if found_installed and not is_missing:
                        ipath, iver = found_installed
                        print(f" APAPI: Using already installed {game} {iver} at {ipath} for {pname} (wanted {spec})")
                        # Still need to handle per-pid unique if multiple versions coexist
                        # Try to ensure datapackage merged
                        try:
                            from worlds.AutoWorld import AutoWorldRegister
                            from worlds.Files import APWorldContainer
                            # Get data for this installed version
                            ap = APWorldContainer(str(ipath)) if ipath.suffix.lower() == ".apworld" else None
                            # For folders, need to get via AutoWorldRegister
                            if game in AutoWorldRegister.world_types:
                                cur_data = AutoWorldRegister.world_types[game].get_data_package_data()
                                if game not in merged_datapackages:
                                    merged_datapackages[game] = cur_data
                                else:
                                    merged_datapackages[game] = _merge_datapackages(merged_datapackages[game], cur_data)
                        except Exception:
                            pass
                        # Per-pid unique: if this pid's world already uses this version, keep it; else need to handle
                        # For already installed, the world class is already correct, so just mark done
                        temp_worlds.append((game, ipath, {}))
                        continue
                    print(f" APAPI: Downloading {game} {spec} for {pname}...")
                    per_pid_dir = temp_dir / f"pid_{pid}_{game.replace(' ', '_').replace('/', '_')}"
                    per_pid_dir.mkdir(parents=True, exist_ok=True)
                    dest = download_apworld_for_spec(game, spec, per_pid_dir)
                    if dest is None or not dest.is_file():
                        raise Exception(f"Failed to download {game} {spec} for {pname} (resolved URL missing or download failed) - APAPI requires correct apworld version to generate properly")
                    # If game was not installed at all, ask if it should be saved to custom_worlds
                    try:
                        if is_missing:
                            try:
                                import sys
                                is_term = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
                                cfg2 = get_apworld_updater_config()
                                ask = bool(cfg2.get("ask_in_terminal", True))
                                save = False
                                if is_term and ask:
                                    ans = input(f" {game} not installed. Save downloaded {dest.name} to custom_worlds permanently? [y/N]: ").strip().lower()
                                    save = ans in ("y", "yes")
                                else:
                                    # Non-interactive: save by default for missing
                                    save = True
                                if save:
                                    from Utils import user_path
                                    import shutil
                                    target = pathlib.Path(user_path("custom_worlds")) / dest.name
                                    target.parent.mkdir(parents=True, exist_ok=True)
                                    shutil.copyfile(dest, target)
                                    print(f"  Saved {game} to {target}")
                                    logger.info(f"APAPI updater: saved {game} {dest.name} to custom_worlds for {pname}")
                                    # Also try to install normally (copy already done, now register that target instead of temp)
                                    # Keep dest as is for temp handling, but also ensure target is registered
                                    try:
                                        import worlds as _w2
                                        import bisect as _bis2
                                        already2 = any(pathlib.Path(s.resolved_path) == target for s in _w2.world_sources)
                                        if not already2:
                                            src2 = _w2.WorldSource(str(target), is_zip=True, relative=False)
                                            _bis2.insort(_w2.world_sources, src2)
                                            src2.load()
                                    except Exception:
                                        pass
                            except Exception as e:
                                logger.debug(f"APAPI updater: save prompt failed for {game}: {e}")
                    except Exception:
                        pass
                    import worlds
                    import bisect
                    already = False
                    for existing in worlds.world_sources:
                        try:
                            if pathlib.Path(existing.resolved_path) == dest:
                                already = True
                                break
                        except Exception:
                            continue
                    from worlds.AutoWorld import AutoWorldRegister
                    old_cls = AutoWorldRegister.world_types.get(game)
                    old_data = None
                    if old_cls is not None:
                        try:
                            old_data = old_cls.get_data_package_data()
                        except Exception:
                            old_data = None
                    if not already:
                        # For temp apworlds outside worlds/custom_worlds, use zipimport directly
                        import zipimport
                        import importlib.util
                        import sys
                        # Try WorldSource first, fallback to direct zipimport
                        source = worlds.WorldSource(str(dest), is_zip=True, relative=False)
                        bisect.insort(worlds.world_sources, source)
                        ok = bool(source.load())
                        if not ok:
                            # Fallback: direct zipimport for temp files
                            try:
                                # Determine world_name from apworld internal folder
                                import zipfile
                                world_name = None
                                with zipfile.ZipFile(dest) as zf:
                                    for n in zf.namelist():
                                        if n.endswith("/__init__.py") and "/" in n:
                                            world_name = n.split("/")[0]
                                            break
                                if world_name:
                                    importer = zipimport.zipimporter(str(dest))
                                    spec = importer.find_spec(f"worlds.{world_name}")
                                    if spec and spec.loader:
                                        # Register spec for future imports
                                        try:
                                            from worlds import apworld_module_specs
                                            apworld_module_specs[f"worlds.{world_name}"] = spec
                                        except Exception:
                                            # Create the dict if not exists and add to meta_path
                                            try:
                                                import worlds as _wmod
                                                if not hasattr(_wmod, "apworld_module_specs"):
                                                    _wmod.apworld_module_specs = {}
                                                _wmod.apworld_module_specs[f"worlds.{world_name}"] = spec
                                                # Ensure finder is installed
                                                from worlds import apworld_module_specs as _specs
                                                import importlib.abc
                                                import importlib.machinery
                                                # Try to find existing finder
                                                found = False
                                                for finder in sys.meta_path:
                                                    if type(finder).__name__ == "APWorldModuleFinder":
                                                        found = True
                                                        break
                                                if not found:
                                                    # Create a simple finder
                                                    class _TempFinder(importlib.abc.MetaPathFinder):
                                                        def find_spec(self, fullname, path, target=None):
                                                            return _specs.get(fullname)
                                                    sys.meta_path.insert(0, _TempFinder())
                                            except Exception:
                                                pass
                                        # Now try to load
                                        mod = importlib.util.module_from_spec(spec)
                                        sys.modules[f"worlds.{world_name}"] = mod
                                        spec.loader.exec_module(mod)
                                        ok = True
                            except Exception as e2:
                                raise Exception(f"Failed to load apworld {dest} for {game} via fallback: {e2}") from e2
                        if not ok:
                            raise Exception(f"Failed to load apworld {dest} for {game} - WorldSource.load() returned False (check apworld structure, expected tunic folder inside) after fallback")
                        # After load, new class is now in AutoWorldRegister[game] (overwrote old)
                        new_cls = AutoWorldRegister.world_types.get(game)
                        if new_cls is not None and old_cls is not None and new_cls is not old_cls:
                            # Restore old under original game, and register new under unique pid key
                            unique_game = f"{game}__APAPI_{pid}_{abs(hash(spec))%10000}"
                            # Keep old
                            AutoWorldRegister.world_types[game] = old_cls
                            # Register new under unique
                            AutoWorldRegister.world_types[unique_game] = new_cls
                            # Also keep in world_sources with unique name for tracking
                            try:
                                w = multiworld.worlds.get(pid)
                                if w is not None:
                                    if getattr(w, "game", None) == game:
                                        w.__class__ = new_cls  # type: ignore
                                        try:
                                            w.item_name_to_id = new_cls.item_name_to_id  # type: ignore
                                            w.location_name_to_id = new_cls.location_name_to_id  # type: ignore
                                        except Exception:
                                            pass
                                        logger.info(f"APAPI updater: per-pid {pname} P{pid} now uses {game}@{spec} as {unique_game} (swapped existing world)")
                                else:
                                    # Worlds not yet created (assert_generate) – set game for this pid to unique so future creation uses correct version
                                    # Keep original game for datapackage, but use unique for world class lookup
                                    try:
                                        orig_game = multiworld.game.get(pid, game)
                                        # Store mapping for later re-evaluation
                                        if not hasattr(multiworld, "_apapi_original_game"):
                                            multiworld._apapi_original_game = {}  # type: ignore
                                        multiworld._apapi_original_game[pid] = orig_game  # type: ignore
                                        multiworld.game[pid] = unique_game
                                        logger.info(f"APAPI updater: per-pid {pname} P{pid} will use {game}@{spec} as {unique_game} (set before world creation)")
                                    except Exception as ee:
                                        logger.debug(f"APAPI updater: could not set per-pid game for {pname}: {ee}")
                            except Exception as e:
                                raise Exception(f"APAPI updater: per-pid class swap failed for {pname} P{pid} {game}@{spec}: {e}") from e
                            try:
                                new_data = new_cls.get_data_package_data()
                                if game in merged_datapackages:
                                    merged = _merge_datapackages(merged_datapackages[game], new_data)
                                    merged_datapackages[game] = merged
                                elif old_data is not None:
                                    merged = _merge_datapackages(old_data, new_data)
                                    merged_datapackages[game] = merged
                                else:
                                    merged_datapackages[game] = new_data
                                worlds.network_data_package["games"][game] = merged_datapackages[game]
                            except Exception as merge_exc:
                                raise Exception(f"Datapackage merge failed for {game} P{pid} {spec}: {merge_exc}") from merge_exc
                        else:
                            from worlds.Files import APWorldContainer
                            apworld = APWorldContainer(str(dest))
                            apworld.read()
                            new_game = apworld.game
                            if new_game and new_game in AutoWorldRegister.world_types:
                                new_data = AutoWorldRegister.world_types[new_game].get_data_package_data()
                                if new_game in merged_datapackages:
                                    merged = _merge_datapackages(merged_datapackages[new_game], new_data)
                                    merged_datapackages[new_game] = merged
                                    worlds.network_data_package["games"][new_game] = merged
                                elif old_data is not None:
                                    merged = _merge_datapackages(old_data, new_data)
                                    merged_datapackages[new_game] = merged
                                    worlds.network_data_package["games"][new_game] = merged
                                else:
                                    merged_datapackages[new_game] = new_data
                                    try:
                                        worlds.network_data_package["games"][new_game] = new_data
                                    except Exception as e:
                                        raise Exception(f"Failed to set datapackage for {new_game}: {e}") from e
                            else:
                                raise Exception(f"Failed to get datapackage for {new_game} after loading {dest} - game not in AutoWorldRegister")
                    temp_worlds.append((game, dest, {}))
                    print(f"  Installed temp {game} {dest.name} for {pname}")
                    logger.info(f"APAPI updater: temp installed {game} {spec} -> {dest} for {pname}")
                except Exception as exc:
                    logger.error(f"APAPI updater: failed to handle {game} {spec} for {pname}: {exc}")
                    print(f"  Error handling {game} {spec}: {exc}")
                    raise Exception(f"APAPI updater: Failed to handle {game} {spec} for {pname}: {exc}") from exc
            # Apply final merged datapackages for all games with multiple versions
            for game, merged in merged_datapackages.items():
                try:
                    import worlds
                    worlds.network_data_package["games"][game] = merged
                    logger.info(f"APAPI updater: final merged datapackage for {game} with {len(merged.get('item_name_to_id', {}))} items")
                except Exception:
                    pass
            if temp_worlds:
                print(f" APAPI: {len(temp_worlds)} temp apworld(s) installed, continuing generation with merged datapackages (temp, not in custom_worlds)")
        except Exception as exc:
            logger.error(f"APAPI updater generate_early hook failed: {exc}", exc_info=True)
            raise

    try:
        on_stage("assert_generate", _on_generate_early)
        on_stage("generate_early", _on_generate_early)
        # Also patch MultiWorld creation to handle apworld_version_wanted before worlds are made
        try:
            from BaseClasses import MultiWorld as _MW
            _orig_mw_init = _MW.__init__
            def _patched_mw_init(self, *args, **kwargs):
                # Before any world is made, handle apworld_version_wanted for missing games and versioned installs
                # This ensures the correct apworld version is available before MultiWorld validates games
                try:
                    from worlds.APAPI.yaml_tools import resolve_player_files_dir, iter_player_yaml_files, read_yaml_documents_file
                    from worlds.AutoWorld import AutoWorldRegister
                    import pathlib
                    pdir = resolve_player_files_dir()
                    # Collect all requests from YAML files before MultiWorld creation
                    early_requests: List[Tuple[str, str, str]] = []  # (player_name, game, spec)
                    if pdir and pdir.is_dir():
                        for yf in iter_player_yaml_files(pdir):
                            try:
                                docs = read_yaml_documents_file(yf)
                                for doc in docs:
                                    if not isinstance(doc, dict):
                                        continue
                                    game = str(doc.get("game", "")).strip()
                                    player_name = str(doc.get("name", "")).strip() or yf.stem
                                    if not game:
                                        continue
                                    spec = None
                                    if "apworld_version_wanted" in doc:
                                        spec = str(doc["apworld_version_wanted"]).strip()
                                    else:
                                        game_opts = doc.get(game, {})
                                        if isinstance(game_opts, dict) and "apworld_version_wanted" in game_opts:
                                            spec = str(game_opts["apworld_version_wanted"]).strip()
                                    if not spec:
                                        continue
                                    early_requests.append((player_name, game, spec))
                            except Exception:
                                continue
                    if early_requests:
                        logger.info(f"APAPI updater: pre-MultiWorld found {len(early_requests)} apworld_version_wanted requests before world creation")
                        # For each request, ensure the apworld version is available
                        # Use same accept_mode logic as generation
                        from worlds.APAPI.host_config import get_apworld_updater_config
                        cfg = get_apworld_updater_config()
                        accept_mode = str(cfg.get("accept_mode", "each")).lower()
                        # For pre-world, we need to handle missing games and version mismatches immediately
                        # We will download to temp and register, with per-pid unique handling deferred to generate_early
                        # But for missing games, we must ensure the game is in AutoWorldRegister before MultiWorld validates
                        for player_name, game, spec in early_requests:
                            try:
                                # Check if already installed with correct version
                                installed = _find_installed_versions(game)
                                spec_ver = spec.strip().lstrip("v")
                                found = any(_parse_semver(iver) == _parse_semver(spec_ver) for _, iver in installed)
                                if found:
                                    continue
                                # Check if game not in AutoWorldRegister at all (missing)
                                is_missing = game not in AutoWorldRegister.world_types
                                # For missing or version mismatch, download now to temp and register
                                # Use temp dir per game
                                temp_dir = get_temp_apworld_dir()
                                per_game_dir = temp_dir / f"pre_{game.replace(' ', '_').replace('/', '_')}"
                                per_game_dir.mkdir(parents=True, exist_ok=True)
                                dest = download_apworld_for_spec(game, spec, per_game_dir)
                                if dest is None or not dest.is_file():
                                    logger.warning(f"APAPI updater: pre-MultiWorld failed to download {game} {spec} for {player_name}")
                                    continue
                                # For missing games, ask if should be saved to custom_worlds
                                if is_missing:
                                    try:
                                        import sys
                                        is_term = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
                                        ask = bool(cfg.get("ask_in_terminal", True))
                                        save = False
                                        if is_term and ask:
                                            ans = input(f" {game} not installed. Save downloaded {dest.name} to custom_worlds permanently? [y/N]: ").strip().lower()
                                            save = ans in ("y", "yes")
                                        else:
                                            save = True
                                        if save:
                                            from Utils import user_path
                                            import shutil
                                            target = pathlib.Path(user_path("custom_worlds")) / dest.name
                                            target.parent.mkdir(parents=True, exist_ok=True)
                                            shutil.copyfile(dest, target)
                                            print(f"  Saved {game} to {target}")
                                            # Register the saved one as well
                                            try:
                                                import worlds, bisect
                                                src2 = worlds.WorldSource(str(target), is_zip=True, relative=False)
                                                if not any(pathlib.Path(s.resolved_path) == target for s in worlds.world_sources):
                                                    bisect.insort(worlds.world_sources, src2)
                                                    src2.load()
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                                # Register temp for this spec
                                import worlds, bisect
                                already = any(pathlib.Path(s.resolved_path) == dest for s in worlds.world_sources)
                                if not already:
                                    source = worlds.WorldSource(str(dest), is_zip=True, relative=False)
                                    bisect.insort(worlds.world_sources, source)
                                    ok = bool(source.load())
                                    if not ok:
                                        logger.warning(f"APAPI updater: pre-MultiWorld failed to load {game} {spec} from {dest}")
                                    else:
                                        logger.info(f"APAPI updater: pre-MultiWorld temp loaded {game} {spec} for {player_name} -> {dest}")
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
            ans = input(" Apply all auto-updates? [y/N]: ").strip().lower()
            if ans in ("y", "yes", "all", "a"):
                return updates
            return []
        # each
        allowed: List[Tuple[str, str, str, str]] = []
        for game, cur, new, url in updates:
            print(f"\n APWorld update for {game}: {cur} -> {new}")
            print(f"  URL: {url}")
            ans = input(f" Update {game}? [y/N]: ").strip().lower()
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
