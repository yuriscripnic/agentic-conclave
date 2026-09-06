"""Encounter configuration loading tests."""

from pathlib import Path

import pytest

from application.commands import AddCharacterCommand, WeaponSpec
from application.encounter import EncounterError, load_encounter

_SHIPPED = Path(__file__).resolve().parents[2] / "config" / "encounter.toml"

_VALID = """\
[[enemies]]
name = "Goblin Scout"
level = 1
strength = 8
dexterity = 14
constitution = 10
intelligence = 10
wisdom = 8
charisma = 8
armor_class = 13
speed_ft = 30
max_hp = 7
weapon = { weapon_id = "scimitar", name = "Scimitar", damage_die_count = 1, damage_die_size = 6 }
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "encounter.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_shipped_encounter_as_enemy_commands() -> None:
    commands = load_encounter(_SHIPPED)
    names = [command.name for command in commands]
    assert names == ["Goblin Scout", "Goblin Skulker", "Orc Brute"]
    assert all(command.character_type == "enemy" for command in commands)
    orc = commands[2]
    assert orc.strength == 16
    assert orc.armor_class == 15
    assert orc.max_hp == 15
    assert orc.weapon is not None
    assert orc.weapon.weapon_id == "greataxe"


def test_maps_stats_and_weapon(tmp_path: Path) -> None:
    (command,) = load_encounter(_write(tmp_path, _VALID))
    assert isinstance(command, AddCharacterCommand)
    assert command.character_type == "enemy"
    assert command.level == 1
    assert command.dexterity == 14
    assert command.max_hp == 7
    assert command.weapon == WeaponSpec(
        weapon_id="scimitar",
        name="Scimitar",
        damage_die_count=1,
        damage_die_size=6,
    )


def test_missing_name_raises(tmp_path: Path) -> None:
    with pytest.raises(EncounterError, match="name"):
        load_encounter(_write(tmp_path, _VALID.replace('name = "Goblin Scout"\n', "")))


def test_non_positive_stat_raises(tmp_path: Path) -> None:
    with pytest.raises(EncounterError, match="max_hp"):
        load_encounter(_write(tmp_path, _VALID.replace("max_hp = 7", "max_hp = 0")))


def test_duplicate_name_raises(tmp_path: Path) -> None:
    text = _VALID + _VALID.replace("Goblin Scout", "goblin scout")
    with pytest.raises(EncounterError, match="duplicate enemy name"):
        load_encounter(_write(tmp_path, text))


def test_empty_enemies_raises(tmp_path: Path) -> None:
    with pytest.raises(EncounterError, match="at least one enemy"):
        load_encounter(_write(tmp_path, ""))
