import pytest

from domain.character.abilities import AbilityType
from domain.character.weapon import Weapon
from domain.common.errors import ValidationError


def test_weapon_defaults() -> None:
    sword = Weapon(
        weapon_id="longsword", name="Longsword", damage_die_count=1, damage_die_size=8
    )
    assert sword.ability is AbilityType.STRENGTH
    assert sword.range_ft == 5


def test_weapon_rejects_bad_die() -> None:
    with pytest.raises(ValidationError):
        Weapon(weapon_id="x", name="X", damage_die_count=0, damage_die_size=6)
    with pytest.raises(ValidationError):
        Weapon(weapon_id="x", name="X", damage_die_count=1, damage_die_size=7)


def test_weapon_rejects_bad_range_or_names() -> None:
    with pytest.raises(ValidationError):
        Weapon(
            weapon_id="x", name="X", damage_die_count=1, damage_die_size=6, range_ft=0
        )
    with pytest.raises(ValidationError):
        Weapon(weapon_id=" ", name="X", damage_die_count=1, damage_die_size=6)
