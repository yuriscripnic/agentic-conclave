"""Encounter configuration loading tests."""

from pathlib import Path

import pytest

from application.encounter import EncounterError, load_encounter

# --- R2: enemies reference ruleset statblocks; the loader resolves them ---

_SHIPPED = Path(__file__).resolve().parents[2] / "config" / "encounter.toml"
_SHIPPED_RULESET = Path(__file__).resolve().parents[2] / "data/rules/dnd5e-srd-5.2"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "encounter.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_resolves_the_three_enemies_from_statblocks() -> None:
    from infrastructure.rules.loader import load_ruleset

    commands = load_encounter(_SHIPPED, load_ruleset(_SHIPPED_RULESET))
    assert [command.name for command in commands] == [
        "Goblin Scout",
        "Goblin Skulker",
        "Orc Brute",
    ]


def test_statblock_numbers_survive_the_migration() -> None:
    """Byte-equivalence with the pre-migration encounter.toml values."""
    from infrastructure.rules.loader import load_ruleset

    scout, skulker, orc = load_encounter(_SHIPPED, load_ruleset(_SHIPPED_RULESET))
    for command in (scout, skulker):
        assert (command.strength, command.dexterity, command.constitution) == (8, 14, 10)
        assert command.armor_class == 13
        assert command.max_hp == 7
        assert command.weapon is not None
        assert command.weapon.weapon_id == "scimitar"
        assert command.weapon.damage_die_size == 6
    assert (orc.strength, orc.dexterity, orc.constitution) == (16, 12, 14)
    assert orc.armor_class == 15
    assert orc.max_hp == 15
    assert orc.weapon is not None
    assert orc.weapon.weapon_id == "greataxe"
    assert orc.weapon.damage_die_size == 12


def test_unknown_statblock_id_is_rejected(
    tmp_path: Path,
) -> None:
    from domain.rules.errors import UnknownRuleEntry
    from infrastructure.rules.loader import load_ruleset

    path = _write(tmp_path, '[[enemies]]\nstatblock = "dragon_boss"\n')
    with pytest.raises((EncounterError, UnknownRuleEntry)):
        load_encounter(path, load_ruleset(_SHIPPED_RULESET))


def test_missing_statblock_key_is_rejected(tmp_path: Path) -> None:
    from infrastructure.rules.loader import load_ruleset

    path = _write(tmp_path, '[[enemies]]\nname = "Lone"\n')
    with pytest.raises(EncounterError):
        load_encounter(path, load_ruleset(_SHIPPED_RULESET))
