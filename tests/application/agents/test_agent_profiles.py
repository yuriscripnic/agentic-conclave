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
_RULES_DATA = Path(__file__).resolve().parents[3] / "data" / "rules" / "dnd5e-srd-5.2"

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

weapon_id = "longsword"
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


def _ruleset() -> object:
    from infrastructure.rules.loader import load_ruleset

    return load_ruleset(_RULES_DATA)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "agents.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_shipped_config_with_three_agents() -> None:
    catalog = load_agent_profiles(_SHIPPED, _ruleset())
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
    catalog = load_agent_profiles(path, _ruleset())
    assert catalog.max_action_retries == 2


def test_missing_required_field_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _VALID.replace('persona = "A cautious sellsword."\n', ""),
    )
    with pytest.raises(AgentProfileError, match="missing fields"):
        load_agent_profiles(path, _ruleset())


def test_unknown_character_class_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace('"fighter"', '"bard"'))
    with pytest.raises(AgentProfileError, match="character_class"):
        load_agent_profiles(path, _ruleset())


def test_non_string_field_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _VALID.replace('objective = "Engage the nearest threat."', "objective = 3"),
    )
    with pytest.raises(AgentProfileError, match="objective"):
        load_agent_profiles(path, _ruleset())


def test_empty_agents_table_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "[agent]\nmax_action_retries = 1\n")
    with pytest.raises(AgentProfileError, match="at least one agent"):
        load_agent_profiles(path, _ruleset())


def test_negative_retries_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace("max_action_retries = 2", "max_action_retries = -1"))
    with pytest.raises(AgentProfileError, match="max_action_retries"):
        load_agent_profiles(path, _ruleset())


def test_unknown_agent_name_raises_not_found() -> None:
    catalog = AgentProfileCatalog(max_action_retries=2, agents={})
    with pytest.raises(AgentProfileNotFoundError):
        catalog.get("nobody")


def test_missing_stats_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID[: _VALID.index("[agents.brix.stats]")])
    with pytest.raises(AgentProfileError, match="stats"):
        load_agent_profiles(path, _ruleset())


def test_partial_stats_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace("wisdom = 12\n", ""))
    with pytest.raises(AgentProfileError, match="wisdom"):
        load_agent_profiles(path, _ruleset())


def test_non_positive_stat_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace("max_hp = 12", "max_hp = 0"))
    with pytest.raises(AgentProfileError, match="max_hp"):
        load_agent_profiles(path, _ruleset())


def test_missing_weapon_id_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace('weapon_id = "longsword"\n', ""))
    with pytest.raises(AgentProfileError, match=r"stats\.weapon_id"):
        load_agent_profiles(path, _ruleset())


# --- R2: agent weapons become ruleset ids resolved through the ruleset ---

_RULES_DATA = Path(__file__).resolve().parents[3] / "data" / "rules" / "dnd5e-srd-5.2"


def test_stats_carry_a_weapon_id_resolved_through_the_ruleset() -> None:
    from infrastructure.rules.loader import load_ruleset

    catalog = load_agent_profiles(_SHIPPED, load_ruleset(_RULES_DATA))
    brix = catalog.agents["brix"]
    assert brix.stats.weapon_id == "longsword"
    assert brix.stats.weapon is not None
    assert brix.stats.weapon.damage_die_size == 8
    assert brix.stats.weapon.weapon_id == "longsword"


def test_unknown_agent_weapon_id_is_rejected(tmp_path: Path) -> None:
    from domain.rules.errors import UnknownRuleEntry
    from infrastructure.rules.loader import load_ruleset

    ruleset = load_ruleset(_RULES_DATA)
    text = _SHIPPED.read_text(encoding="utf-8").replace(
        'weapon_id = "longsword"', 'weapon_id = "vorpal_blade"'
    )
    path = _write(tmp_path, text)
    with pytest.raises(UnknownRuleEntry):
        load_agent_profiles(path, ruleset)
