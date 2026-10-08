"""The shipped SRD 5.2 data files parse and carry the ids the configs reference."""

import tomllib
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data/rules/dnd5e-srd-5.2"


def _rows(name: str) -> list[dict[str, object]]:
    with (DATA / name).open("rb") as handle:
        document = tomllib.load(handle)
    rows = next(iter(document.values()), None)
    assert isinstance(rows, list)
    return rows  # type: ignore[return-value]


def test_ruleset_toml_declares_id_and_diagonal_rule() -> None:
    with (DATA / "ruleset.toml").open("rb") as handle:
        data = tomllib.load(handle)
    assert data["id"] == "dnd5e-srd-5.2"
    assert data["grid"]["diagonal_rule"] == "5_10_5"


def test_weapons_toml_defines_the_five_weapons_in_play() -> None:
    ids = {row["weapon_id"] for row in _rows("weapons.toml")}
    assert ids == {"longsword", "shortsword", "mace", "scimitar", "greataxe"}


def test_weapons_toml_rows_carry_dice_and_damage_type() -> None:
    rows = {row["weapon_id"]: row for row in _rows("weapons.toml")}
    longsword = rows["longsword"]
    assert longsword["damage_die_count"] == 1
    assert longsword["damage_die_size"] == 8
    assert longsword["ability"] == "strength"
    assert isinstance(longsword["damage_type"], str)


def test_classes_toml_defines_the_four_classes() -> None:
    rows = {row["class_id"]: row for row in _rows("classes.toml")}
    assert set(rows) == {"fighter", "rogue", "wizard", "cleric"}
    assert rows["fighter"]["hit_die_size"] == 10
    assert rows["wizard"]["hit_die_size"] == 6


def test_statblocks_toml_matches_todays_encounter() -> None:
    """Byte-equivalence with config/encounter.toml before the migration."""
    rows = {row["statblock_id"]: row for row in _rows("statblocks.toml")}
    assert set(rows) == {"goblin_scout", "goblin_skulker", "orc_brute"}
    goblin = rows["goblin_scout"]
    assert goblin["level"] == 1
    assert goblin["strength"] == 8
    assert goblin["dexterity"] == 14
    assert goblin["constitution"] == 10
    assert goblin["intelligence"] == 10
    assert goblin["wisdom"] == 8
    assert goblin["charisma"] == 8
    assert goblin["armor_class"] == 13
    assert goblin["speed_ft"] == 30
    assert goblin["max_hp"] == 7
    assert goblin["weapon_id"] == "scimitar"
    orc = rows["orc_brute"]
    assert orc["strength"] == 16
    assert orc["armor_class"] == 15
    assert orc["max_hp"] == 15
    assert orc["weapon_id"] == "greataxe"


def test_notice_is_present_with_attribution() -> None:
    notice = (DATA.parent / "NOTICE").read_text(encoding="utf-8")
    assert "CC-BY-4.0" in notice
    assert "SRD 5.2" in notice
