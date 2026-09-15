from __future__ import annotations

"""Slot-lock/guess/proxy helpers. Stdlib only."""

import re
from typing import Any

MYSTERY_PROXY_PORT: int = 11318
MYSTERY_PROXY_HOST: str = "localhost"
MYSTERY_GLOBAL_PORT: int = 11400
MYSTERY_GLOBAL_HOST: str = "0.0.0.0"

CACHE_KEY_PREFIX: str = "mystery_cache"
UNLOCKS_KEY_PREFIX: str = "mystery_unlocks"
PUZZLE_STATE_PREFIX: str = "mystery_puzzle_state"
NUZLOCKE_PREFIX: str = "mystery_nuzlocke"
NUZLOCKE_EXTRA_PREFIX: str = "mystery_nuzlocke_extra"

_NON_ALNUM: Any = re.compile(r"[^a-z0-9]+")
_PIECE_RE: Any = re.compile(r"^Puzzle Piece: (.+) #(\d+)$")
_HINT_RE: Any = re.compile(r"^Puzzle Hint: (.+) #(\d+)$")


def cache_key(team: int, slot: int) -> str:
    """Input: team, slot. Returns: cache Set key."""
    return f"{CACHE_KEY_PREFIX}_{team}_{slot}"


def unlocks_key(team: int) -> str:
    """Input: team. Returns: unlocks dict key."""
    return f"{UNLOCKS_KEY_PREFIX}_{team}"


def puzzle_state_key(team: int, slot: int) -> str:
    """Input: team, slot. Returns: puzzle state key."""
    return f"{PUZZLE_STATE_PREFIX}_{team}_{slot}"


def nuzlocke_key(team: int) -> str:
    """Input: team. Returns: nuzlocke dead-slots/hits key."""
    return f"{NUZLOCKE_PREFIX}_{team}"


def nuzlocke_extra_key(team: int) -> str:
    """Input: team. Returns: nuzlocke extra-lives key (per-slot extra lives earned)."""
    return f"{NUZLOCKE_EXTRA_PREFIX}_{team}"


def puzzle_piece_name(puzzle: str, index: int) -> str:
    """Input: puzzle, 1-based index. Returns: piece item name."""
    return f"Puzzle Piece: {puzzle} #{index}"


def puzzle_hint_name(puzzle: str, index: int) -> str:
    """Input: puzzle, 1-based index. Returns: hint item name."""
    return f"Puzzle Hint: {puzzle} #{index}"


def parse_puzzle_piece(name: str) -> tuple[str, int] | None:
    """Input: item name. Returns: (puzzle, index) or None."""
    match: Any = _PIECE_RE.match(name.strip())
    if not match:
        return None
    return match.group(1), int(match.group(2))


def parse_puzzle_hint(name: str) -> tuple[str, int] | None:
    """Input: item name. Returns: (puzzle, index) or None."""
    match: Any = _HINT_RE.match(name.strip())
    if not match:
        return None
    return match.group(1), int(match.group(2))


def normalize_puzzle_state(raw: Any) -> dict[str, dict[str, Any]]:
    """Input: raw server data. Returns: {puzzle: {pieces, hints, solved}}."""
    if not isinstance(raw, dict):
        return {}
    clean: dict[str, dict[str, Any]] = {}
    for puzzle, entry in raw.items():
        if not isinstance(puzzle, str) or not isinstance(entry, dict):
            continue
        pieces: Any = entry.get("pieces", [])
        hints: Any = entry.get("hints", [])
        clean[puzzle] = {
            "pieces": sorted({i for i in pieces if isinstance(i, int) and i > 0}),
            "hints": sorted({i for i in hints if isinstance(i, int) and i > 0}),
            "solved": bool(entry.get("solved", False)),
        }
    return clean


