from __future__ import annotations

"""Dynamic items/locations for Mystery Game (No Logic style).

``item_name_to_id`` / ``location_name_to_id`` must be complete at import
time (the datapackage is built right after all worlds load), but the actual
puzzles are per-seed. Like No Logic, we therefore:

- reserve fixed ID blocks at import (puzzle completion items/locations,
  unlock items/locations, plus per-puzzle piece and hint items),
- scan ``<player_files_path>/mystery/*.yaml`` for puzzle packs when
  available. Each doc may be ``{puzzles: [...]}`` or a plain list, and each
  entry may be a bare name or a mapping::

      puzzles:
        - "Riddle of Echoes"                      # bare name
        - name: "The Silent Vault"                # full pack entry
          pieces: 4                               # piece items required (else the option)
          hints:
            - "It echoes where water falls."
            - "Count the bells, then subtract one."

- fill the rest with generic ``Puzzle <n>`` entries up to ``MAX_PUZZLES``,
  after the world-shipped ``puzzle_packs/`` (player packs win ties and come
  first in the roster),
- always reserve generic ``Unlock Slot <n>`` entries up to
  ``MAX_UNLOCK_SLOTS`` (per-seed slot mapping happens in ``generate_early``).

Piece/hint item names are static per ``(puzzle, index)`` (``#i``); how many
of them a seed uses comes from options/pack data at generation time.
"""

import logging
from pathlib import Path
from typing import Any

from worlds.APAPI.debug import dprint
from worlds.APAPI.yaml_tools import (
    iter_player_yaml_files,
    read_yaml_documents,
    read_yaml_documents_file,
    resolve_player_files_dir,
)

from .cache import puzzle_hint_name, puzzle_piece_name

logger = logging.getLogger("APAPI.MysteryGame")

MYSTERY_BASE_ID: int = 1_000_000
MAX_PUZZLES: int = 64
MAX_UNLOCK_SLOTS: int = 32
MAX_PIECES: int = 8
MAX_HINTS: int = 8

PUZZLE_ITEM_BASE: int = MYSTERY_BASE_ID
PUZZLE_LOCATION_BASE: int = MYSTERY_BASE_ID + 1_000
UNLOCK_ITEM_BASE: int = MYSTERY_BASE_ID + 2_000
UNLOCK_LOCATION_BASE: int = MYSTERY_BASE_ID + 3_000
PIECE_ITEM_BASE: int = MYSTERY_BASE_ID + 4_000
HINT_ITEM_BASE: int = MYSTERY_BASE_ID + 5_000

MYSTERY_TOKEN_ITEM: str = "Mystery Token"
MYSTERY_TOKEN_ID: int = MYSTERY_BASE_ID + 9_000


def puzzle_item_name(puzzle: str) -> str:
    """Item granted when a puzzle is solved."""
    return f"Puzzle Complete: {puzzle}"


def puzzle_location_name(puzzle: str) -> str:
    """Checkable location for a puzzle."""
    return f"Solve Puzzle: {puzzle}"


def unlock_item_name(index: int) -> str:
    """Item that unlocks scrambled slot number ``index`` (1-based)."""
    return f"Unlock Slot {index}"


def unlock_location_name(index: int) -> str:
    """Location holding the unlock item for scrambled slot ``index``."""
    return f"Unlock Check: Slot {index}"


def _parse_pack_entry(entry: Any) -> tuple[str, list[str], int | None] | None:
    """Parse one puzzle entry into ``(name, hints, pieces_override)``."""
    if isinstance(entry, str) and entry.strip():
        return entry.strip(), [], None
    if isinstance(entry, dict):
        name: Any = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        hints: Any = entry.get("hints", [])
        pieces: Any = entry.get("pieces")
        clean_hints: list[str] = []
        if isinstance(hints, list):
            clean_hints = [hint.strip() for hint in hints
                           if isinstance(hint, str) and hint.strip()][:MAX_HINTS]
        clean_pieces: int | None = pieces if isinstance(pieces, int) and pieces >= 0 else None
        return name.strip(), clean_hints, clean_pieces
    return None


def _collect_pack_docs(docs: list[Any], names: list[str],
                       hints: dict[str, list[str]], pieces: dict[str, int]) -> None:
    """Fold parsed YAML docs into the pack tables (first-seen wins)."""
    for document in docs:
        candidates: Any = document.get("puzzles") if isinstance(document, dict) else document
        if not isinstance(candidates, list):
            continue
        for entry in candidates:
            parsed = _parse_pack_entry(entry)
            if parsed is None:
                continue
            name, pack_hints, pack_pieces = parsed
            if name not in names:
                names.append(name)
            if pack_hints:
                hints.setdefault(name, pack_hints)
            if pack_pieces is not None:
                pieces.setdefault(name, pack_pieces)


