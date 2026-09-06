"""Agent profile configuration (mirrors ai.models.profiles' load-and-validate pattern)."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain.character.character import CharacterClass


class AgentProfileError(ValueError):
    """Raised when config/agents.toml has a structurally invalid shape."""


class AgentProfileNotFoundError(KeyError):
    """Raised when an unknown agent profile name is requested."""


@dataclass(frozen=True)
class AgentProfile:
    name: str
    character_name: str
    character_class: str
    persona: str
    objective: str
    model_profile: str


@dataclass(frozen=True)
class AgentProfileCatalog:
    max_action_retries: int
    agents: Mapping[str, AgentProfile]

    def get(self, name: str) -> AgentProfile:
        try:
            return self.agents[name]
        except KeyError:
            raise AgentProfileNotFoundError(f"unknown agent profile: {name}") from None


def load_agent_profiles(path: str | Path) -> AgentProfileCatalog:
    """Load [agent] and [agents.*] tables; structure validation only."""
    with Path(path).open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)

    agent_table = data.get("agent", {})
    if not isinstance(agent_table, dict):
        raise AgentProfileError("[agent] must be a table")

    retries = agent_table.get("max_action_retries", 2)
    if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
        raise AgentProfileError("[agent] max_action_retries must be an int >= 0")

    agents_table = data.get("agents", {})
    if not isinstance(agents_table, dict) or not agents_table:
        raise AgentProfileError("[agents] must define at least one agent")

    agents: dict[str, AgentProfile] = {}
    for name, entry in agents_table.items():
        if not isinstance(entry, dict):
            raise AgentProfileError(f"[agents.{name}] must be a table")
        required = {"character_name", "character_class", "persona", "objective", "model_profile"}
        missing = required - set(entry)
        if missing:
            raise AgentProfileError(f"[agents.{name}] missing fields: {sorted(missing)}")
        try:
            CharacterClass(entry["character_class"])
        except ValueError:
            valid = ", ".join(cls.value for cls in CharacterClass)
            raise AgentProfileError(
                f"[agents.{name}] character_class '{entry['character_class']}' "
                f"is not one of: {valid}"
            ) from None
        for field_name in ("character_name", "persona", "objective", "model_profile"):
            value = entry[field_name]
            if not isinstance(value, str) or not value:
                raise AgentProfileError(f"[agents.{name}] {field_name} must be a non-empty string")
        agents[name] = AgentProfile(
            name=name,
            character_name=entry["character_name"],
            character_class=entry["character_class"],
            persona=entry["persona"],
            objective=entry["objective"],
            model_profile=entry["model_profile"],
        )

    return AgentProfileCatalog(max_action_retries=retries, agents=agents)
