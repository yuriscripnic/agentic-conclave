"""Encounter configuration (spec §3.3): the fight is data, in every CLI mode."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from application.commands import AddCharacterCommand, WeaponSpec


class EncounterError(ValueError):
    """Raised when config/encounter.toml has a structurally invalid shape."""


@dataclass(frozen=True)
class EnemySpec:
    """One validated enemy definition before it becomes an AddCharacterCommand."""

    name: str
    level: int
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


def _positive_int(table: dict[str, Any], key: str, where: str) -> int:
    value = table.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise EncounterError(f"{where} {key} must be an int >= 1")
    return value


def _weapon(entry: dict[str, Any], where: str) -> WeaponSpec:
    weapon = entry.get("weapon")
    if not isinstance(weapon, dict):
        raise EncounterError(f"{where} weapon must be a table")
    for key in ("weapon_id", "name"):
        value = weapon.get(key)
        if not isinstance(value, str) or not value:
            raise EncounterError(f"{where} weapon.{key} must be a non-empty string")
    return WeaponSpec(
        weapon_id=weapon["weapon_id"],
        name=weapon["name"],
        damage_die_count=_positive_int(weapon, "damage_die_count", f"{where} weapon"),
        damage_die_size=_positive_int(weapon, "damage_die_size", f"{where} weapon"),
    )


def _enemy_command(entry: dict[str, Any], index: int) -> AddCharacterCommand:
    where = f"enemies[{index}]"
    if not isinstance(entry, dict):
        raise EncounterError(f"{where} must be a table")
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        raise EncounterError(f"{where} name must be a non-empty string")
    return AddCharacterCommand(
        name=name,
        character_type="enemy",
        level=_positive_int(entry, "level", where),
        strength=_positive_int(entry, "strength", where),
        dexterity=_positive_int(entry, "dexterity", where),
        constitution=_positive_int(entry, "constitution", where),
        intelligence=_positive_int(entry, "intelligence", where),
        wisdom=_positive_int(entry, "wisdom", where),
        charisma=_positive_int(entry, "charisma", where),
        armor_class=_positive_int(entry, "armor_class", where),
        speed_ft=_positive_int(entry, "speed_ft", where),
        max_hp=_positive_int(entry, "max_hp", where),
        weapon=_weapon(entry, where),
    )


def load_encounter(path: str | Path) -> tuple[AddCharacterCommand, ...]:
    """Load [[enemies]] entries as enemy commands; distinct names required (CLI targets by name)."""
    with Path(path).open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)

    entries = data.get("enemies")
    if not isinstance(entries, list) or not entries:
        raise EncounterError("[[enemies]] must define at least one enemy")

    commands: list[AddCharacterCommand] = []
    names: set[str] = set()
    for index, entry in enumerate(entries):
        command = _enemy_command(entry, index)
        if command.name.lower() in names:
            raise EncounterError(f"enemies[{index}] duplicate enemy name: {command.name}")
        names.add(command.name.lower())
        commands.append(command)
    return tuple(commands)
