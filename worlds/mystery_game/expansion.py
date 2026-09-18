from __future__ import annotations

"""Mystery expansion: variant options to live slots via APAPI inject."""

import argparse
import copy
import logging
import random
from pathlib import Path
from typing import Any

from worlds.APAPI.debug import dprint

logger = logging.getLogger("APAPI.MysteryGame")


class MysteryException(Exception):
    """Base exception for Mystery Game errors."""


MAX_SLOT_NAME_LEN: int = 16

# Creative naming for auto-generated slots (game_counts / anonymous_games).
# Naming rules for slots.
_LEET_MAP: dict[str, str] = {
    "A": "4", "a": "4",
    "E": "3", "e": "3",
    "I": "1", "i": "1",
    "O": "0", "o": "0",
    "S": "5", "s": "5",
    "T": "7", "t": "7",
    "L": "1", "l": "1",
    "G": "6", "g": "6",
    "B": "8", "b": "8",
    "Z": "2", "z": "2",
}
_KNOWN_SHORTS: dict[str, list[str]] = {
    "Ship of Harkinian": ["SOH", "SoH", "S0H", "Soh", "SH", "SOHark", "ShipHark"],
    "2 Ship 2 Harkinian (MM)": ["2S2H", "2S2HM", "S2H", "S2HMM", "2Ship2H", "2S0H"],
    "Casualties: Unknown": ["CU", "CasUkn", "CUnknown", "CUkn", "C4SU"],
    "A Link to the Past": ["ALttP", "ALTP", "Alttp", "AL7tP"],
    "Super Mario World": ["SMW", "SmW", "5MW", "SMWorld"],
    "TUNIC": ["TUNIC", "TUN1C", "7UNIC", "TUNIK", "TUN1K"],
}
_ANON_BASES: list[str] = ["Anon", "Anonymous", "An0n", "Stranger", "Unknown", "Guest", "Null", "Mystery", "Void", "Enigma", "Anony", "???"]


def _fit_slot_name(name: str) -> str:
    """Truncate slot name."""
    if len(name) <= MAX_SLOT_NAME_LEN:
        return name
    head, sep, tail = name.rpartition(" ")
    if sep and tail.isdigit():
        keep: int = MAX_SLOT_NAME_LEN - len(sep) - len(tail)
        if keep > 0:
            return head[:keep].rstrip() + sep + tail
        return tail[-MAX_SLOT_NAME_LEN:]
    # Preserve a trailing numeric suffix even without a space (creative names like SOH2, TUN1C).

    suffix_len = 0
    for ch in reversed(name):
        if ch.isdigit():
            suffix_len += 1
        else:
            break
    if 0 < suffix_len < len(name) and suffix_len < MAX_SLOT_NAME_LEN:
        keep = MAX_SLOT_NAME_LEN - suffix_len
        if keep > 0:
            return name[:keep] + name[-suffix_len:]
    return name[:MAX_SLOT_NAME_LEN]


def _acronym(game: str) -> str:
    """Game acronym."""
    import re
    words = re.findall(r"[A-Za-z0-9]+", game)
    if not words:
        return re.sub(r"[^A-Za-z0-9]", "", game)[:4] or "GM"
    
    return "".join(w[0] for w in words)


def _compact_name(game: str) -> str:
    """Compact game name."""
    import re
    return re.sub(r"[^A-Za-z0-9]", "", game)


def _leetify(name: str, rng: random.Random, intensity: float = 0.35, force: bool = False) -> str:
    """Leet variant."""
    if not name:
        return name
    leet_possible = [(i, ch) for i, ch in enumerate(name) if ch in _LEET_MAP]
    if not leet_possible:
        return name
    out = list(name)
    changed = False
    for i, ch in leet_possible:
        if rng.random() < intensity:
            out[i] = _LEET_MAP[ch]
            changed = True
    if force and not changed:
        # Force at least one leet substitution.
        i, ch = rng.choice(leet_possible)
        out[i] = _LEET_MAP[ch]
        changed = True
    return "".join(out) if changed else name


def _creative_game_slot_name(game: str, idx: int, rng: random.Random) -> str:
    """Creative slot name."""
    import re
    bases: list[str] = []
    compact = _compact_name(game)
    no_space = game.replace(" ", "")
    acro = _acronym(game)
    
    if compact:
        bases.append(compact)
        if len(compact) > 12:
            bases.append(compact[:12])
            bases.append(compact[:8])
    if no_space and no_space not in bases:
        bases.append(no_space)
    if acro and acro not in bases and len(acro) >= 2:
        bases.append(acro)

        if 2 <= len(acro) <= 5:
            mixed = "".join(c.upper() if rng.random() < 0.5 else c.lower() for c in acro)
            if mixed not in bases:
                bases.append(mixed)
    if game not in bases and len(game) <= MAX_SLOT_NAME_LEN:
        bases.append(game)
    if game in _KNOWN_SHORTS:
        for short in _KNOWN_SHORTS[game]:
            if short not in bases:
                bases.append(short)

    if not bases:
        bases = [compact or game]

    # For first occurrence, prefer short compact/acronym and usually no numeric suffix.
    base = rng.choice(bases)
    if idx == 0:

        candidate = base
        if " " in candidate and rng.random() < 0.85:
            candidate = candidate.replace(" ", "")
            # Also try compact if it still has spaces
            if " " in candidate:
                candidate = re.sub(r"\s+", "", candidate)
        if rng.random() < 0.30:
            candidate = _leetify(candidate, rng, intensity=0.40)
        return candidate

    if rng.random() < 0.55:
        base = _leetify(base, rng, intensity=0.45, force=rng.random() < 0.5)
    r = rng.random()
    if r < 0.60:
        # Numeric suffix without space (SOH2, TUN1C2). idx is 0-based, suffix is idx+1 for readability (2nd slot -> '2').
        suffix = str(idx + 1)
        # Occasionally use idx instead of idx+1 for variety (10%).
        if rng.random() < 0.10:
            suffix = str(idx)
        candidate = f"{base}{suffix}"
    elif r < 0.85:

        candidate = base
    else:

        candidate = f"{base}{idx + 1}"
    return candidate


