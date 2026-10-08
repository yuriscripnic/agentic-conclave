"""The Ruleset port: data queries the engine makes, errors when data is absent."""

import pytest

from domain.character.abilities import AbilityType
from domain.character.character import CharacterClass
from domain.character.weapon import Weapon
from domain.common.errors import ValidationError
from domain.rules.classes import ClassData
from domain.rules.errors import RulesetError, UnknownRuleEntry
from domain.rules.ruleset import Ruleset
from domain.rules.statblock import Statblock


class _EmptyRuleset:
    """Minimal port stand-in: no data at all."""

    ruleset_id = "test-empty"
    diagonal_rule = "5_10_5"

    def weapon(self, weapon_id: str) -> Weapon:
        raise UnknownRuleEntry("weapon", weapon_id)

    def statblock(self, statblock_id: str) -> Statblock:
        raise UnknownRuleEntry("statblock", statblock_id)

    def character_class(self, class_id: str) -> ClassData:
        raise UnknownRuleEntry("class", class_id)


def test_ruleset_protocol_is_satisfied_by_a_plain_class() -> None:
    ruleset: Ruleset = _EmptyRuleset()
    assert ruleset.ruleset_id == "test-empty"
    assert ruleset.diagonal_rule == "5_10_5"


@pytest.mark.parametrize(
    "kind, attr, entry_id",
    [
        ("weapon", "weapon", "mace2"),
        ("statblock", "statblock", "goblin-9"),
        ("class", "character_class", "bard"),
    ],
)
def test_unknown_entry_raises_with_kind_and_id(
    kind: str, attr: str, entry_id: str
) -> None:
    ruleset: Ruleset = _EmptyRuleset()
    with pytest.raises(UnknownRuleEntry) as exc:
        getattr(ruleset, attr)(entry_id)
    assert exc.value.kind == kind
    assert exc.value.entry_id == entry_id
    assert isinstance(exc.value, RulesetError)


def _statblock(**overrides: object) -> Statblock:
    kwargs: dict[str, object] = {
        "statblock_id": "goblin_scout",
        "name": "Goblin Scout",
        "level": 1,
        "strength": 8,
        "dexterity": 14,
        "constitution": 10,
        "intelligence": 10,
        "wisdom": 8,
        "charisma": 8,
        "armor_class": 13,
        "speed_ft": 30,
        "max_hp": 7,
        "weapon_id": "scimitar",
    }
    kwargs.update(overrides)
    return Statblock(**kwargs)  # type: ignore[arg-type]


def test_statblock_holds_the_enemy_shape() -> None:
    statblock = _statblock()
    assert statblock.weapon_id == "scimitar"
    assert statblock.level == 1


@pytest.mark.parametrize(
    "field, value",
    [("max_hp", 0), ("armor_class", -1), ("speed_ft", 0), ("level", 0), ("level", 21)],
)
def test_statblock_rejects_out_of_range_numbers(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        _statblock(**{field: value})


@pytest.mark.parametrize("field", ["statblock_id", "name", "weapon_id"])
def test_statblock_rejects_blank_strings(field: str) -> None:
    with pytest.raises(ValidationError):
        _statblock(**{field: "  "})


def test_class_data_carries_hit_die() -> None:
    data = ClassData(class_id="fighter", name="Fighter", hit_die_size=10)
    assert data.hit_die_size == 10
    assert data.class_id in {member.value for member in CharacterClass}


def test_class_data_rejects_unknown_class_id() -> None:
    with pytest.raises(ValidationError):
        ClassData(class_id="bard", name="Bard", hit_die_size=8)


def test_class_data_rejects_non_die_hit_die() -> None:
    with pytest.raises(ValidationError):
        ClassData(class_id="fighter", name="Fighter", hit_die_size=7)


def test_weapon_ability_is_a_str_enum_value() -> None:
    weapon = Weapon(
        weapon_id="longsword",
        name="Longsword",
        damage_die_count=1,
        damage_die_size=8,
        ability=AbilityType.STRENGTH,
    )
    assert weapon.ability.value == "strength"
