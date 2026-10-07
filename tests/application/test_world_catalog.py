"""load_world_catalog: toml → WorldMap."""

import pytest

from application.world_catalog import (
    InvalidMapConfigError,
    InvalidWorldConfigError,
    load_battle_map,
    load_world_catalog,
)
from domain.common.errors import ValidationError
from domain.space.board import CoverLevel
from domain.space.square import Square

VALID = """
[world]
start = "courtyard"
enemies_at = "eastern_tower"

[[locations]]
id = "courtyard"
name = "Ruined Courtyard"
description = "Open ground."

[[locations.exits]]
direction = "north"
to = "eastern_tower"

[[locations]]
id = "eastern_tower"
name = "Eastern Tower"
description = "A tower."
"""


def _write(tmp_path, text: str):
    path = tmp_path / "world.toml"
    path.write_text(text)
    return path


def test_loads_locations_and_start(tmp_path) -> None:
    world = load_world_catalog(_write(tmp_path, VALID))
    assert world.by_name("ruined courtyard") is not None
    assert world.by_name("EASTERN TOWER") is not None
    start = world.get(world.start_id)
    assert start.is_exit_to("north") is not None


def test_enemies_at_is_exposed(tmp_path) -> None:
    world = load_world_catalog(_write(tmp_path, VALID))
    assert world.by_name("eastern tower") is not None


def test_duplicate_ids_rejected(tmp_path) -> None:
    doc = VALID + """

[[locations]]
id = "courtyard"
name = "Also Courtyard"
description = "Duplicate."
"""
    with pytest.raises(InvalidWorldConfigError):
        load_world_catalog(_write(tmp_path, doc))


def test_unknown_start_rejected(tmp_path) -> None:
    doc = VALID.replace('start = "courtyard"', 'start = "void"')
    with pytest.raises(InvalidWorldConfigError):
        load_world_catalog(_write(tmp_path, doc))


def test_unknown_exit_destination_rejected(tmp_path) -> None:
    doc = VALID.replace('to = "eastern_tower"', 'to = "void"')
    with pytest.raises(InvalidWorldConfigError):
        load_world_catalog(_write(tmp_path, doc))


@pytest.mark.parametrize("text", ["", '[world]\nstart = "a"\n'])
def test_missing_sections_rejected(tmp_path, text: str) -> None:
    with pytest.raises(InvalidWorldConfigError):
        load_world_catalog(_write(tmp_path, text))


VALID_MAP = """\
[map]
name = "Test Room"
width = 5
height = 5
walls = [[0, 0]]

[[cover]]
square = [2, 2]
level = "half"

[spawns.party]
squares = [[1, 1]]

[spawns.enemies]
squares = [[4, 4]]
"""


def _write_map(tmp_path, text: str):
    path = tmp_path / "map.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_battle_map_parses_board_cover_and_spawns(tmp_path) -> None:
    battle_map = load_battle_map(_write_map(tmp_path, VALID_MAP))
    assert battle_map.board.width == 5
    assert battle_map.board.is_wall(Square(0, 0))
    assert battle_map.board.cover_at(Square(2, 2)) is CoverLevel.HALF
    assert battle_map.spawns.party == (Square(1, 1),)
    assert battle_map.spawns.enemies == (Square(4, 4),)


P = "[spawns.party]\nsquares = [[1,1]]\n"
E = "[spawns.enemies]\nsquares = [[4,4]]\n"
H = '[map]\nwidth = 5\nheight = 5\n'


@pytest.mark.parametrize(
    "text",
    [
        H + P,  # no spawns.enemies
        H + 'walls = [[9, 9]]\n' + P + E,  # wall out of bounds
        H + '[[cover]]\nsquare = [1,1]\nlevel = "murk"\n' + P + E,  # unknown level
        H  # duplicate cover
        + '[[cover]]\nsquare = [1,1]\nlevel = "half"\n[[cover]]\nsquare = [1,1]\n'
        + 'level = "half"\n'
        + P
        + E,
        "width = 5\nheight = 5\n",  # no [map] table
    ],
)
def test_malformed_maps_fail_loudly_at_load(tmp_path, text: str) -> None:
    with pytest.raises((InvalidMapConfigError, ValidationError)):
        load_battle_map(_write_map(tmp_path, text))
