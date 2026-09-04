import pytest

from domain.character.abilities import AbilityScores, AbilityType
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.common.errors import ValidationError
from domain.common.ids import CharacterId


def _longsword() -> Weapon:
    return Weapon(
        weapon_id="longsword", name="Longsword", damage_die_count=1, damage_die_size=8
    )


def _scores(**overrides: int) -> AbilityScores:
    values = {
        "strength": 16,
        "dexterity": 13,
        "constitution": 15,
        "intelligence": 10,
        "wisdom": 12,
        "charisma": 9,
    }
    values.update(overrides)
    return AbilityScores(**values)


def _character(**overrides: object) -> Character:
    params: dict[str, object] = {
        "id": CharacterId.generate(),
        "name": "Arin",
        "character_type": CharacterType.PLAYER_CHARACTER,
        "character_class": CharacterClass.FIGHTER,
        "level": 1,
        "ability_scores": _scores(),
        "armor_class": 16,
        "speed_ft": 30,
        "hit_points": HitPoints(current=12, maximum=12),
    }
    params.update(overrides)
    return Character(**params)  # type: ignore[arg-type]


def test_character_holds_core_state() -> None:
    arin = _character()
    assert arin.name == "Arin"
    assert arin.character_class is CharacterClass.FIGHTER
    assert arin.is_defeated() is False
    assert arin.conditions == ()


def test_monster_does_not_require_a_class() -> None:
    goblin = _character(
        name="Goblin",
        character_type=CharacterType.MONSTER,
        character_class=None,
        ability_scores=_scores(
            strength=8, dexterity=14, constitution=10, wisdom=8, charisma=8
        ),
        armor_class=13,
        hit_points=HitPoints(current=7, maximum=7),
    )
    assert goblin.character_class is None


def test_player_character_requires_a_class() -> None:
    with pytest.raises(ValidationError):
        _character(character_class=None)


def test_character_range_validation() -> None:
    with pytest.raises(ValidationError):
        _character(level=0)
    with pytest.raises(ValidationError):
        _character(armor_class=0)
    with pytest.raises(ValidationError):
        _character(armor_class=31)
    with pytest.raises(ValidationError):
        _character(speed_ft=0)
    with pytest.raises(ValidationError):
        _character(name="   ")


def test_apply_damage_and_healing_go_through_domain_methods() -> None:
    arin = _character()
    arin.apply_damage(5)
    assert arin.hit_points.current == 7
    arin.apply_healing(2)
    assert arin.hit_points.current == 9
    arin.apply_damage(99)
    assert arin.is_defeated() is True


def test_conditions_add_and_remove() -> None:
    arin = _character()
    arin.add_condition("prone")
    arin.add_condition("prone")  # idempotent
    assert arin.conditions == ("prone",)
    arin.remove_condition("prone")
    assert arin.conditions == ()
    with pytest.raises(ValidationError):
        arin.remove_condition("prone")


def test_equipped_weapon_defaults_to_none() -> None:
    assert _character().equipped_weapon is None
    assert _character(equipped_weapon=_longsword()).equipped_weapon is not None


def test_ability_scores_are_usable_through_character() -> None:
    arin = _character()
    assert arin.ability_scores.modifier(AbilityType.STRENGTH) == 3