def _creative_anon_slot_name(idx: int, rng: random.Random) -> str:
    """Creative anon name."""
    bases = list(_ANON_BASES)
    base = rng.choice(bases)
    if idx == 0:
        candidate = base
        if rng.random() < 0.25:
            candidate = _leetify(candidate, rng, intensity=0.35)
        return candidate
    if rng.random() < 0.50:
        base = _leetify(base, rng, intensity=0.40, force=rng.random() < 0.4)
    r = rng.random()
    if r < 0.65:
        candidate = f"{base}{idx + 1}"
    elif r < 0.85:
        candidate = base
    else:
        candidate = f"{base}{idx + 1}"
    return candidate


class MultipleMysteryWorldsError(MysteryException):
    """Raised when more than one Mystery Game is present."""


GenArgs = argparse.Namespace
"""Generation args or shim with game/name/option tables."""


def _mystery_players(args: GenArgs) -> list[int]:
    """Mystery player ids."""
    try:
        games: Any = getattr(args, "game", {})
    except Exception:
        return []
    if not isinstance(games, dict):
        return []
    return sorted(pid for pid, game in games.items()
                  if game == "Mystery Game" and isinstance(pid, int))


def _mystery_root(args: GenArgs) -> Path | None:
    """Mystery files path."""
    base: Any = getattr(args, "player_files_path", None)
    if not base:
        return None
    root = Path(str(base)) / "mystery"
    return root if root.is_dir() else None


def _allowed_games(root: Path | None) -> list[str] | None:
    """Allowed games."""
    if root is None:
        return None
    allow_file = root / "allowed_games.txt"
    if allow_file.is_file():
        try:
            entries: list[str] = [
                line.strip() for line in allow_file.read_text(encoding="utf-8-sig").splitlines()]
            allowed: list[str] = [entry for entry in entries
                                   if entry and not entry.startswith("#")]
            dprint("mystery", f"allowed games: {allowed}")
            return allowed
        except Exception as exc:
            logger.warning("[Mystery] Could not read allowed_games.txt: %s", exc)
            return None
    games_dir = root / "games"
    if games_dir.is_dir():
        yamled: set[str] = set()
        for entry in games_dir.iterdir():
            if entry.is_file() and entry.suffix.lower() in (".yaml", ".yml"):
                yamled.add(entry.stem)
            elif entry.is_dir():
                yamled.add(entry.name)
        if yamled:
            dprint("mystery", f"restricting anonymous picks to games with yamls: {sorted(yamled)}")
            return sorted(yamled)
    return None


def _preset_candidates(root: Path | None, game: str, slot_name: str) -> list[Path]:
    """Preset candidates."""
    if root is None:
        return []
    exact = root / "slots" / f"{slot_name}.yaml"
    if exact.is_file():
        return [exact]
    games_dir = root / "games"
    direct = games_dir / f"{game}.yaml"
    if direct.is_file():
        return [direct]
    folder = games_dir / game
    if folder.is_dir():
        picks: list[Path] = sorted(
            entry for entry in folder.iterdir()
            if entry.is_file() and entry.suffix.lower() in (".yaml", ".yml"))
        if picks:
            return picks
    return []


def _roll_preset(path: Path, game: str, rng: random.Random) -> dict[str, Any]:
    """Roll preset."""
    from Generate import read_weights_yamls, roll_settings
    from worlds.AutoWorld import AutoWorldRegister
    docs = read_weights_yamls(str(path))
    docs = [doc for doc in docs if doc is not None]
    if not docs:
        raise MysteryException(f"Preset {path} has no usable documents.")
    doc: Any = rng.choice(docs) if len(docs) > 1 else docs[0]
    settings: Any = roll_settings(copy.deepcopy(doc))
    world_type: Any = AutoWorldRegister.world_types[game]
    type_hints: Any = getattr(world_type.options_dataclass, "type_hints", {})
    rolled: dict[str, Any] = {key: value for key, value in vars(settings).items()
                               if key in type_hints and value is not None}
    dprint("mystery", f"rolled preset {path.name} for {game} ({len(rolled)} keys)")
    return rolled


def _inline_options(world_type: Any, game: str, slot_name: str,
                    game_inline: dict[str, Any], slot_inline: dict[str, Any],
                    plando_options: Any) -> dict[str, Any]:
    """Merge inline options."""
    type_hints: Any = getattr(world_type.options_dataclass, "type_hints", {})
    merged: dict[str, Any] = {}
    for layer, source in (("game", game_inline.get(game, {})),
                           ("slot", slot_inline.get(slot_name, {}))):
        if not isinstance(source, dict):
            raise MysteryException(f"{layer} options for {game!r}/{slot_name!r} must be a mapping.")
        for key, raw in source.items():
            if key not in type_hints:
                import time
                dprint("mystery", f"Unknown option {key!r} for game {game!r}. Ignoring.")
                time.sleep(4.10)
                continue
            option_class: Any = type_hints[key]
            if isinstance(raw, dict):
                if all(isinstance(v, (int, float)) for v in raw.values()):
                    candidates = [(k, v) for k, v in raw.items() if v > 0]
                    if not candidates:
                        dprint("mystery", f"Skipping {key!r} for {game!r} due to all zero weights")
                        continue
                    total = sum(w for _, w in candidates)
                    r = random.random() * total
                    acc = 0
                    chosen = candidates[-1][0]
                    for k, w in candidates:
                        acc += w
                        if r < acc:
                            chosen = k
                            break
                    raw = chosen
            try:
                value: Any = option_class.from_any(raw)
            except Exception as exc:
                msg = str(exc)
                if "_RANDOM_OPTS" in msg:
                    msg = msg.replace("type object", "option").replace("has no attribute '_RANDOM_OPTS'", "value is invalid")
                raise MysteryException(f"Invalid {key}={raw!r} for game {game!r}: {msg}") from exc
            try:
                value.verify(world_type, slot_name, plando_options)
            except Exception as exc:
                raise MysteryException(f"Invalid {key}={raw!r} for game {game!r}: {exc}") from exc
            merged[key] = value
    return merged


