"""load_world_catalog: toml → WorldMap."""

import pytest

from application.world_catalog import InvalidWorldConfigError, load_world_catalog

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
