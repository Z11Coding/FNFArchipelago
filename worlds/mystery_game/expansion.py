from __future__ import annotations

"""Mystery expansion: variant options turn into live slots.

Called from ``MysteryGameWorld.generate_early`` with an args-shaped shim so
the same builder works on live world options. Each spec is then added via
``APAPI.inject_player_now`` (live mid-generation path — never Main.main).

Preset conventions (all under ``<player_files_path>/mystery/``):

- ``games/<Game>.yaml`` — dedicated preset for that game.
- ``games/<Game>/*.yaml`` — several to pick from (seeded choice).
- ``slots/<SlotName>.yaml`` — exact-slot preset, wins over game presets.
- ``allowed_games.txt`` — one game per line; restricts anonymous picks and
  validates explicit requests. Without it (but with any game yamls present),
  anonymous picks are limited to games that have dedicated yamls.

Only one Mystery Game per multiworld; a second raises.
"""

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


class MultipleMysteryWorldsError(MysteryException):
    """Raised when more than one Mystery Game is present (only one allowed)."""


GenArgs = argparse.Namespace
"""Generation args (or an args-shaped shim with game/name/option tables)."""


def _mystery_players(args: GenArgs) -> list[int]:
    try:
        games: Any = getattr(args, "game", {})
    except Exception:
        return []
    if not isinstance(games, dict):
        return []
    return sorted(pid for pid, game in games.items()
                  if game == "Mystery Game" and isinstance(pid, int))


def _mystery_root(args: GenArgs) -> Path | None:
    base: Any = getattr(args, "player_files_path", None)
    if not base:
        return None
    root = Path(str(base)) / "mystery"
    return root if root.is_dir() else None


def _allowed_games(root: Path | None) -> list[str] | None:
    """Explicit allow-list, else games-with-yamls, else None (anything)."""
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
    """Preset files for a slot: exact-slot file wins, else game dedicated/folder."""
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
    """Roll one preset file into ``{option_key: Option}`` for ``game``."""
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
    """Roll inline overrides: game-level first, slot-level wins.

    Raises MysteryException on unknown keys or unparsable values (typos
    must fail fast, not silently seed wrong).
    """
    type_hints: Any = getattr(world_type.options_dataclass, "type_hints", {})
    merged: dict[str, Any] = {}
    for layer, source in (("game", game_inline.get(game, {})),
                          ("slot", slot_inline.get(slot_name, {}))):
        if not isinstance(source, dict):
            raise MysteryException(f"{layer} options for {game!r}/{slot_name!r} must be a mapping.")
        for key, raw in source.items():
            if key not in type_hints:
                raise MysteryException(f"Unknown option {key!r} for game {game!r}.")
            option_class: Any = type_hints[key]
            try:
                value: Any = option_class.from_any(raw)
            except Exception as exc:
                raise MysteryException(f"Invalid {key}={raw!r} for game {game!r}: {exc}") from exc
            try:
                value.verify(world_type, slot_name, plando_options)
            except Exception as exc:
                raise MysteryException(f"Invalid {key}={raw!r} for game {game!r}: {exc}") from exc
            merged[key] = value
    return merged


def _eligible_anonymous(rng: random.Random) -> list[str]:
    """Loaded, visible worlds usable for anonymous picks (never Mystery itself)."""
    from worlds.AutoWorld import AutoWorldRegister
    return sorted(
        game for game, world_type in AutoWorldRegister.world_types.items()
        if game != "Mystery Game" and not bool(getattr(world_type, "hidden", False)))


def build_mystery_specs(args: GenArgs, seed: Any) -> list[Any]:
    """Turn one mystery slot's options into expansion specs (may raise)."""
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
    allowed: list[str] | None = _allowed_games(root)

    wanted: list[tuple[str, str, str]] = []  # (game, slot_name, kind)
    for game, count in counts.items():
        if not isinstance(count, int) or count < 0:
            raise MysteryException(f"Invalid count {count!r} for game {game!r}.")
        for _ in range(count):
            wanted.append((game, "", "count"))
    for slot_name, game in slots.items():
        wanted.append((game, str(slot_name), "slot"))

    eligible: list[str] = _eligible_anonymous(rng)
    pool: list[str] = [game for game in eligible if allowed is None or game in allowed]
    for _ in range(max(anon, 0)):
        if not pool:
            raise MysteryException("No eligible games left for anonymous picks.")
        wanted.append((rng.choice(pool), "", "anon"))

    # Validate every explicitly requested game up front (fail fast, loudly).
    for game, _slot_name, _kind in wanted:
        if game not in AutoWorldRegister.world_types:
            raise MysteryException(f"Unknown game {game!r} requested by Mystery Game.")
        if allowed is not None and game not in allowed:
            raise MysteryException(f"Game {game!r} is not in allowed_games.txt.")

    # Name count slots after their game, anonymous slots opaquely (so the
    # name leaks nothing); explicit slot names pass through (collisions are
    # the host's to fix, generated ones re-number themselves).
    taken_lower: set[str] = set()
    try:
        taken_lower = {str(name).lower() for name in getattr(args, "name", {}).values()}
    except Exception:
        pass
    anon_counter: int = 0
    game_counters: dict[str, int] = {}
    specs: list[Any] = []
    for game, slot_name, kind in wanted:
        if kind == "slot":
            if slot_name.lower() in taken_lower:
                raise MysteryException(f"Duplicate slot name {slot_name!r} requested by Mystery Game.")
        else:
            while True:
                if kind == "count":
                    game_counters[game] = game_counters.get(game, 0) + 1
                    slot_name = f"{game} {game_counters[game]}"
                else:
                    anon_counter += 1
                    slot_name = f"Anonymous {anon_counter}"
                if slot_name.lower() not in taken_lower:
                    break
        options: dict[str, Any] = {}
        for candidate in _preset_candidates(root, game, slot_name):
            try:
                options = _roll_preset(candidate, game, rng)
                break
            except Exception as exc:
                logger.warning("[Mystery] Preset %s failed, trying next: %s", candidate, exc)
        options.update(_inline_options(AutoWorldRegister.world_types[game], game,
                                       slot_name, game_inline, slot_inline, plando_options))
        taken_lower.add(slot_name.lower())
        specs.append(ExpansionSpec(game=game, name=slot_name, options=options))

    for unused_game in game_inline:
        if unused_game not in {spec.game for spec in specs}:
            logger.warning("[Mystery] game_options entry for %r matches no added slot.", unused_game)

    dprint("mystery", f"expansion specs: {[(spec.game, spec.name) for spec in specs]}")
    return specs


__all__ = [
    "GenArgs",
    "MultipleMysteryWorldsError",
    "MysteryException",
    "build_mystery_specs",
]
