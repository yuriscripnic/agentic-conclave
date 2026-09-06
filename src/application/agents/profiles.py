"""Agent profile configuration (mirrors ai.models.profiles' load-and-validate pattern)."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from application.commands import WeaponSpec
from domain.character.character import CharacterClass


class AgentProfileError(ValueError):
    """Raised when config/agents.toml has a structurally invalid shape."""


class AgentProfileNotFoundError(KeyError):
    """Raised when an unknown agent profile name is requested."""


@dataclass(frozen=True)
class AgentStats:
    """The character statline an agent-controlled character is created with (spec §3.2)."""

    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int
    armor_class: int
    speed_ft: int
    max_hp: int
    weapon: WeaponSpec


@dataclass(frozen=True)
class AgentProfile:
    name: str
    character_name: str
    character_class: str
    persona: str
    objective: str
    model_profile: str
    stats: AgentStats


@dataclass(frozen=True)
class AgentProfileCatalog:
    max_action_retries: int
    agents: Mapping[str, AgentProfile]

    def get(self, name: str) -> AgentProfile:
        try:
            return self.agents[name]
        except KeyError:
            raise AgentProfileNotFoundError(f"unknown agent profile: {name}") from None


_STAT_INT_FIELDS = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
    "armor_class",
    "speed_ft",
    "max_hp",
)


def _positive_int(table: Mapping[str, Any], key: str, where: str) -> int:
    value = table.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AgentProfileError(f"{where} {key} must be an int >= 1")
    return value


def _load_stats(agent_table: Mapping[str, Any], name: str) -> AgentStats:
    where = f"[agents.{name}]"
    stats = agent_table.get("stats")
    if not isinstance(stats, dict):
        raise AgentProfileError(f"{where} stats must be a table")
    values = {field: _positive_int(stats, field, where) for field in _STAT_INT_FIELDS}
    weapon_where = f"{where} stats.weapon"
    weapon = stats.get("weapon")
    if not isinstance(weapon, dict):
        raise AgentProfileError(f"{weapon_where} must be a table")
    for key in ("weapon_id", "name"):
        value = weapon.get(key)
        if not isinstance(value, str) or not value:
            raise AgentProfileError(f"{weapon_where}.{key} must be a non-empty string")
    return AgentStats(
        **values,
        weapon=WeaponSpec(
            weapon_id=weapon["weapon_id"],
            name=weapon["name"],
            damage_die_count=_positive_int(weapon, "damage_die_count", weapon_where),
            damage_die_size=_positive_int(weapon, "damage_die_size", weapon_where),
        ),
    )


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
            stats=_load_stats(entry, name),
        )

    return AgentProfileCatalog(max_action_retries=retries, agents=agents)