def merge_puzzle_state(local: dict[str, dict[str, Any]],
                       server: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Input: local, server states. Returns: merged state (union, in place)."""
    for puzzle, entry in server.items():
        mine: dict[str, Any] = local.setdefault(
            puzzle, {"pieces": [], "hints": [], "solved": False})
        mine["pieces"] = sorted(set(mine.get("pieces", [])) | set(entry.get("pieces", [])))
        mine["hints"] = sorted(set(mine.get("hints", [])) | set(entry.get("hints", [])))
        mine["solved"] = bool(mine.get("solved", False) or entry.get("solved", False))
    return local


def puzzle_ready(state: dict[str, dict[str, Any]], puzzle: str, need_pieces: int) -> bool:
    """Input: state, puzzle, need_pieces. Returns: True if all pieces held (0=free)."""
    if need_pieces <= 0:
        return True
    have: set[int] = set(state.get(puzzle, {}).get("pieces", []))
    return all(i in have for i in range(1, need_pieces + 1))


def normalize_game_name(name: str) -> str:
    """Input: game name. Returns: lower alphanumeric fold."""
    return _NON_ALNUM.sub("", name.lower()).strip()


def check_guess(guess: str, answer: str) -> bool:
    """Input: guess, answer. Returns: True if normalized names match."""
    return bool(guess and answer) and normalize_game_name(guess) == normalize_game_name(answer)


def new_cache_entry(game: str) -> dict[str, Any]:
    """Input: game. Returns: empty cache entry."""
    return {"game": game, "pending_checks": [], "held_items": []}


def normalize_cache_entry(raw: Any, game: str = "Unknown") -> dict[str, Any]:
    """Input: raw, game. Returns: coerced cache entry."""
    if not isinstance(raw, dict):
        return new_cache_entry(game)
    pending: Any = raw.get("pending_checks", [])
    held: Any = raw.get("held_items", [])
    return {
        "game": raw.get("game", game) if isinstance(raw.get("game"), str) else game,
        "pending_checks": [int(check) for check in pending if isinstance(check, int)],
        "held_items": [item for item in held if isinstance(item, dict)],
    }


def merge_pending_checks(entry: dict[str, Any], checks: list[int]) -> dict[str, Any]:
    """Input: entry, checks. Output: adds checks without duplicates (in place)."""
    seen: set[int] = set(entry.setdefault("pending_checks", []))
    for check in checks:
        if isinstance(check, int) and check not in seen:
            seen.add(check)
            entry["pending_checks"].append(check)
    return entry


def merge_held_items(entry: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    """Input: entry, items. Output: appends items deduping on index (in place)."""
    held: list[dict[str, Any]] = entry.setdefault("held_items", [])
    known: set[Any] = {item.get("index") for item in held if "index" in item}
    for item in items:
        if not isinstance(item, dict):
            continue
        if "index" in item and item["index"] in known:
            continue
        held.append(item)
        if "index" in item:
            known.add(item["index"])
    return entry


def set_operation(key: str, value: Any, default: Any = None) -> dict[str, Any]:
    """Input: key, value. Returns: Set packet dict."""
    return {
        "cmd": "Set",
        "key": key,
        "default": {} if default is None else default,
        "want_reply": False,
        "operations": [{"operation": "replace", "value": value}],
    }


def proxy_instructions(
    host: str,
    port: int,
    routes: dict[str, str],
    frozen: list[str],
) -> str:
    """Input: host, port, routes, frozen. Returns: instructions string."""
    lines: list[str] = [
        f"Connect your game client to ws://{host}:{port} (NOT the multiworld server).",
        "Use the alias as your slot name; the proxy logs in as the real slot.",
    ]
    if routes:
        lines.append("Aliases:")
        for alias, real in sorted(routes.items()):
            state: str = "FROZEN" if alias in frozen or real in frozen else "open"
            lines.append(f"  {alias} -> {real} [{state}]")
    else:
        lines.append("No routes yet: unlock or relay a slot first (see !mystery_relay).")
    if frozen:
        lines.append("Frozen slots hold ALL traffic until unlocked (checks cached server-side).")
    return "\n".join(lines)


__all__ = [
    "CACHE_KEY_PREFIX",
    "MYSTERY_PROXY_HOST",
    "MYSTERY_PROXY_PORT",
    "MYSTERY_GLOBAL_HOST",
    "MYSTERY_GLOBAL_PORT",
    "NUZLOCKE_PREFIX",
    "NUZLOCKE_EXTRA_PREFIX",
    "PUZZLE_STATE_PREFIX",
    "UNLOCKS_KEY_PREFIX",
    "cache_key",
    "check_guess",
    "merge_held_items",
    "merge_pending_checks",
    "merge_puzzle_state",
    "new_cache_entry",
    "normalize_cache_entry",
    "normalize_game_name",
    "normalize_puzzle_state",
    "nuzlocke_extra_key",
    "nuzlocke_key",
    "parse_puzzle_hint",
    "parse_puzzle_piece",
    "proxy_instructions",
    "puzzle_hint_name",
    "puzzle_piece_name",
    "puzzle_ready",
    "puzzle_state_key",
    "set_operation",
    "unlocks_key",
]
