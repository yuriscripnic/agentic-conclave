"""Location and WorldMap value objects are pure domain types (spec Task 1)."""

import pytest

from domain.common.ids import LocationId
from domain.world.locations import Location, LocationExit, WorldMap


def _world() -> WorldMap:
    courtyard = LocationId.generate()
    tower = LocationId.generate()
    locations = {
        courtyard: Location(
            id=courtyard,
            name="Ruined Courtyard",
            description="Broken flagstones under an open sky.",
            exits=(LocationExit(direction="north", destination=tower),),
        ),
        tower: Location(
            id=tower,
            name="Eastern Tower",
            description="A weathered stone tower.",
            exits=(LocationExit(direction="south", destination=courtyard),),
        ),
    }
    return WorldMap(locations=locations, start_id=courtyard)


def test_exit_lookup_is_case_insensitive() -> None:
    world = _world()
    start = world.get(world.start_id)
    assert start.is_exit_to("NORTH") is not None
    assert start.exit("north") is not None


def test_unknown_exit_returns_none() -> None:
    world = _world()
    start = world.get(world.start_id)
    assert start.exit("west") is None
    assert start.is_exit_to("east") is None


def test_by_name_matches_location() -> None:
    world = _world()
    assert world.by_name("eastern tower") is not None
    assert world.by_name("EASTERN TOWER") is not None
    assert world.by_name("nope") is None


def test_get_unknown_location_raises() -> None:
    with pytest.raises(KeyError):
        _world().get(LocationId.generate())
