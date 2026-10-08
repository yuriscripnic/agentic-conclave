"""Validating TOML loader for data/rules/<id>/ (R2 spec §2, §6).

Strict by design: every failure is a load-time RulesetError naming the file
and entry, so bad data can never reach a running game.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain.character.abilities import AbilityType
from domain.character.weapon import Weapon
from domain.rules.classes import ClassData
from domain.rules.dice import DIE_SIZES
from domain.rules.errors import RulesetError, UnknownRuleEntry
from domain.rules.statblock import Statblock

_DIAGONAL_RULES = frozenset({"5_10_5", "5_5_5"})


@dataclass(frozen=True)
class TomlRuleset:
    """Immutable in-memory view of one ruleset directory."""

    _id: str
    _diagonal_rule: str
    _weapons: dict[str, Weapon]
    _statblocks: dict[str, Statblock]
    _classes: dict[str, ClassData]

    @property
    def ruleset_id(self) -> str:
        return self._id

    @property
    def diagonal_rule(self) -> str:
        return self._diagonal_rule

    def weapon(self, weapon_id: str) -> Weapon:
        try:
            return self._weapons[weapon_id]
        except KeyError:
            raise UnknownRuleEntry("weapon", weapon_id) from None

    def statblock(self, statblock_id: str) -> Statblock:
        try:
            return self._statblocks[statblock_id]
        except KeyError:
            raise UnknownRuleEntry("statblock", statblock_id) from None

    def character_class(self, class_id: str) -> ClassData:
        try:
            return self._classes[class_id]
        except KeyError:
            raise UnknownRuleEntry("class", class_id) from None


def _read_table(directory: Path, name: str) -> Any:
    path = directory / name
    if not path.is_file():
        raise RulesetError(f"{directory} is missing {name}")
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise RulesetError(f"{name} is not valid TOML: {error}") from None


def _rows(document: Any, name: str) -> list[dict[str, Any]]:
    rows = next(iter(document.values()), None) if document else None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise RulesetError(f"{name} must be an array of tables")
    return rows


def _string(row: dict[str, Any], key: str, where: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RulesetError(f"{where} {key} must be a non-empty string")
    return value


def _positive(row: dict[str, Any], key: str, where: str) -> int:
    value = row.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RulesetError(f"{where} {key} must be an int")
    if value < 1:
        raise RulesetError(f"{where} {key} must be >= 1, got {value}")
    return value


def _weapons(directory: Path) -> dict[str, Weapon]:
    weapons: dict[str, Weapon] = {}
    for row in _rows(_read_table(directory, "weapons.toml"), "weapons.toml"):
        where = f"weapons.toml weapon {row.get('weapon_id')!r}"
        weapon_id = _string(row, "weapon_id", where)
        if weapon_id in weapons:
            raise RulesetError(f"duplicate weapon id {weapon_id!r} in weapons.toml")
        die_size = _positive(row, "damage_die_size", where)
        if die_size not in DIE_SIZES:
            raise RulesetError(
                f"{where} die size must be one of {DIE_SIZES}, got d{die_size}"
            )
        ability = _string(row, "ability", where)
        _string(row, "damage_type", where)  # recorded now; R3/R9 consume it
        try:
            ability_type = AbilityType(ability)
        except ValueError:
            raise RulesetError(
                f"{where} ability {ability!r} is not an AbilityType value"
            ) from None
        weapons[weapon_id] = Weapon(
            weapon_id=weapon_id,
            name=_string(row, "name", where),
            damage_die_count=_positive(row, "damage_die_count", where),
            damage_die_size=die_size,
            ability=ability_type,
            range_ft=_positive(row, "range_ft", where),
        )
    return weapons


def _statblocks(directory: Path, weapons: dict[str, Weapon]) -> dict[str, Statblock]:
    statblocks: dict[str, Statblock] = {}
    for row in _rows(_read_table(directory, "statblocks.toml"), "statblocks.toml"):
        where = f"statblocks.toml statblock {row.get('statblock_id')!r}"
        statblock_id = _string(row, "statblock_id", where)
        if statblock_id in statblocks:
            raise RulesetError(f"duplicate statblock id {statblock_id!r}")
        weapon_id = _string(row, "weapon_id", where)
        if weapon_id not in weapons:
            raise RulesetError(
                f"{where} names weapon {weapon_id!r}, which weapons.toml does not define"
            )
        statblocks[statblock_id] = Statblock(
            statblock_id=statblock_id,
            name=_string(row, "name", where),
            level=_positive(row, "level", where),
            strength=_positive(row, "strength", where),
            dexterity=_positive(row, "dexterity", where),
            constitution=_positive(row, "constitution", where),
            intelligence=_positive(row, "intelligence", where),
            wisdom=_positive(row, "wisdom", where),
            charisma=_positive(row, "charisma", where),
            armor_class=_positive(row, "armor_class", where),
            speed_ft=_positive(row, "speed_ft", where),
            max_hp=_positive(row, "max_hp", where),
            weapon_id=weapon_id,
        )
    return statblocks


def _classes(directory: Path) -> dict[str, ClassData]:
    classes: dict[str, ClassData] = {}
    for row in _rows(_read_table(directory, "classes.toml"), "classes.toml"):
        where = f"classes.toml class {row.get('class_id')!r}"
        class_id = _string(row, "class_id", where)
        if class_id in classes:
            raise RulesetError(f"duplicate class id {class_id!r}")
        classes[class_id] = ClassData(
            class_id=class_id,
            name=_string(row, "name", where),
            hit_die_size=_positive(row, "hit_die_size", where),
        )
    return classes


def load_ruleset(directory: Path) -> TomlRuleset:
    """Load and cross-validate one ruleset directory (R2 spec §2)."""
    if not directory.is_dir():
        raise RulesetError(f"no ruleset directory at {directory}")
    ruleset_document = _read_table(directory, "ruleset.toml")
    ruleset_id = _string(ruleset_document, "id", "ruleset.toml")
    grid = ruleset_document.get("grid")
    if not isinstance(grid, dict):
        raise RulesetError("ruleset.toml must carry a [grid] table")
    diagonal_rule = _string(grid, "diagonal_rule", "ruleset.toml [grid]")
    if diagonal_rule not in _DIAGONAL_RULES:
        raise RulesetError(
            f"ruleset.toml [grid] diagonal_rule must be one of "
            f"{sorted(_DIAGONAL_RULES)}, got {diagonal_rule!r}"
        )
    weapons = _weapons(directory)
    statblocks = _statblocks(directory, weapons)
    classes = _classes(directory)
    return TomlRuleset(
        _id=ruleset_id,
        _diagonal_rule=diagonal_rule,
        _weapons=weapons,
        _statblocks=statblocks,
        _classes=classes,
    )
