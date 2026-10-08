"""Encounter configuration (spec §3.3): the fight is data, in every CLI mode."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from application.commands import AddCharacterCommand, WeaponSpec
from domain.rules.ruleset import Ruleset


class EncounterError(ValueError):
    """Raised when config/encounter.toml has a structurally invalid shape."""


def _statblock_command(entry: dict[str, Any], index: int, ruleset: Ruleset) -> AddCharacterCommand:
    """Resolve one [[enemies]] entry against the active ruleset (R2)."""
    where = f"enemies[{index}]"
    if not isinstance(entry, dict):
        raise EncounterError(f"{where} must be a table")
    statblock_id = entry.get("statblock")
    if not isinstance(statblock_id, str) or not statblock_id.strip():
        raise EncounterError(f"{where} statblock must be a non-empty string")
    statblock = ruleset.statblock(statblock_id)
    weapon = ruleset.weapon(statblock.weapon_id)
    return AddCharacterCommand(
        name=statblock.name,
        character_type="enemy",
        level=statblock.level,
        strength=statblock.strength,
        dexterity=statblock.dexterity,
        constitution=statblock.constitution,
        intelligence=statblock.intelligence,
        wisdom=statblock.wisdom,
        charisma=statblock.charisma,
        armor_class=statblock.armor_class,
        speed_ft=statblock.speed_ft,
        max_hp=statblock.max_hp,
        weapon=WeaponSpec(
            weapon_id=weapon.weapon_id,
            name=weapon.name,
            damage_die_count=weapon.damage_die_count,
            damage_die_size=weapon.damage_die_size,
            # ability stays the WeaponSpec default (strength): the spec pins this
            # migration to "not change a single roll", and the shipped scimitar
            # is Finesse→DEX in data. Switching becomes a re-tuned-eval change.
            range_ft=weapon.range_ft,
        ),
    )


def load_encounter(path: str | Path, ruleset: Ruleset) -> tuple[AddCharacterCommand, ...]:
    """Load [[enemies]] entries as enemy commands; distinct names required (CLI targets by name)."""
    with Path(path).open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)

    entries = data.get("enemies")
    if not isinstance(entries, list) or not entries:
        raise EncounterError("[[enemies]] must define at least one enemy")

    commands: list[AddCharacterCommand] = []
    names: set[str] = set()
    for index, entry in enumerate(entries):
        command = _statblock_command(entry, index, ruleset)
        if command.name.lower() in names:
            raise EncounterError(f"enemies[{index}] duplicate enemy name: {command.name}")
        names.add(command.name.lower())
        commands.append(command)
    return tuple(commands)


def encounter_map_name(path: str | Path) -> str | None:
    """The encounter's battle-map name, or None when the encounter is ungridded."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    value = data.get("map")
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise EncounterError("encounter 'map' must be a non-empty string")
    return value