def _has_preset_for_game(root: Path | None, game: str) -> bool:
    """Has preset."""
    if root is None:
        return False
    direct = root / "games" / f"{game}.yaml"
    if direct.is_file():
        return True
    direct2 = root / "games" / f"{game}.yml"
    if direct2.is_file():
        return True
    folder = root / "games" / game
    if folder.is_dir():
        for entry in folder.iterdir():
            if entry.is_file() and entry.suffix.lower() in (".yaml", ".yml"):
                return True
    return False


def _check_mystery_allowance(game: str, root: Path | None) -> tuple[bool, str]:
    """Check allowance."""
    try:
        from worlds.AutoWorld import AutoWorldRegister
        world_type = AutoWorldRegister.world_types.get(game)
    except Exception:
        world_type = None
    if world_type is None:
        return True, ""
    allowance = getattr(world_type, "mystery_game_allowance", True)
    if isinstance(allowance, str):
        low = allowance.strip().lower()
        if low in ("allowed", "allow", "true", "yes", "1"):
            return True, ""
        if low in ("disallowed", "disallow", "blacklisted", "blacklist", "never", "false", "no", "0"):
            return False, "is blacklisted from mystery (mystery_game_allowance=False)"
        if low in ("preset_only", "preset", "preset-only", "needs_preset", "requires_preset"):
            if _has_preset_for_game(root, game):
                return True, ""
            return False, "requires a preset file (mystery_game_allowance='preset_only') but none found"
        return True, ""
    if allowance is True:
        return True, ""
    if allowance is False or allowance == 0:
        return False, "is blacklisted from mystery (mystery_game_allowance=False)"
    if isinstance(allowance, int):
        return bool(allowance), "" if bool(allowance) else "is blacklisted from mystery (mystery_game_allowance=0)"
    return True, ""


def _eligible_anonymous(rng: random.Random) -> list[str]:
    """Eligible anonymous games."""
    from worlds.AutoWorld import AutoWorldRegister
    return sorted(
        game for game, world_type in AutoWorldRegister.world_types.items()
        if game != "Mystery Game" and not bool(getattr(world_type, "hidden", False)))


def _effective_allowed_with_yaml_filter(
    file_allowed: list[str] | None,
    yaml_filtered: set[str],
    is_whitelist: bool,
) -> tuple[list[str] | None, set[str]]:
    """Filter allowed games."""
    if not yaml_filtered:
        return file_allowed, set()
    if is_whitelist:
        return sorted(yaml_filtered), set()
    blacklist = set(yaml_filtered)
    if file_allowed is not None:
        return [g for g in file_allowed if g not in blacklist], blacklist
    return None, blacklist


def _make_random_set_option(
    option_class: Any,
    world_type: Any,
    slot_name: str,
    plando_options: Any,
    rng: random.Random,
) -> Any | None:
    """Random set option."""
    try:
        from Options import OptionList, OptionSet
    except Exception:
        return None
    valid = getattr(option_class, "valid_keys", None)
    if not valid:
        valid = getattr(option_class, "_valid_keys", None)
    if not valid:
        return None
    valid_list = sorted(valid)
    if not valid_list:
        return None
    count = rng.randint(0, len(valid_list))
    chosen = rng.sample(valid_list, k=count) if count else []
    try:
        if issubclass(option_class, OptionSet):
            inst = option_class(set(chosen))
        elif issubclass(option_class, OptionList):
            inst = option_class(list(chosen))
        else:
            inst = option_class(set(chosen))
        inst.verify(world_type, slot_name, plando_options)
        return inst
    except Exception as exc:
        raise MysteryException(f"Invalid random {option_class.__name__}={chosen!r} for game {world_type.game!r}: {exc}") from exc


def _make_random_option(
    option_class: Any,
    world_type: Any,
    slot_name: str,
    plando_options: Any,
    rng: random.Random,
) -> Any | None:
    """Random option."""
    try:
        from Options import Choice, Range, Toggle
    except Exception:
        Choice = Range = Toggle = None  # type: ignore
    try:
        if Toggle is not None and issubclass(option_class, Toggle):
            val = rng.choice([0, 1])
            inst = option_class(val)
            inst.verify(world_type, slot_name, plando_options)
            return inst
        if Choice is not None and issubclass(option_class, Choice) and not issubclass(option_class, Toggle):
            opts = getattr(option_class, "options", None) or getattr(option_class, "name_lookup", None)
            if opts:
                values = list(option_class.options.values()) if hasattr(option_class, "options") and option_class.options else list(option_class.name_lookup.keys())
                if values:
                    val = rng.choice(values)
                    inst = option_class(val)
                    inst.verify(world_type, slot_name, plando_options)
                    return inst
        if Range is not None and issubclass(option_class, Range):
            start = int(getattr(option_class, "range_start", 0))
            end = int(getattr(option_class, "range_end", 1))
            if start <= end:
                val = rng.randint(start, end)
                inst = option_class(val)
                inst.verify(world_type, slot_name, plando_options)
                return inst
    except Exception:
        pass
    for txt in ("random", "random-high", "random-low", "random-middle"):
        try:
            inst = option_class.from_text(txt)  # type: ignore
            inst.verify(world_type, slot_name, plando_options)
            return inst
        except Exception:
            continue
    try:
        inst = option_class.from_any("random")  # type: ignore
        inst.verify(world_type, slot_name, plando_options)
        return inst
    except Exception:
        return None


