"""Ruleset selection: config names the id, the factory resolves the directory."""

from pathlib import Path

import pytest

from domain.rules.errors import RulesetError
from session.factory import load_session_ruleset, ruleset_id_from_config


def _config(tmp_path: Path, ruleset_id: str | None) -> Path:
    (tmp_path / "game.toml").write_text(
        f'[ruleset]\nid = "{ruleset_id}"\n' if ruleset_id else "",
        encoding="utf-8",
    )
    return tmp_path


def _data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    shipped = root / "rules" / "dnd5e-srd-5.2"
    shipped.mkdir(parents=True)
    (shipped / "ruleset.toml").write_text(
        'id = "dnd5e-srd-5.2"\nname = "SRD"\n[grid]\ndiagonal_rule = "5_10_5"\n',
        encoding="utf-8",
    )
    (shipped / "weapons.toml").write_text(
        '[[weapon]]\nweapon_id = "club"\nname = "Club"\n'
        "damage_die_count = 1\ndamage_die_size = 4\nability = \"strength\"\n"
        'damage_type = "bludgeoning"\nrange_ft = 5\n',
        encoding="utf-8",
    )
    (shipped / "classes.toml").write_text(
        '[[class]]\nclass_id = "fighter"\nname = "Fighter"\nhit_die_size = 10\n',
        encoding="utf-8",
    )
    (shipped / "statblocks.toml").write_text(
        '[[statblock]]\nstatblock_id = "dummy"\nname = "Dummy"\nlevel = 1\n'
        "strength = 10\ndexterity = 10\nconstitution = 10\nintelligence = 10\n"
        "wisdom = 10\ncharisma = 10\narmor_class = 10\nspeed_ft = 30\n"
        'max_hp = 4\nweapon_id = "club"\n',
        encoding="utf-8",
    )
    return root


def test_config_without_a_ruleset_defaults_to_srd_5_2(tmp_path: Path) -> None:
    assert ruleset_id_from_config(_config(tmp_path, None)) == "dnd5e-srd-5.2"


def test_config_names_the_ruleset_id(tmp_path: Path) -> None:
    assert ruleset_id_from_config(_config(tmp_path, "alt")) == "alt"


def test_selection_loads_the_named_directory(tmp_path: Path) -> None:
    ruleset = load_session_ruleset(
        _config(tmp_path, "dnd5e-srd-5.2"), _data_root(tmp_path)
    )
    assert ruleset.ruleset_id == "dnd5e-srd-5.2"


def test_swapping_the_id_is_config_only(tmp_path: Path) -> None:
    with pytest.raises(RulesetError, match="alt"):
        load_session_ruleset(_config(tmp_path, "alt"), _data_root(tmp_path))