def _builtin_pack_docs() -> list[Any]:
    """Parse the world-shipped packs (zip-safe via importlib.resources)."""
    docs: list[Any] = []
    try:
        from importlib import resources
        anchor = resources.files("worlds.mystery_game.puzzle_packs")
        for entry in anchor.iterdir():
            if not entry.name.endswith((".yaml", ".yml")):
                continue
            try:
                try:
                    text: str = entry.read_text(encoding="utf-8-sig")
                except Exception:
                    with entry.open("rb") as stream:
                        text = stream.read().decode("utf-8-sig")
                docs.extend(read_yaml_documents(text))
            except Exception as exc:
                logger.warning("[Mystery] Could not read built-in pack %s: %s", entry.name, exc)
        if docs:
            return docs
    except Exception:
        pass
    # Loose-folder fallback for unusual loaders.
    try:
        folder = Path(__file__).parent / "puzzle_packs"
        if folder.is_dir():
            for pack_file in sorted(folder.glob("*.yaml")):
                try:
                    docs.extend(read_yaml_documents_file(pack_file))
                except Exception as exc:
                    logger.warning("[Mystery] Could not read built-in pack %s: %s",
                                   pack_file.name, exc)
    except Exception:
        pass
    return docs


def discover_puzzle_packs() -> tuple[list[str], dict[str, list[str]], dict[str, int]]:
    """Puzzle packs: player files first (they win ties), then built-in packs.

    Returns ``(names, hints_by_puzzle, pieces_by_puzzle)``; generic fill
    happens in :func:`build_puzzle_roster`. Backwards compatible with
    bare-name lists.
    """
    names: list[str] = []
    hints: dict[str, list[str]] = {}
    pieces: dict[str, int] = {}
    players_dir = resolve_player_files_dir()
    mystery_dir = None
    if players_dir is not None:
        candidate = players_dir / "mystery"
        if candidate.is_dir():
            mystery_dir = candidate
    if mystery_dir is None:
        dprint("mystery", "no Players/mystery folder; using built-in puzzles")
    else:
        for yaml_file in iter_player_yaml_files(mystery_dir):
            try:
                _collect_pack_docs(read_yaml_documents_file(yaml_file), names, hints, pieces)
            except Exception as exc:
                logger.warning("[Mystery] Could not read puzzle file %s: %s", yaml_file.name, exc)
    _collect_pack_docs(_builtin_pack_docs(), names, hints, pieces)
    dprint("mystery", f"discovered {len(names)} named puzzle(s)")
    return names, hints, pieces


def discover_puzzle_names() -> list[str]:
    """Named puzzles from ``Players/mystery/*.yaml`` (empty when none found)."""
    names, _hints, _pieces = discover_puzzle_packs()
    return names


def build_puzzle_roster(custom: list[str] | None = None) -> list[str]:
    """Full puzzle roster: custom names first, generic fill up to MAX_PUZZLES."""
    roster: list[str] = list(custom or [])
    index: int = 1
    while len(roster) < MAX_PUZZLES:
        generic = f"Puzzle {index}"
        if generic not in roster:
            roster.append(generic)
        index += 1
    return roster[:MAX_PUZZLES]


_PACK_NAMES, PUZZLE_HINTS, PUZZLE_PIECE_OVERRIDES = discover_puzzle_packs()
PUZZLE_ROSTER: list[str] = build_puzzle_roster(_PACK_NAMES)


def build_item_name_to_id() -> dict[str, int]:
    """Import-time item table (static IDs so the datapackage is stable)."""
    table: dict[str, int] = {MYSTERY_TOKEN_ITEM: MYSTERY_TOKEN_ID}
    for index, puzzle in enumerate(PUZZLE_ROSTER):
        table[puzzle_item_name(puzzle)] = PUZZLE_ITEM_BASE + index
        for piece in range(1, MAX_PIECES + 1):
            table[puzzle_piece_name(puzzle, piece)] = PIECE_ITEM_BASE + index * MAX_PIECES + (piece - 1)
        for hint in range(1, MAX_HINTS + 1):
            table[puzzle_hint_name(puzzle, hint)] = HINT_ITEM_BASE + index * MAX_HINTS + (hint - 1)
    for index in range(MAX_UNLOCK_SLOTS):
        table[unlock_item_name(index + 1)] = UNLOCK_ITEM_BASE + index
    return table


def build_location_name_to_id() -> dict[str, int]:
    """Import-time location table (static IDs so the datapackage is stable)."""
    table: dict[str, int] = {}
    for index, puzzle in enumerate(PUZZLE_ROSTER):
        table[puzzle_location_name(puzzle)] = PUZZLE_LOCATION_BASE + index
    for index in range(MAX_UNLOCK_SLOTS):
        table[unlock_location_name(index + 1)] = UNLOCK_LOCATION_BASE + index
    return table


__all__ = [
    "MAX_HINTS",
    "MAX_PIECES",
    "MAX_PUZZLES",
    "MAX_UNLOCK_SLOTS",
    "MYSTERY_BASE_ID",
    "MYSTERY_TOKEN_ID",
    "MYSTERY_TOKEN_ITEM",
    "PUZZLE_HINTS",
    "PUZZLE_PIECE_OVERRIDES",
    "PUZZLE_ROSTER",
    "build_item_name_to_id",
    "build_location_name_to_id",
    "discover_puzzle_names",
    "discover_puzzle_packs",
    "puzzle_item_name",
    "puzzle_location_name",
    "unlock_item_name",
    "unlock_location_name",
]