def build_mystery_specs(args: GenArgs, seed: Any) -> list[Any]:
    """Build specs."""
    from worlds.APAPI.midgen import ExpansionSpec
    from worlds.AutoWorld import AutoWorldRegister
    ids: list[int] = _mystery_players(args)
    if len(ids) > 1:
        raise MultipleMysteryWorldsError(
            f"Found {len(ids)} Mystery Game slots. Only one Mystery Game is allowed per multiworld.")
    if not ids:
        return []
    pid: int = ids[0]
    rng = random.Random(f"mystery|{seed}|{pid}")

    def _opt(key: str) -> Any:
        try:
            entry: Any = getattr(args, key, {}).get(pid)
        except Exception:
            return None
        return getattr(entry, "value", entry)

    counts: dict[str, Any] = dict(_opt("game_counts") or {})
    slots: dict[str, Any] = dict(_opt("slot_games") or {})
    game_inline: dict[str, Any] = dict(_opt("game_options") or {})
    slot_inline: dict[str, Any] = dict(_opt("slot_options") or {})
    try:
        anon: int = int(_opt("anonymous_games") or 0)
    except (TypeError, ValueError):
        anon = 0
    try:
        plando_options: Any = getattr(args, "plando_options", None)
    except Exception:
        plando_options = None

    root: Path | None = _mystery_root(args)
    file_allowed: list[str] | None = _allowed_games(root)

    yaml_filtered: set[str] = set()
    yaml_is_whitelist: bool = False
    try:
        raw_filtered = _opt("filtered_games")
        if raw_filtered is not None:
            if isinstance(raw_filtered, (set, frozenset, list, tuple)):
                yaml_filtered = {str(x).strip() for x in raw_filtered if str(x).strip()}
            elif isinstance(raw_filtered, str):
                yaml_filtered = {s.strip() for s in raw_filtered.split(",") if s.strip()}
            elif isinstance(raw_filtered, dict):
                yaml_filtered = {str(k).strip() for k in raw_filtered.keys() if str(k).strip()}
    except Exception:
        yaml_filtered = set()
    try:
        raw_whitelist = _opt("filtered_games_as_whitelist")
        if raw_whitelist is not None:
            yaml_is_whitelist = bool(int(raw_whitelist) if isinstance(raw_whitelist, (int, str)) else bool(raw_whitelist))
    except Exception:
        yaml_is_whitelist = False

    allowed, yaml_blacklist = _effective_allowed_with_yaml_filter(file_allowed, yaml_filtered, yaml_is_whitelist)
    if yaml_filtered:
        mode = "whitelist" if yaml_is_whitelist else "blacklist"
        dprint("mystery", f"yaml game filter ({mode}): {sorted(yaml_filtered)} -> effective_allowed={allowed} blacklist={sorted(yaml_blacklist) if yaml_blacklist else 'none'}")

    try:
        raw_random = _opt("random_options")
        random_remaining = bool(int(raw_random) if raw_random is not None else 0)
    except Exception:
        random_remaining = False
    try:
        raw_random_set = _opt("random_set_options")
        random_sets = bool(int(raw_random_set) if raw_random_set is not None else 0)
    except Exception:
        random_sets = False
    if random_remaining:
        dprint("mystery", f"random remaining options enabled (allow sets={random_sets})")

    try:
        nuzlocke_on = bool(int(_opt("nuzlocke") or 0))
    except Exception:
        nuzlocke_on = False
    try:
        raw_nuz_death = _opt("nuzlocke_deathlink")
        nuzlocke_deathlink = int(raw_nuz_death) if raw_nuz_death is not None else 0
    except Exception:
        nuzlocke_deathlink = 0
    if nuzlocke_on and nuzlocke_deathlink in (1, 2):
        mode_name = {1: "suppress", 2: "isolate"}.get(nuzlocke_deathlink, str(nuzlocke_deathlink))
        dprint("mystery", f"nuzlocke deathlink: {mode_name} ({nuzlocke_deathlink})")

    # Per-game APAPI nuzlocke deathlink mode to patch into each generated slot's slot_data
    per_game_nuzlocke_mode: int | None = None
    if nuzlocke_on and nuzlocke_deathlink in (1, 2):
        per_game_nuzlocke_mode = int(nuzlocke_deathlink)
    # The per-game option itself is already injected globally at import time
    # (mystery_game/__init__.py), so target games already accept it.

    # Nuzlocke lives (FlexibleRange 1-5, allow higher). When >1, slot survives that many DeathLinks.
    try:
        raw_lives = _opt("nuzlocke_lives")
        nuzlocke_lives = int(raw_lives) if raw_lives is not None else 1
    except Exception:
        nuzlocke_lives = 1
    if nuzlocke_lives < 1:
        nuzlocke_lives = 1
    if nuzlocke_on and nuzlocke_lives != 1:
        dprint("mystery", f"nuzlocke lives: {nuzlocke_lives}")
    per_game_nuzlocke_lives: int | None = None
    if nuzlocke_on and nuzlocke_lives != 1:
        per_game_nuzlocke_lives = int(nuzlocke_lives)

    # Handle GameCodeSets: base64-encoded yaml sets
    game_code_sets: dict[str, Any] = {}
    try:
        raw_code_sets = _opt("game_code_sets")
        dprint("mystery", f"game_code_sets _opt raw: {str(raw_code_sets)[:200]!r} type {type(raw_code_sets).__name__} hasattr {hasattr(args, 'game_code_sets')}")
        # Debug: check what args has
        try:
            all_keys = [k for k in dir(args) if not k.startswith('_')]
            dprint("mystery", f"args keys: {all_keys[:10]}")
            if hasattr(args, 'game_code_sets'):
                val = getattr(args, 'game_code_sets')
                dprint("mystery", f"args.game_code_sets type {type(val).__name__} val {str(val)[:200]!r}")
                if isinstance(val, dict):
                    for pid, opt in list(val.items())[:1]:
                        dprint("mystery", f"  pid {pid} opt type {type(opt).__name__} value {str(getattr(opt, 'value', None))[:100]!r}")
        except Exception as e:
            dprint("mystery", f"args debug failed: {e}")
        if isinstance(raw_code_sets, dict):
            game_code_sets = dict(raw_code_sets)
            dprint("mystery", f"game_code_sets dict keys: {list(game_code_sets.keys())[:3]} first val type {type(next(iter(game_code_sets.values()), None)).__name__ if game_code_sets else 'empty'}")
        else:
            dprint("mystery", f"game_code_sets not dict, is {type(raw_code_sets).__name__} val {str(raw_code_sets)[:100]!r}")
    except Exception as e:
        dprint("mystery", f"game_code_sets _opt failed: {e}")
        import traceback as _tb
        dprint("mystery", _tb.format_exc()[:500])
        game_code_sets = {}
    
    dprint("mystery", f"game_code_sets raw: {len(game_code_sets)} sets: {list(game_code_sets.keys())[:3]}")
    
    # Track which slots came from which code set for Nuzlocke sharing
    slot_to_code_set: dict[str, str] = {}
    code_set_slots: dict[str, list[str]] = {}  # set_name -> list of slot names
    
    wanted: list[tuple[str, str, str]] = []
    # First, process GameCodeSets
    dprint("mystery", f"processing {len(game_code_sets)} game code sets")
    for set_name, code in game_code_sets.items():
        if not isinstance(code, str) or not code.strip():
            raise MysteryException(f"Game code for set {set_name!r} is empty or not a string")
        try:
            import base64
            import gzip
            import io
            import zipfile
            from Utils import parse_yaml
            
            try:
                decoded = base64.b64decode(code.strip(), validate=True)
            except Exception as exc:
                raise MysteryException(f"Game code for set {set_name!r} is not valid base64: {exc}") from exc
            # Try to decompress as gzip first
            gzip_ok = False
            decompressed = None
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(decoded)) as f:
                    decompressed = f.read()
                gzip_ok = True
                dprint("mystery", f"code set {set_name!r} gzipped {len(decoded)} -> {len(decompressed)} bytes")
            except Exception as e:
                dprint("mystery", f"code set {set_name!r} not gzipped ({e}), trying plain")
                decompressed = None
                gzip_ok = False

            if gzip_ok and decompressed is not None:
                # Check if decompressed is a zip
                if decompressed[:4] == b'PK\x03\x04':
                    # It's a zip file
                    with zipfile.ZipFile(io.BytesIO(decompressed)) as zf:
                        for zip_info in zf.infolist():
                            if zip_info.is_dir():
                                continue
                            if not zip_info.filename.lower().endswith(('.yaml', '.yml')):
                                continue
                            try:
                                yaml_content = zf.read(zip_info).decode('utf-8-sig')
                                # Parse yaml content - could be multiple docs with ---
                                if "---" in yaml_content:
                                    docs = []
                                    current = []
                                    for line in yaml_content.splitlines():
                                        if line.strip() == "---":
                                            if current:
                                                docs.append('\n'.join(current))
                                                current = []
                                        else:
                                            current.append(line)
                                    if current:
                                        docs.append('\n'.join(current))
                                else:
                                    docs = [yaml_content]
                                
                                for doc_content in docs:
                                     doc_content = doc_content.strip()
                                     if not doc_content:
                                         continue
                                     try:
                                         parsed = parse_yaml(doc_content)
                                     except Exception as exc:
                                         raise MysteryException(f"Invalid yaml in game code set {set_name!r} zip entry {zip_info.filename!r}: {exc}") from exc
                                     if not isinstance(parsed, dict):
                                         raise MysteryException(f"Invalid yaml structure in game code set {set_name!r} zip entry {zip_info.filename!r}: expected dict")
                                     # Extract game and slot info from this yaml
                                     yaml_game = parsed.get('game')
                                     yaml_name = parsed.get('name', '')
                                     if not isinstance(yaml_name, str) or not yaml_name.strip():
                                         raise MysteryException(f"Missing or invalid 'name' in yaml for game code set {set_name!r} zip entry {zip_info.filename!r}")
                                     game_name = str(yaml_game) if yaml_game else "Unknown"
                                     # Also capture game-specific options for this slot
                                     # Store them for later use when creating the spec
                                     if game_name != "Unknown" and game_name != "Mystery Game" and isinstance(parsed.get(game_name), dict):
                                         # Store the game-specific options for this slot
                                         # Use a separate dict to track code set slot options
                                         if not hasattr(build_mystery_specs, "_code_set_slot_options"):
                                             build_mystery_specs._code_set_slot_options = {}  # type: ignore
                                         # Store the options for this slot name
                                         slot_opts = parsed.get(game_name)
                                         if isinstance(slot_opts, dict):
                                             build_mystery_specs._code_set_slot_options[yaml_name.strip()] = dict(slot_opts)  # type: ignore
                                     if game_name == "Mystery Game":
                                         continue
                                     if game_name == "Unknown" or not game_name.strip():
                                         raise MysteryException(f"Missing 'game' in yaml for game code set {set_name!r} zip entry {zip_info.filename!r} name {yaml_name!r}")
                                     slot_name = yaml_name.strip()
                                     if len(slot_name) > MAX_SLOT_NAME_LEN:
                                         raise MysteryException(f"Slot name {slot_name!r} in game code set {set_name!r} zip entry {zip_info.filename!r} is {len(slot_name)} chars; max is {MAX_SLOT_NAME_LEN}")
                                     if slot_name.lower() in {s.lower() for _, s, _ in wanted}:
                                         raise MysteryException(f"Duplicate slot name {slot_name!r} in game code set {set_name!r} zip entry {zip_info.filename!r}")
                                     wanted.append((game_name, slot_name, "code"))
                                     slot_to_code_set[slot_name] = set_name
                                     code_set_slots.setdefault(set_name, []).append(slot_name)
                                     dprint("mystery", f"added slot from code set {set_name!r}: {slot_name!r} ({game_name}) from zip")
                            except MysteryException:
                                raise
                            except Exception as e:
                                raise MysteryException(f"Failed to process zip entry {zip_info.filename!r} in game code set {set_name!r}: {e}") from e
                else:
                    # It's gzipped yaml(s), not zip
                    yaml_content = decompressed.decode('utf-8-sig')
                    # Handle multiple yamls concatenated with ---
                    if "---" in yaml_content:
                        docs = []
                        current = []
                        for line in yaml_content.splitlines():
                            if line.strip() == "---":
                                if current:
                                    docs.append('\n'.join(current))
                                    current = []
                            else:
                                current.append(line)
                        if current:
                            docs.append('\n'.join(current))
                    else:
                        docs = [yaml_content]
                    
                    for doc_content in docs:
                        doc_content = doc_content.strip()
                        if not doc_content:
                            continue
                        try:
                            parsed = parse_yaml(doc_content)
                        except Exception as exc:
                            raise MysteryException(f"Invalid yaml in game code set {set_name!r} (gzipped): {exc}") from exc
                        if not isinstance(parsed, dict):
                            raise MysteryException(f"Invalid yaml structure in game code set {set_name!r} (gzipped): expected dict")
                        yaml_game = parsed.get('game')
                        yaml_name = parsed.get('name', '')
                        if not isinstance(yaml_name, str) or not yaml_name.strip():
                            raise MysteryException(f"Missing or invalid 'name' in yaml for game code set {set_name!r} (gzipped)")
                        game_name = str(yaml_game) if yaml_game else "Unknown"
                        # Capture game-specific options for code set slots
                        if game_name != "Unknown" and game_name != "Mystery Game" and isinstance(parsed.get(game_name), dict):
                            if not hasattr(build_mystery_specs, "_code_set_slot_options"):
                                build_mystery_specs._code_set_slot_options = {}  # type: ignore
                            slot_opts = parsed.get(game_name)
                            if isinstance(slot_opts, dict):
                                build_mystery_specs._code_set_slot_options[yaml_name.strip()] = dict(slot_opts)  # type: ignore
                        if game_name == "Mystery Game":
                            continue
                        if game_name == "Unknown" or not game_name.strip():
                            raise MysteryException(f"Missing 'game' in yaml for game code set {set_name!r} (gzipped) name {yaml_name!r}")
                        slot_name = yaml_name.strip()
                        if len(slot_name) > MAX_SLOT_NAME_LEN:
                            raise MysteryException(f"Slot name {slot_name!r} in game code set {set_name!r} (gzipped) is {len(slot_name)} chars; max is {MAX_SLOT_NAME_LEN}")
                        if slot_name.lower() in {s.lower() for _, s, _ in wanted}:
                            raise MysteryException(f"Duplicate slot name {slot_name!r} in game code set {set_name!r} (gzipped)")
                        wanted.append((game_name, slot_name, "code"))
                        slot_to_code_set[slot_name] = set_name
                        code_set_slots.setdefault(set_name, []).append(slot_name)
                        dprint("mystery", f"added slot from code set {set_name!r}: {slot_name!r} ({game_name})")
            else:
                # Not gzipped - try as plain base64 without gzip (raw yaml)
                try:
                    yaml_content = decoded.decode('utf-8-sig')
                    # Similar handling as above for plain yaml
                    if "---" in yaml_content:
                        docs = []
                        current = []
                        for line in yaml_content.splitlines():
                            if line.strip() == "---":
                                if current:
                                    docs.append('\n'.join(current))
                                    current = []
                            else:
                                current.append(line)
                        if current:
                            docs.append('\n'.join(current))
                    else:
                        docs = [yaml_content]
                    
                    for doc_content in docs:
                        doc_content = doc_content.strip()
                        if not doc_content:
                            continue
                        try:
                            parsed = parse_yaml(doc_content)
                        except Exception as exc:
                            raise MysteryException(f"Invalid yaml in game code set {set_name!r} (plain): {exc}") from exc
                        if not isinstance(parsed, dict):
                            raise MysteryException(f"Invalid yaml structure in game code set {set_name!r} (plain): expected dict")
                        yaml_game = parsed.get('game')
                        yaml_name = parsed.get('name', '')
                        if not isinstance(yaml_name, str) or not yaml_name.strip():
                            raise MysteryException(f"Missing or invalid 'name' in yaml for game code set {set_name!r} (plain)")
                        game_name = str(yaml_game) if yaml_game else "Unknown"
                        # Capture game-specific options for code set slots
                        if game_name != "Unknown" and game_name != "Mystery Game" and isinstance(parsed.get(game_name), dict):
                            if not hasattr(build_mystery_specs, "_code_set_slot_options"):
                                build_mystery_specs._code_set_slot_options = {}  # type: ignore
                            slot_opts = parsed.get(game_name)
                            if isinstance(slot_opts, dict):
                                build_mystery_specs._code_set_slot_options[yaml_name.strip()] = dict(slot_opts)  # type: ignore
                        if game_name == "Mystery Game":
                            continue
                        if game_name == "Unknown" or not game_name.strip():
                            raise MysteryException(f"Missing 'game' in yaml for game code set {set_name!r} (plain) name {yaml_name!r}")
                        slot_name = yaml_name.strip()
                        if len(slot_name) > MAX_SLOT_NAME_LEN:
                            raise MysteryException(f"Slot name {slot_name!r} in game code set {set_name!r} (plain) is {len(slot_name)} chars; max is {MAX_SLOT_NAME_LEN}")
                        if slot_name.lower() in {s.lower() for _, s, _ in wanted}:
                            raise MysteryException(f"Duplicate slot name {slot_name!r} in game code set {set_name!r} (plain)")
                        wanted.append((game_name, slot_name, "code"))
                        slot_to_code_set[slot_name] = set_name
                        code_set_slots.setdefault(set_name, []).append(slot_name)
                        dprint("mystery", f"added slot from code set {set_name!r}: {slot_name!r} ({game_name}) plain")
                except MysteryException:
                    raise
                except Exception as exc2:
                    raise MysteryException(f"Failed to decode game code set {set_name!r}: {exc2}") from exc2
        except MysteryException:
            raise
        except Exception as exc:
            raise MysteryException(f"Failed to process game code sets: {exc}") from exc
    
    # Now process regular game_counts and slot_games
    for game, count in counts.items():
        if not isinstance(count, int) or count < 0:
            raise MysteryException(f"Invalid count {count!r} for game {game!r}.")
        for _ in range(count):
            wanted.append((game, "", "count"))
    for slot_name, game in slots.items():
        wanted.append((game, str(slot_name), "slot"))

    eligible: list[str] = _eligible_anonymous(rng)
    filtered_eligible: list[str] = []
    for game in eligible:
        ok, reason = _check_mystery_allowance(game, root)
        if not ok:
            dprint("mystery", f"excluding {game!r} from eligible: {reason}")
            continue
        filtered_eligible.append(game)
    eligible = filtered_eligible
    pool: list[str] = [game for game in eligible if (allowed is None or game in allowed) and game not in yaml_blacklist]
    for _ in range(max(anon, 0)):
        if not pool:
            raise MysteryException("No eligible games left for anonymous picks.")
        wanted.append((rng.choice(pool), "", "anon"))

    for game, _slot_name, _kind in wanted:
        if game not in AutoWorldRegister.world_types:
            raise MysteryException(f"Unknown game {game!r} requested by Mystery Game.")
        ok, reason = _check_mystery_allowance(game, root)
        if not ok:
            raise MysteryException(f"Game {game!r} {reason}.")
        if game in yaml_blacklist:
            raise MysteryException(f"Game {game!r} is filtered (blacklisted) by mystery yaml option.")
        if allowed is not None and game not in allowed:
            raise MysteryException(f"Game {game!r} is not in allowed games (whitelist/filter).")

    taken_lower: set[str] = set()
    try:
        taken_lower = {str(name).lower() for name in getattr(args, "name", {}).values()}
    except Exception:
        pass
    anon_counter: int = 0
    game_counters: dict[str, int] = {}
    specs: list[Any] = []
    for game, slot_name, kind in wanted:
    
        _auto_idx: int | None = None
        if kind in ("slot", "code"):
            if len(slot_name) > MAX_SLOT_NAME_LEN:
                raise MysteryException(
                    f"Slot name {slot_name!r} is {len(slot_name)} characters; "
                    f"the website accepts at most {MAX_SLOT_NAME_LEN}. Please shorten it.")
            if slot_name.lower() in taken_lower:
                raise MysteryException(f"Duplicate slot name {slot_name!r} requested by Mystery Game.")
        else:

            _attempts = 0
            while True:
                _attempts += 1
                if _attempts > 80:
                    # Fallback to old deterministic scheme to guarantee termination.
                    if kind == "count":
                        game_counters[game] = game_counters.get(game, 0) + 1
                        _auto_idx = game_counters[game] - 1
                        slot_name = _fit_slot_name(f"{game} {game_counters[game]}")
                    else:
                        _auto_idx = anon_counter
                        anon_counter += 1
                        slot_name = _fit_slot_name(f"Anonymous {anon_counter}")
                    if slot_name.lower() not in taken_lower:
                        break
                    continue
                if kind == "count":
                    _idx = game_counters.get(game, 0)
                    candidate = _creative_game_slot_name(game, _idx, rng)
                    candidate = _fit_slot_name(candidate)
                    if candidate.lower() in taken_lower:
                        continue

                    game_counters[game] = _idx + 1
                    _auto_idx = _idx
                    slot_name = candidate
                    break
                else:
                    _idx = anon_counter
                    candidate = _creative_anon_slot_name(_idx, rng)
                    candidate = _fit_slot_name(candidate)
                    if candidate.lower() in taken_lower:
                        continue
                    anon_counter += 1
                    _auto_idx = _idx
                    slot_name = candidate
                    break
        options: dict[str, Any] = {}

        _preset_search_names: list[str] = [slot_name]
        if _auto_idx is not None:
            _old_alias = f"{game} {_auto_idx + 1}" if kind == "count" else f"Anonymous {_auto_idx + 1}"
            if _old_alias != slot_name:
                _preset_search_names.append(_old_alias)
            _fitted_old = _fit_slot_name(_old_alias)
            if _fitted_old not in _preset_search_names:
                _preset_search_names.append(_fitted_old)
        for _search_name in _preset_search_names:
            for candidate in _preset_candidates(root, game, _search_name):
                try:
                    options = _roll_preset(candidate, game, rng)
                    if _search_name != slot_name:
                        dprint("mystery", f"preset alias {_search_name!r} -> {slot_name!r} for {game}")
                    break
                except Exception as exc:
                    logger.warning("[Mystery] Preset %s failed, trying next: %s", candidate, exc)
            if options:
                break

        _effective_slot_inline: dict[str, Any] = slot_inline  # type: ignore
        if _auto_idx is not None and slot_name not in slot_inline:
            for _alias in _preset_search_names[1:]:
                if _alias in slot_inline:
                    _effective_slot_inline = dict(slot_inline)
                    _effective_slot_inline[slot_name] = slot_inline[_alias]  # type: ignore
                    dprint("mystery", f"alias slot_options {_alias!r} -> {slot_name!r} for {game}")
                    break

        _code_set_opts: dict[str, Any] = {}
        if kind == "code" and hasattr(build_mystery_specs, "_code_set_slot_options"):
            try:
                _code_set_dict: dict[str, Any] = getattr(build_mystery_specs, "_code_set_slot_options", {})  # type: ignore
                if slot_name in _code_set_dict:
                    _code_captured = _code_set_dict[slot_name]
                    if isinstance(_code_captured, dict):
                        _code_set_opts = dict(_code_captured)
                        dprint("mystery", f"code set slot {slot_name!r} has {len(_code_set_opts)} game-specific opts from yaml")
            except Exception:
                pass

        if _code_set_opts:

            _effective_slot_inline = dict(_effective_slot_inline)

            if slot_name not in _effective_slot_inline:
                _effective_slot_inline[slot_name] = {}
            elif not isinstance(_effective_slot_inline[slot_name], dict):
                _effective_slot_inline[slot_name] = {}

            for k, v in _code_set_opts.items():
                if k not in _effective_slot_inline[slot_name]:
                    _effective_slot_inline[slot_name][k] = v
        options.update(_inline_options(AutoWorldRegister.world_types[game], game,
                                       slot_name, game_inline, _effective_slot_inline, plando_options))
        if random_remaining:
            world_type = AutoWorldRegister.world_types[game]
            type_hints: Any = getattr(world_type.options_dataclass, "type_hints", {})
            for key, option_class in type_hints.items():
                if key in options:
                    continue
                randomized: Any | None = None
                if random_sets:
                    try:
                        from Options import OptionList, OptionSet
                        if issubclass(option_class, (OptionSet, OptionList)):
                            randomized = _make_random_set_option(option_class, world_type, slot_name, plando_options, rng)
                            if randomized is not None:
                                options[key] = randomized
                                dprint("mystery", f"randomized set {game}/{slot_name} {key} -> {randomized.value!r}")
                                continue
                    except Exception as exc:
                        logger.warning("[Mystery] Random set for %s %s failed: %s", game, key, exc)
                randomized = _make_random_option(option_class, world_type, slot_name, plando_options, rng)
                if randomized is not None:
                    options[key] = randomized
                    dprint("mystery", f"randomized {game}/{slot_name} {key} -> {randomized.value!r}")
        if per_game_nuzlocke_mode in (1, 2):
            if "mystery_nuzlocke_deathlink" not in options:
                try:
                    from worlds.mystery_game.options import MysteryNuzlockeDeathLink

                    world_type = AutoWorldRegister.world_types[game]
                    if "mystery_nuzlocke_deathlink" in getattr(world_type.options_dataclass, "type_hints", {}):
                        options["mystery_nuzlocke_deathlink"] = MysteryNuzlockeDeathLink(per_game_nuzlocke_mode)
                        dprint("mystery", f"patched nuzlocke deathlink for {game}/{slot_name} -> {per_game_nuzlocke_mode}")
                except Exception as exc:
                    logger.warning("[Mystery] Failed to patch nuzlocke deathlink for %s: %s", game, exc)
        if per_game_nuzlocke_lives is not None:
            if "mystery_nuzlocke_lives" not in options:
                try:
                    from worlds.mystery_game.options import MysteryNuzlockeLives

                    world_type = AutoWorldRegister.world_types[game]
                    if "mystery_nuzlocke_lives" in getattr(world_type.options_dataclass, "type_hints", {}):
                        options["mystery_nuzlocke_lives"] = MysteryNuzlockeLives(per_game_nuzlocke_lives)
                        dprint("mystery", f"patched nuzlocke lives for {game}/{slot_name} -> {per_game_nuzlocke_lives}")
                except Exception as exc:
                    logger.warning("[Mystery] Failed to patch nuzlocke lives for %s: %s", game, exc)
        taken_lower.add(slot_name.lower())
        specs.append(ExpansionSpec(game=game, name=slot_name, options=options))

    for unused_game in game_inline:
        if unused_game not in {spec.game for spec in specs}:
            logger.warning("[Mystery] game_options entry for %r matches no added slot.", unused_game)

    dprint("mystery", f"expansion specs: {[(spec.game, spec.name) for spec in specs]}")
    return specs


__all__ = [
    "GenArgs",
    "MAX_SLOT_NAME_LEN",
    "MultipleMysteryWorldsError",
    "MysteryException",
    "build_mystery_specs",
]
