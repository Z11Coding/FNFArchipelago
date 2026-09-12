from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from typing import Any, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from BaseClasses import Location, MultiWorld


@dataclass
class SphereLocationEntry:
    sphere: int
    location_player: int
    location_name: str
    location_id: int | None
    item_player: int | None
    item_name: str | None
    item_id: int | None
    item_flags: int


@dataclass
class SphereData:
    index: int
    locations: list[SphereLocationEntry]


@dataclass
class PlaythroughModel:
    seed_name: str
    generated_at_utc: str
    players: dict[int, dict[str, Any]]
    spheres: list[SphereData]
    unreachable_locations: list[SphereLocationEntry]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_text(self) -> str:
        lines: list[str] = []
        lines.append(f"Seed: {self.seed_name}")
        lines.append(f"Generated: {self.generated_at_utc}")
        lines.append(f"Players: {len(self.players)}")
        for sphere in self.spheres:
            lines.append(f"\nSphere {sphere.index}: {len(sphere.locations)} location(s)")
            for entry in sphere.locations:
                lines.append(
                    f"  P{entry.location_player} {entry.location_name} [{entry.location_id}]"
                    f" -> {entry.item_name} (P{entry.item_player}, id={entry.item_id})"
                )

        if self.unreachable_locations:
            lines.append(f"\nUnreachable: {len(self.unreachable_locations)} location(s)")
            for entry in self.unreachable_locations:
                lines.append(
                    f"  P{entry.location_player} {entry.location_name} [{entry.location_id}]"
                    f" -> {entry.item_name} (P{entry.item_player}, id={entry.item_id})"
                )
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        lines: list[str] = ["flowchart LR"]
        for sphere in self.spheres:
            lines.append(f"  subgraph S{sphere.index}[Sphere {sphere.index}]")
            for idx, entry in enumerate(sphere.locations):
                node_name = f"S{sphere.index}_{idx}"
                location_label = entry.location_name.replace('"', "'")
                item_label = (entry.item_name or "None").replace('"', "'")
                lines.append(f"    {node_name}[\"{location_label} -> {item_label}\"]")
            lines.append("  end")

        for i in range(len(self.spheres) - 1):
            lines.append(f"  S{i} --> S{i+1}")

        return "\n".join(lines)


def _sorted_locations(locations: Iterable["Location"]) -> list["Location"]:
    return sorted(
        locations,
        key=lambda loc: (
            loc.player,
            loc.address if isinstance(loc.address, int) else 2**31 - 1,
            loc.name,
        ),
    )


def _to_entry(sphere_index: int, location: "Location") -> SphereLocationEntry:
    return SphereLocationEntry(
        sphere=sphere_index,
        location_player=location.player,
        location_name=location.name,
        location_id=location.address if isinstance(location.address, int) else None,
        item_player=location.item.player if location.item else None,
        item_name=location.item.name if location.item else None,
        item_id=location.item.code if location.item and isinstance(location.item.code, int) else None,
        item_flags=int(location.item.flags) if location.item else 0,
    )


def decompose_logical_spheres(multiworld: "MultiWorld") -> tuple[list[list["Location"]], list["Location"]]:
    """
    Split MultiWorld logical spheres into reachable sphere lists and unreachable locations.

    Uses MultiWorld.get_spheres(), which may emit:
    - normal sphere sets
    - an empty set separator
    - a final set of unreachable locations
    """
    reachable_spheres: list[list["Location"]] = []
    unreachable_locations: list["Location"] = []
    next_is_unreachable = False

    for raw_sphere in multiworld.get_spheres():
        ordered = _sorted_locations(raw_sphere)

        if not ordered:
            next_is_unreachable = True
            continue

        if next_is_unreachable:
            unreachable_locations.extend(ordered)
            next_is_unreachable = False
        else:
            reachable_spheres.append(ordered)

    return reachable_spheres, unreachable_locations


def build_playthrough_model(multiworld: "MultiWorld") -> PlaythroughModel:
    players = {
        player: {
            "name": multiworld.player_name.get(player, f"Player {player}"),
            "game": multiworld.game.get(player, "Unknown"),
        }
        for player in multiworld.player_ids
    }

    reachable_spheres, unreachable_raw = decompose_logical_spheres(multiworld)

    spheres: list[SphereData] = [
        SphereData(index=sphere_index, locations=[_to_entry(sphere_index, location) for location in locations])
        for sphere_index, locations in enumerate(reachable_spheres)
    ]
    unreachable: list[SphereLocationEntry] = [
        _to_entry(-1, location) for location in unreachable_raw
    ]

    generated_at_utc = datetime.now(timezone.utc).isoformat()

    return PlaythroughModel(
        seed_name=multiworld.seed_name,
        generated_at_utc=generated_at_utc,
        players=players,
        spheres=spheres,
        unreachable_locations=unreachable,
    )
