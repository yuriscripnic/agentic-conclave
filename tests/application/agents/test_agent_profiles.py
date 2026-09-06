"""Agent profile catalog loading tests."""

from pathlib import Path

import pytest

from application.agents.profiles import (
    AgentProfileCatalog,
    AgentProfileError,
    AgentProfileNotFoundError,
    load_agent_profiles,
)

_SHIPPED = Path(__file__).resolve().parents[3] / "config" / "agents.toml"

_STATS = """\
[agents.brix.stats]
strength = 16
dexterity = 13
constitution = 15
intelligence = 10
wisdom = 12
charisma = 9
armor_class = 16
speed_ft = 30
max_hp = 12

[agents.brix.stats.weapon]
weapon_id = "longsword"
name = "Longsword"
damage_die_count = 1
damage_die_size = 8
"""

_VALID = """\
[agent]
max_action_retries = 2

[agents.brix]
character_name = "Brix"
character_class = "fighter"
persona = "A cautious sellsword."
objective = "Engage the nearest threat."
model_profile = "player"

""" + _STATS


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "agents.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_shipped_config_with_three_agents() -> None:
    catalog = load_agent_profiles(_SHIPPED)
    assert catalog.max_action_retries == 2
    assert set(catalog.agents) == {"brix", "mira", "sera"}
    brix = catalog.get("brix")
    assert brix.character_name == "Brix"
    assert brix.character_class == "fighter"
    assert brix.model_profile == "player"
    assert brix.stats.strength == 16
    assert brix.stats.weapon.weapon_id == "longsword"
    mira = catalog.get("mira")
    assert mira.character_class == "rogue"
    assert mira.stats.dexterity == 16
    assert mira.stats.weapon.weapon_id == "shortsword"
    sera = catalog.get("sera")
    assert sera.character_class == "cleric"
    assert sera.stats.wisdom == 16
    assert sera.stats.weapon.weapon_id == "mace"


def test_defaults_when_agent_table_missing(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace("[agent]\nmax_action_retries = 2\n\n", ""))
    catalog = load_agent_profiles(path)
    assert catalog.max_action_retries == 2


def test_missing_required_field_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _VALID.replace('persona = "A cautious sellsword."\n', ""),
    )
    with pytest.raises(AgentProfileError, match="missing fields"):
        load_agent_profiles(path)


def test_unknown_character_class_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace('"fighter"', '"bard"'))
    with pytest.raises(AgentProfileError, match="character_class"):
        load_agent_profiles(path)


def test_non_string_field_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _VALID.replace('objective = "Engage the nearest threat."', "objective = 3"),
    )
    with pytest.raises(AgentProfileError, match="objective"):
        load_agent_profiles(path)


def test_empty_agents_table_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "[agent]\nmax_action_retries = 1\n")
    with pytest.raises(AgentProfileError, match="at least one agent"):
        load_agent_profiles(path)


def test_negative_retries_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace("max_action_retries = 2", "max_action_retries = -1"))
    with pytest.raises(AgentProfileError, match="max_action_retries"):
        load_agent_profiles(path)


def test_unknown_agent_name_raises_not_found() -> None:
    catalog = AgentProfileCatalog(max_action_retries=2, agents={})
    with pytest.raises(AgentProfileNotFoundError):
        catalog.get("nobody")


def test_missing_stats_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID[: _VALID.index("[agents.brix.stats]")])
    with pytest.raises(AgentProfileError, match="stats"):
        load_agent_profiles(path)


def test_partial_stats_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace("wisdom = 12\n", ""))
    with pytest.raises(AgentProfileError, match="wisdom"):
        load_agent_profiles(path)


def test_non_positive_stat_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace("max_hp = 12", "max_hp = 0"))
    with pytest.raises(AgentProfileError, match="max_hp"):
        load_agent_profiles(path)


def test_missing_weapon_table_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID[: _VALID.index("[agents.brix.stats.weapon]")])
    with pytest.raises(AgentProfileError, match=r"stats\.weapon"):
        load_agent_profiles(path)


def test_non_positive_weapon_die_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace("damage_die_size = 8", "damage_die_size = 0"))
    with pytest.raises(AgentProfileError, match="damage_die_size"):
        load_agent_profiles(path)
