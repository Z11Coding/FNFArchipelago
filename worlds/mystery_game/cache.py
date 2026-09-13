from __future__ import annotations

"""Pure slot-lock / guess-mode / proxy helpers for Mystery Game.

Stdlib-only on purpose: no Archipelago imports, so this module is unit
testable anywhere. The client (``MysteryClient``) and world use these for:

- server data-storage keys (``cached_checks`` per locked slot, persisted by
  the server itself via ``Set``/``Get``/``SetNotify`` + ``ctx.save()``),
- cache entry shape ``{game, pending_checks, held_items}`` mapping which
  game each held check belongs to, so nothing is lost on close,
- guess normalization/comparison (``!mystery_guess <slot> <game>``),
- proxy connection instruction text.
"""

import re
from typing import Any

#: Port the in-client proxy listens on (localhost), AHIT uses 11311.
MYSTERY_PROXY_PORT: int = 11318
MYSTERY_PROXY_HOST: str = "localhost"

#: Server data-storage key prefixes (team/slot appended at runtime).
CACHE_KEY_PREFIX: str = "mystery_cache"
UNLOCKS_KEY_PREFIX: str = "mystery_unlocks"
PUZZLE_STATE_PREFIX: str = "mystery_puzzle_state"

_NON_ALNUM: Any = re.compile(r"[^a-z0-9]+")
_PIECE_RE: Any = re.compile(r"^Puzzle Piece: (.+) #(\d+)$")
_HINT_RE: Any = re.compile(r"^Puzzle Hint: (.+) #(\d+)$")


def cache_key(team: int, slot: int) -> str:
    """Server data key holding a locked slot's ``cached_checks`` entry."""
    return f"{CACHE_KEY_PREFIX}_{team}_{slot}"


def unlocks_key(team: int) -> str:
    """Server data key holding ``{slot_name: 'item' | 'guess'}`` unlocks."""
    return f"{UNLOCKS_KEY_PREFIX}_{team}"


def puzzle_state_key(team: int, slot: int) -> str:
    """Server data key holding puzzle progress for one mystery slot.

    Value: ``{puzzle: {'pieces': [i...], 'hints': [i...], 'solved': bool}}``.
    """
    return f"{PUZZLE_STATE_PREFIX}_{team}_{slot}"


def puzzle_piece_name(puzzle: str, index: int) -> str:
    """Pool item granting piece ``index`` (1-based) of ``puzzle``."""
    return f"Puzzle Piece: {puzzle} #{index}"


def puzzle_hint_name(puzzle: str, index: int) -> str:
    """Pool item revealing hint ``index`` (1-based) of ``puzzle``."""
    return f"Puzzle Hint: {puzzle} #{index}"


def parse_puzzle_piece(name: str) -> tuple[str, int] | None:
    """Parse a piece item name into ``(puzzle, index)`` (1-based)."""
    match: Any = _PIECE_RE.match(name.strip())
    if not match:
        return None
    return match.group(1), int(match.group(2))


def parse_puzzle_hint(name: str) -> tuple[str, int] | None:
    """Parse a hint item name into ``(puzzle, index)`` (1-based)."""
    match: Any = _HINT_RE.match(name.strip())
    if not match:
        return None
    return match.group(1), int(match.group(2))


def normalize_puzzle_state(raw: Any) -> dict[str, dict[str, Any]]:
    """Coerce server data into ``{puzzle: {pieces, hints, solved}}``."""
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
    """Union-merge server puzzle progress into local progress (in place)."""
    for puzzle, entry in server.items():
        mine: dict[str, Any] = local.setdefault(
            puzzle, {"pieces": [], "hints": [], "solved": False})
        mine["pieces"] = sorted(set(mine.get("pieces", [])) | set(entry.get("pieces", [])))
        mine["hints"] = sorted(set(mine.get("hints", [])) | set(entry.get("hints", [])))
        mine["solved"] = bool(mine.get("solved", False) or entry.get("solved", False))
    return local


def puzzle_ready(state: dict[str, dict[str, Any]], puzzle: str, need_pieces: int) -> bool:
    """True when ``puzzle`` has all ``need_pieces`` pieces (0 = free solve)."""
    if need_pieces <= 0:
        return True
    have: set[int] = set(state.get(puzzle, {}).get("pieces", []))
    return all(i in have for i in range(1, need_pieces + 1))


def normalize_game_name(name: str) -> str:
    """Lowercase alphanumeric fold so 'A Link to the Past' == 'alinktothepast'."""
    return _NON_ALNUM.sub("", name.lower()).strip()


def check_guess(guess: str, answer: str) -> bool:
    """True when a guessed game name matches the real one."""
    return bool(guess and answer) and normalize_game_name(guess) == normalize_game_name(answer)


def new_cache_entry(game: str) -> dict[str, Any]:
    """Empty cache entry for a locked slot's game."""
    return {"game": game, "pending_checks": [], "held_items": []}


def normalize_cache_entry(raw: Any, game: str = "Unknown") -> dict[str, Any]:
    """Coerce server data into a valid cache entry (tolerates missing keys)."""
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
    """Add location ids to ``pending_checks`` without duplicates (in place)."""
    seen: set[int] = set(entry.setdefault("pending_checks", []))
    for check in checks:
        if isinstance(check, int) and check not in seen:
            seen.add(check)
            entry["pending_checks"].append(check)
    return entry


def merge_held_items(entry: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    """Append received-item dicts, deduping on ``(index)`` when present."""
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
    """Build a ``Set`` packet replacing ``key`` (persisted server-side)."""
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
    """Human-readable steps for connecting a game client through the proxy."""
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
