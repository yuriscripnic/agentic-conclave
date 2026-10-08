"""The loader validates strictly: malformed data fails at load, not mid-game."""

from pathlib import Path

import pytest

from domain.character.abilities import AbilityType
from domain.rules.errors import RulesetError, UnknownRuleEntry
from infrastructure.rules.loader import load_ruleset

SHIPPED = Path(__file__).resolve().parents[3] / "data/rules/dnd5e-srd-5.2"


def test_loads_the_shipped_ruleset() -> None:
    ruleset = load_ruleset(SHIPPED)
    assert ruleset.ruleset_id == "dnd5e-srd-5.2"
    assert ruleset.diagonal_rule == "5_10_5"


def test_shipped_weapons_resolve_to_domain_objects() -> None:
    ruleset = load_ruleset(SHIPPED)
    longsword = ruleset.weapon("longsword")
    assert longsword.damage_die_size == 8
    assert longsword.ability is AbilityType.STRENGTH
    scimitar = ruleset.weapon("scimitar")
    assert scimitar.ability is AbilityType.DEXTERITY


def test_shipped_statblocks_and_classes_resolve() -> None:
    ruleset = load_ruleset(SHIPPED)
    orc = ruleset.statblock("orc_brute")
    assert orc.max_hp == 15
    assert orc.weapon_id == "greataxe"
    fighter = ruleset.character_class("fighter")
    assert fighter.hit_die_size == 10


def test_unknown_ids_raise_unknown_rule_entry() -> None:
    ruleset = load_ruleset(SHIPPED)
    with pytest.raises(UnknownRuleEntry):
        ruleset.weapon("mace2")
    with pytest.raises(UnknownRuleEntry):
        ruleset.statblock("goblin-9")


def test_missing_directory_names_the_path() -> None:
    with pytest.raises(RulesetError, match="no-such-ruleset"):
        load_ruleset(Path("/tmp/rules-data/no-such-ruleset"))


def _write(tmp_path: Path, name: str, text: str) -> None:
    directory = tmp_path / "test-ruleset"
    directory.mkdir(exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


def _minimal_ruleset(tmp_path: Path, overrides: dict[str, str] | None = None) -> Path:
    """A tiny valid ruleset; entries in `overrides` replace whole files."""
    files = {
        "ruleset.toml": 'id = "test"\nname = "Test"\n[grid]\ndiagonal_rule = "5_10_5"\n',
        "weapons.toml": (
            '[[weapon]]\nweapon_id = "club"\nname = "Club"\n'
            "damage_die_count = 1\ndamage_die_size = 4\nability = \"strength\"\n"
            'damage_type = "bludgeoning"\nrange_ft = 5\n'
        ),
        "classes.toml": (
            '[[class]]\nclass_id = "fighter"\nname = "Fighter"\nhit_die_size = 10\n'
        ),
        "statblocks.toml": (
            '[[statblock]]\nstatblock_id = "dummy"\nname = "Dummy"\nlevel = 1\n'
            "strength = 10\ndexterity = 10\nconstitution = 10\nintelligence = 10\n"
            "wisdom = 10\ncharisma = 10\narmor_class = 10\nspeed_ft = 30\n"
            'max_hp = 4\nweapon_id = "club"\n'
        ),
    }
    files.update(overrides or {})
    for name, text in files.items():
        _write(tmp_path, name, text)
    return tmp_path / "test-ruleset"


def test_missing_required_file_is_a_load_error(tmp_path: Path) -> None:
    directory = tmp_path / "test-ruleset"
    directory.mkdir()
    (directory / "ruleset.toml").write_text(
        'id = "test"\n[grid]\ndiagonal_rule = "5_10_5"\n', encoding="utf-8"
    )
    with pytest.raises(RulesetError, match="weapons.toml"):
        load_ruleset(directory)


def test_unknown_die_size_is_a_load_error(tmp_path: Path) -> None:
    directory = _minimal_ruleset(
        tmp_path,
        {
            "weapons.toml": '[[weapon]]\nweapon_id = "club"\nname = "Club"\n'
            "damage_die_count = 1\ndamage_die_size = 7\n"
            'ability = "strength"\ndamage_type = "bludgeoning"\n'
            "range_ft = 5\n"
        },
    )
    with pytest.raises(RulesetError, match="die size"):
        load_ruleset(directory)


def test_unknown_ability_is_a_load_error(tmp_path: Path) -> None:
    directory = _minimal_ruleset(
        tmp_path,
        {
            "weapons.toml": '[[weapon]]\nweapon_id = "club"\nname = "Club"\n'
            "damage_die_count = 1\ndamage_die_size = 4\n"
            'ability = "charisma2"\ndamage_type = "bludgeoning"\n'
            "range_ft = 5\n"
        },
    )
    with pytest.raises(RulesetError, match="ability"):
        load_ruleset(directory)


def test_dangling_statblock_weapon_fails_at_load(tmp_path: Path) -> None:
    directory = _minimal_ruleset(
        tmp_path,
        {
            "statblocks.toml": '[[statblock]]\nstatblock_id = "dummy"\nname = "Dummy"\n'
            "level = 1\nstrength = 10\ndexterity = 10\n"
            "constitution = 10\nintelligence = 10\nwisdom = 10\n"
            "charisma = 10\narmor_class = 10\nspeed_ft = 30\n"
            'max_hp = 4\nweapon_id = "greatclub"\n'
        },
    )
    with pytest.raises(RulesetError, match="dummy"):
        load_ruleset(directory)


def test_duplicate_weapon_id_is_a_load_error(tmp_path: Path) -> None:
    directory = _minimal_ruleset(
        tmp_path,
        {
            "weapons.toml": (
                '[[weapon]]\nweapon_id = "club"\nname = "Club"\n'
                "damage_die_count = 1\ndamage_die_size = 4\nability = \"strength\"\n"
                'damage_type = "bludgeoning"\nrange_ft = 5\n'
                '[[weapon]]\nweapon_id = "club"\nname = "Club II"\n'
                "damage_die_count = 1\ndamage_die_size = 6\nability = \"strength\"\n"
                'damage_type = "bludgeoning"\nrange_ft = 5\n'
            )
        },
    )
    with pytest.raises(RulesetError, match="duplicate"):
        load_ruleset(directory)


def test_unknown_diagonal_rule_is_a_load_error(tmp_path: Path) -> None:
    directory = _minimal_ruleset(
        tmp_path, {"ruleset.toml": 'id = "test"\n[grid]\ndiagonal_rule = "3_3_3"\n'}
    )
    with pytest.raises(RulesetError, match="diagonal_rule"):
        load_ruleset(directory)


def test_wrong_value_type_is_a_load_error(tmp_path: Path) -> None:
    directory = _minimal_ruleset(
        tmp_path,
        {
            "classes.toml": '[[class]]\nclass_id = "fighter"\nname = "Fighter"\n'
            'hit_die_size = "ten"\n'
        },
    )
    with pytest.raises(RulesetError):
        load_ruleset(directory)
