from __future__ import annotations

"""YAML helpers for player files, name formatting, and multi-doc parsing."""

import string
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import Utils


class SafeFormatter(string.Formatter):
    """Formatter where unknown fields stay literal."""

    def get_value(self, key: Any, args: Any, kwargs: Any) -> Any:
        """Input: key, args, kwargs. Returns: formatted value or literal."""
        if isinstance(key, int):
            return args[key] if key < len(args) else "{" + str(key) + "}"
        return kwargs.get(key, "{" + key + "}")


def read_yaml_text(text: str) -> Any:
    """Input: YAML text. Returns: parsed value."""
    return Utils.parse_yaml(text)


def read_yaml_documents(text: str) -> list[Any]:
    """Input: YAML text. Returns: list of parsed docs."""
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
    """Input: path. Returns: parsed YAML."""
    file_path = Path(path)
    return Utils.parse_yaml(file_path.read_text(encoding="utf-8-sig"))


def read_yaml_documents_file(path: str | Path) -> list[Any]:
    """Input: path. Returns: list of parsed docs."""
    file_path = Path(path)
    return read_yaml_documents(file_path.read_text(encoding="utf-8-sig"))


def resolve_player_files_dir(explicit: str | Path | None = None) -> Path | None:
    """Input: explicit dir or None. Returns: players dir or None."""
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
    """Input: players dir. Returns: sorted YAML files."""
    directory = Path(players_dir)
    if not directory.is_dir():
        return []
    return sorted(
        (entry for entry in directory.glob("*") if entry.is_file() and entry.name != "desktop.ini"),
        key=lambda entry: entry.name,
    )


def extract_player_names(parsed: Any) -> tuple[list[str], bool]:
    """Input: parsed YAML. Returns: (names, success)."""
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
    """Input: name, player, number. Returns: formatted name."""
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
    """Input: name, player, counter. Returns: formatted name with counted number."""
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
