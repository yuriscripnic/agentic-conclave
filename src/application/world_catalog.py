"""load_world_catalog: toml → WorldMap; load_battle_map: toml → BattleMap.

Application owns I/O; domain types stay pure.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from domain.common.errors import ValidationError
from domain.common.ids import LocationId
from domain.space.board import Board, CoverLevel, Spawns
from domain.space.square import Square
from domain.world.locations import Location, LocationExit, WorldMap


class InvalidWorldConfigError(ValueError):
    pass


@dataclass(frozen=True)
class BattleMap:
    """A board plus the spawn squares an encounter's combatants start on."""

    board: Board
    spawns: Spawns


class InvalidMapConfigError(ValueError):
    pass


def _map_int(table: dict[str, object], key: str, where: str) -> int:
    value = table.get(key)
    if not isinstance(value, int) or value < 1:
        raise InvalidMapConfigError(f"{where} needs a positive integer '{key}'")
    return value


def _map_square(value: object, where: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2 or not all(
        isinstance(item, int) for item in value
    ):
        raise InvalidMapConfigError(f"{where} needs a [x, y] square, got {value!r}")
    return (value[0], value[1])


def _map_squares(value: object, where: str) -> list[tuple[int, int]]:
    if not isinstance(value, list):
        raise InvalidMapConfigError(f"{where} needs a list of [x, y] squares")
    return [_map_square(entry, where) for entry in value]


def load_battle_map(path: Path) -> BattleMap:
    """toml -> BattleMap; every malformation fails loudly here, never mid-combat."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    table = data.get("map")
    if not isinstance(table, dict):
        raise InvalidMapConfigError(f"{path.name} needs a [map] table")
    width = _map_int(table, "width", path.name)
    height = _map_int(table, "height", path.name)
    walls = frozenset(
        Square(x, y) for x, y in _map_squares(table.get("walls", []), path.name)
    )
    cover: dict[Square, CoverLevel] = {}
    for entry in data.get("cover", []):
        if not isinstance(entry, dict):
            raise InvalidMapConfigError(f"{path.name}: each [[cover]] must be a table")
        x, y = _map_square(entry.get("square"), path.name)
        try:
            level = CoverLevel(str(entry.get("level")))
        except ValueError as error:
            raise InvalidMapConfigError(
                f"{path.name}: unknown cover level {entry.get('level')!r}"
            ) from error
        if Square(x, y) in cover:
            raise InvalidMapConfigError(f"{path.name}: duplicate cover square ({x}, {y})")
        cover[Square(x, y)] = level
    spawns_table = data.get("spawns")
    if not isinstance(spawns_table, dict):
        raise InvalidMapConfigError(f"{path.name} needs a [spawns] table")
    party_table = spawns_table.get("party")
    enemies_table = spawns_table.get("enemies")
    if not isinstance(party_table, dict) or not isinstance(enemies_table, dict):
        raise InvalidMapConfigError(f"{path.name}: [spawns] needs party and enemies")
    try:
        board = Board(width=width, height=height, walls=walls, cover=cover)
    except ValidationError as error:
        raise InvalidMapConfigError(f"{path.name}: {error}") from error
    return BattleMap(
        board=board,
        spawns=Spawns(
            party=tuple(
                Square(x, y)
                for x, y in _map_squares(party_table.get("squares", []), path.name)
            ),
            enemies=tuple(
                Square(x, y)
                for x, y in _map_squares(enemies_table.get("squares", []), path.name)
            ),
        ),
    )


def _require(world: dict[str, object], key: str) -> str:
    value = world.get(key)
    if not isinstance(value, str) or not value:
        raise InvalidWorldConfigError(f"world.toml missing '{key}'")
    return value


def load_world_catalog(path: Path) -> WorldMap:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    world = data.get("world")
    raw_locations = data.get("locations")
    if not isinstance(world, dict):
        raise InvalidWorldConfigError("world.toml needs a [world] table")
    if not isinstance(raw_locations, list) or not raw_locations:
        raise InvalidWorldConfigError("world.toml needs at least one [[locations]]")

    ids: dict[str, LocationId] = {}
    for entry in raw_locations:
        if not isinstance(entry, dict):
            raise InvalidWorldConfigError("each [[locations]] entry must be a table")
        key = entry.get("id")
        if not isinstance(key, str) or not key:
            raise InvalidWorldConfigError(f"bad location id: {key!r}")
        if key in ids:
            raise InvalidWorldConfigError(f"duplicate location id: {key}")
        ids[key] = LocationId.generate()

    locations: dict[LocationId, Location] = {}
    for entry in raw_locations:
        assert isinstance(entry, dict)
        location_id = ids[str(entry["id"])]
        exits: tuple[LocationExit, ...] = ()
        for exit_ in entry.get("exits", []):
            destination_key = exit_["to"]
            if destination_key not in ids:
                raise InvalidWorldConfigError(
                    f"location '{entry['id']}' has exit to unknown '{destination_key}'"
                )
            exits += (
                LocationExit(
                    direction=str(exit_["direction"]),
                    destination=ids[str(destination_key)],
                ),
            )
        destinations = {exit_.destination for exit_ in exits}
        if len(destinations) != len(exits):
            raise InvalidWorldConfigError(f"location '{entry['id']}' has duplicate exits")
        locations[location_id] = Location(
            id=location_id,
            name=str(entry["name"]),
            description=str(entry.get("description", "")),
            exits=exits,
        )

    start = _require(world, "start")
    if start not in ids:
        raise InvalidWorldConfigError(f"[world].start '{start}' is not a location id")
    enemies_at = world.get("enemies_at")
    return WorldMap(
        locations=locations,
        start_id=ids[start],
        enemies_at=ids[enemies_at] if isinstance(enemies_at, str) else None,
    )
