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

_VALID = """\
[agent]
max_action_retries = 2

[agents.brix]
character_name = "Brix"
character_class = "fighter"
persona = "A cautious sellsword."
objective = "Engage the nearest threat."
model_profile = "player"
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "agents.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_shipped_config() -> None:
    catalog = load_agent_profiles(_SHIPPED)
    assert catalog.max_action_retries == 2
    brix = catalog.get("brix")
    assert brix.character_name == "Brix"
    assert brix.character_class == "fighter"
    assert brix.model_profile == "player"


def test_defaults_when_agent_table_missing(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[agents.brix]\ncharacter_name = "B"\ncharacter_class = "rogue"\n'
        'persona = "p"\nobjective = "o"\nmodel_profile = "player"\n',
    )
    catalog = load_agent_profiles(path)
    assert catalog.max_action_retries == 2


def test_missing_required_field_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[agents.brix]\ncharacter_name = "B"\ncharacter_class = "fighter"\n'
        'persona = "p"\nmodel_profile = "player"\n',
    )
    with pytest.raises(AgentProfileError, match="missing fields"):
        load_agent_profiles(path)


def test_unknown_character_class_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[agents.brix]\ncharacter_name = "B"\ncharacter_class = "bard"\n'
        'persona = "p"\nobjective = "o"\nmodel_profile = "player"\n',
    )
    with pytest.raises(AgentProfileError, match="character_class"):
        load_agent_profiles(path)


def test_non_string_field_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[agents.brix]\ncharacter_name = "B"\ncharacter_class = "fighter"\n'
        'persona = "p"\nobjective = "o"\nmodel_profile = 3\n',
    )
    with pytest.raises(AgentProfileError, match="model_profile"):
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
