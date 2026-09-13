"""load_world_catalog: toml → WorldMap. Application owns I/O; domain types stay pure."""

from __future__ import annotations

import tomllib
from pathlib import Path

from domain.common.ids import LocationId
from domain.world.locations import Location, LocationExit, WorldMap


class InvalidWorldConfigError(ValueError):
    pass


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
