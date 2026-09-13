from __future__ import annotations

"""Easy, typed YAML reading for APAPI consumers.

Wraps :func:`Utils.parse_yaml` with small helpers so worlds (e.g. Mystery
Game puzzle packs, per-slot preset folders) don't each re-implement:

- player-file discovery (``--player_files_path`` argv override, else the
  ``generator.player_files_path`` setting, like No Logic does),
- multi-document splitting on standalone ``---`` lines,
- player-name extraction (``name`` field plus ``triggers`` overrides),
- ``{number}`` / ``{player}`` name formatting.
"""

import string
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import Utils


class SafeFormatter(string.Formatter):
    """Archipelago's SafeFormatter: unknown fields stay literal."""

    def get_value(self, key: Any, args: Any, kwargs: Any) -> Any:
        if isinstance(key, int):
            return args[key] if key < len(args) else "{" + str(key) + "}"
        return kwargs.get(key, "{" + key + "}")


def read_yaml_text(text: str) -> Any:
    """Parse one YAML document's text; returns dicts/lists/scalars."""
    return Utils.parse_yaml(text)


def read_yaml_documents(text: str) -> list[Any]:
    """Split ``text`` on standalone ``---`` lines and parse each document."""
    lines: list[str] = text.splitlines()
    start: int = 1 if lines and lines[0].strip() == "---" else 0
    documents: list[str] = []
    current: list[str] = []
    for line in lines[start:]:
        if line.strip() == "---":
            documents.append("\n".join(current))
            current = []
        else:
            current.append(line)
    if current:
        documents.append("\n".join(current))
    parsed: list[Any] = []
    for document in documents:
        document = document.strip()
        if document:
            parsed.append(Utils.parse_yaml(document))
    return parsed


def read_yaml_file(path: str | Path) -> Any:
    """Read and parse a single-document YAML file."""
    file_path = Path(path)
    return Utils.parse_yaml(file_path.read_text(encoding="utf-8-sig"))


def read_yaml_documents_file(path: str | Path) -> list[Any]:
    """Read a (possibly multi-document) YAML file into a list of docs."""
    file_path = Path(path)
    return read_yaml_documents(file_path.read_text(encoding="utf-8-sig"))


def resolve_player_files_dir(explicit: str | Path | None = None) -> Path | None:
    """Locate the Players dir: explicit path, ``--player_files_path`` argv, else settings."""
    if explicit is not None:
        candidate = Path(explicit)
        return candidate if candidate.is_dir() else None
    if "--player_files_path" in sys.argv:
        candidate = Path(sys.argv[sys.argv.index("--player_files_path") + 1])
        if candidate.is_dir():
            return candidate
    try:
        settings_path: str = Utils.get_settings()["generator"]["player_files_path"]
        candidate = Path(Utils.user_path(settings_path))
        return candidate if candidate.is_dir() else None
    except Exception:
        return None


def iter_player_yaml_files(players_dir: str | Path) -> list[Path]:
    """Sorted player YAML files (any extension; skips dirs and desktop.ini)."""
    directory = Path(players_dir)
    if not directory.is_dir():
        return []
    return sorted(
        (entry for entry in directory.glob("*") if entry.is_file() and entry.name != "desktop.ini"),
        key=lambda entry: entry.name,
    )


def extract_player_names(parsed: Any) -> tuple[list[str], bool]:
    """Collect candidate player names from parsed YAML (main + trigger names).

    Returns ``(names, success)``. Raises nothing; callers filter by game.
    """
    if isinstance(parsed, list):
        parsed = parsed[0] if parsed else {}
    if not isinstance(parsed, dict):
        return [], False
    names: list[str] = []
    main_name: Any = parsed.get("name")
    if isinstance(main_name, str) and main_name.strip():
        names.append(main_name.strip())
    triggers: Any = parsed.get("triggers")
    if isinstance(triggers, list):
        for trigger in triggers:
            if not isinstance(trigger, dict):
                continue
            options: Any = trigger.get("options")
            if not isinstance(options, dict):
                continue
            fallback: Any = options.get(None)
            if not isinstance(fallback, dict):
                continue
            trigger_name: Any = fallback.get("name")
            if isinstance(trigger_name, str) and trigger_name.strip() and trigger_name.strip() not in names:
                names.append(trigger_name.strip())
    return names, len(names) > 0


def format_player_name(name: str, player: int, number: int) -> str:
    """Apply Archipelago ``{number}``/``{player}`` substitution (1-based)."""
    resolved: str = "%%".join(
        part.replace("%number%", "{number}").replace("%player%", "{player}")
        for part in name.split("%%")
    )
    return SafeFormatter().vformat(resolved, (), {
        "number": number,
        "NUMBER": (number if number > 1 else ""),
        "player": player,
        "PLAYER": (player if player > 1 else ""),
    }).strip()


def resolve_player_name(name: str, player: int, counter: Counter[str]) -> str:
    """Format ``name`` with a shared occurrence counter (like Generate's handle_name)."""
    counter[name.lower()] += 1
    return format_player_name(name, player, counter[name.lower()])


__all__ = [
    "SafeFormatter",
    "extract_player_names",
    "format_player_name",
    "iter_player_yaml_files",
    "read_yaml_documents",
    "read_yaml_documents_file",
    "read_yaml_file",
    "read_yaml_text",
    "resolve_player_files_dir",
    "resolve_player_name",
]
