# R2 — Ruleset & Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the rules data — weapons, classes, monster statblocks and the grid's diagonal rule — out of Python constants and inline config tables into `data/rules/*.toml` behind a `Ruleset` port, so `dnd5e-srd-5.2` is data and swapping the ruleset id is config-only.

**Architecture:** A `Ruleset` Protocol lives in `src/domain/rules/`; a validating TOML loader in `src/infrastructure/rules/` implements it. The session factory selects the ruleset directory from `config/game.toml` and injects it; the encounter loader and agent profiles resolve weapon and statblock ids through it. `WeaponSpec` and `AddCharacterCommand` keep their contracts; only the sources of the numbers change.

**Tech Stack:** Python 3.12 stdlib only (`tomllib`, dataclasses, enum, Protocol). No new dependencies. pytest, ruff, mypy --strict as today.

**Spec:** `docs/superpowers/specs/2026-10-07-rules-core-r2-ruleset-design.md`

## Global Constraints

- The domain package `src/domain/rules/` imports nothing from application, ai, infrastructure or interfaces (CLAUDE.md §4); the loader lives in `src/infrastructure/rules/`.
- `WeaponSpec` and `AddCharacterCommand` keep their current fields and defaults; no call-site contract changes (spec §2).
- The migration must not change a single roll: same weapons, same statblocks, same seeded results byte-for-byte.
- Without a ruleset injected (all pre-existing tests, no-board combat), behaviour is byte-for-byte today's.
- Error types, exact names: `RulesetError` (load-time, message names file and entry), `UnknownRuleEntry` (resolve-time, carries `kind` and `entry_id`).
- Supported `diagonal_rule` values: `5_10_5` (default, R1 behaviour) and `5_5_5`; anything else is a load error.
- FROZEN ADAPTER LICENCE: no new agent capability; `ai/` is touched only if a test forces it.
- No new dependencies; `ruff` clean; `mypy --strict` clean; full suite green at every task's end.

## Review Focus

The spec implies these failure modes but no single task's tests exercise all of them; each line is pinned by the named test.

- **Dangling reference.** A statblock naming a weapon the ruleset does not define must fail at load, naming the statblock — not at first resolve mid-game. Pinned by Task 3.
- **Silent default on unknown id.** Resolving an absent id must raise `UnknownRuleEntry`, never return a look-alike. Pinned by Task 1's resolve tests.
- **Migration drift.** The statblock migration must keep every number identical to today's encounter — a changed HP or die size silently re-balances the shipped fight. Pinned by Task 5's byte-equivalence test.
- **Config-only swap actually swaps.** Editing `config/game.toml`'s ruleset id must change what the factory loads — a second ruleset directory proves the path moves. Pinned by Task 4.
- **Optional-ruleset rot.** Paths that run without a ruleset (no-board combat, existing tests) must behave exactly as before, including the 5-10-5 default. Pinned by Task 4's default test.

---

### Task 1: Domain value objects and the Ruleset port

**Files:**
- Create: `src/domain/rules/errors.py`
- Create: `src/domain/rules/statblock.py`
- Create: `src/domain/rules/classes.py`
- Create: `src/domain/rules/ruleset.py`
- Test: `tests/domain/test_ruleset_port.py`

**Interfaces:**
- Consumes: `domain.common.errors.ValidationError`; `domain.character.weapon.Weapon`; `domain.rules.dice.DIE_SIZES`; `domain.rules.progression.MIN_LEVEL/MAX_LEVEL`; `domain.character.character.CharacterClass`.
- Produces, for every later task: `RulesetError(ValueError)`, `UnknownRuleEntry(RulesetError)` with attributes `kind: str`, `entry_id: str`; `Statblock(statblock_id, name, level, strength, dexterity, constitution, intelligence, wisdom, charisma, armor_class, speed_ft, max_hp, weapon_id)` frozen; `ClassData(class_id, name, hit_die_size)` frozen; `Ruleset` Protocol with `ruleset_id: str`, `diagonal_rule: str`, `weapon(weapon_id: str) -> Weapon`, `statblock(statblock_id: str) -> Statblock`, `character_class(class_id: str) -> ClassData`.

- [ ] **Step 1: Write the failing tests**

`tests/domain/test_ruleset_port.py`:

```python
"""The Ruleset port: data queries the engine makes, errors when data is absent."""

import pytest

from domain.character.abilities import AbilityType
from domain.character.character import CharacterClass
from domain.character.weapon import Weapon
from domain.rules.classes import ClassData
from domain.rules.errors import RulesetError, UnknownRuleEntry
from domain.rules.ruleset import Ruleset
from domain.rules.statblock import Statblock


class _EmptyRuleset:
    """Minimal port stand-in: no data at all."""

    ruleset_id = "test-empty"
    diagonal_rule = "5_10_5"

    def weapon(self, weapon_id: str) -> Weapon:
        raise UnknownRuleEntry("weapon", weapon_id)

    def statblock(self, statblock_id: str) -> Statblock:
        raise UnknownRuleEntry("statblock", statblock_id)

    def character_class(self, class_id: str) -> ClassData:
        raise UnknownRuleEntry("class", class_id)


def test_ruleset_protocol_is_satisfied_by_a_plain_class() -> None:
    ruleset: Ruleset = _EmptyRuleset()
    assert ruleset.ruleset_id == "test-empty"
    assert ruleset.diagonal_rule == "5_10_5"


@pytest.mark.parametrize(
    "kind, attr, entry_id",
    [
        ("weapon", "weapon", "mace2"),
        ("statblock", "statblock", "goblin-9"),
        ("class", "character_class", "bard"),
    ],
)
def test_unknown_entry_raises_with_kind_and_id(
    kind: str, attr: str, entry_id: str
) -> None:
    ruleset: Ruleset = _EmptyRuleset()
    with pytest.raises(UnknownRuleEntry) as exc:
        getattr(ruleset, attr)(entry_id)
    assert exc.value.kind == kind
    assert exc.value.entry_id == entry_id
    assert isinstance(exc.value, RulesetError)


def _statblock(**overrides: object) -> Statblock:
    kwargs: dict[str, object] = {
        "statblock_id": "goblin_scout",
        "name": "Goblin Scout",
        "level": 1,
        "strength": 8,
        "dexterity": 14,
        "constitution": 10,
        "intelligence": 10,
        "wisdom": 8,
        "charisma": 8,
        "armor_class": 13,
        "speed_ft": 30,
        "max_hp": 7,
        "weapon_id": "scimitar",
    }
    kwargs.update(overrides)
    return Statblock(**kwargs)  # type: ignore[arg-type]


def test_statblock_holds_the_enemy_shape() -> None:
    statblock = _statblock()
    assert statblock.weapon_id == "scimitar"
    assert statblock.level == 1


@pytest.mark.parametrize(
    "field, value",
    [("max_hp", 0), ("armor_class", -1), ("speed_ft", 0), ("level", 0), ("level", 21)],
)
def test_statblock_rejects_out_of_range_numbers(field: str, value: int) -> None:
    with pytest.raises(Exception):
        _statblock(**{field: value})


@pytest.mark.parametrize("field", ["statblock_id", "name", "weapon_id"])
def test_statblock_rejects_blank_strings(field: str) -> None:
    with pytest.raises(Exception):
        _statblock(**{field: "  "})


def test_class_data_carries_hit_die() -> None:
    data = ClassData(class_id="fighter", name="Fighter", hit_die_size=10)
    assert data.hit_die_size == 10
    assert data.class_id in {member.value for member in CharacterClass}


def test_class_data_rejects_unknown_class_id() -> None:
    with pytest.raises(Exception):
        ClassData(class_id="bard", name="Bard", hit_die_size=8)


def test_class_data_rejects_non_die_hit_die() -> None:
    with pytest.raises(Exception):
        ClassData(class_id="fighter", name="Fighter", hit_die_size=7)


def test_weapon_ability_is_a_str_enum_value() -> None:
    weapon = Weapon(
        weapon_id="longsword",
        name="Longsword",
        damage_die_count=1,
        damage_die_size=8,
        ability=AbilityType.STRENGTH,
    )
    assert weapon.ability.value == "strength"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_ruleset_port.py -v`
Expected: FAIL — `domain.rules.classes`, `domain.rules.errors`, `domain.rules.ruleset`, `domain.rules.statblock` do not exist (collection/import errors).

- [ ] **Step 3: Write the domain modules**

`src/domain/rules/errors.py`:

```python
"""Ruleset data errors (R2 spec §3): load-time and resolve-time."""

from __future__ import annotations


class RulesetError(ValueError):
    """Rules data is malformed or missing; the message names file and entry."""


class UnknownRuleEntry(RulesetError):
    """A ruleset was asked for an id it does not define."""

    def __init__(self, kind: str, entry_id: str) -> None:
        self.kind = kind
        self.entry_id = entry_id
        super().__init__(f"unknown {kind} id {entry_id!r} in the active ruleset")
```

`src/domain/rules/statblock.py`:

```python
"""Monster statblock value object: the enemy shape the encounter loader maps."""

from __future__ import annotations

from dataclasses import dataclass

from domain.common.errors import ValidationError
from domain.rules.progression import MAX_LEVEL, MIN_LEVEL


@dataclass(frozen=True)
class Statblock:
    statblock_id: str
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
    weapon_id: str

    def __post_init__(self) -> None:
        if not self.statblock_id.strip():
            raise ValidationError("statblock_id must be a non-empty string")
        if not self.name.strip():
            raise ValidationError("statblock name must be a non-empty string")
        if not self.weapon_id.strip():
            raise ValidationError("statblock weapon_id must be a non-empty string")
        if not MIN_LEVEL <= self.level <= MAX_LEVEL:
            raise ValidationError(
                f"statblock level must be between {MIN_LEVEL} and {MAX_LEVEL}, "
                f"got {self.level}"
            )
        for field in (
            "strength",
            "dexterity",
            "constitution",
            "intelligence",
            "wisdom",
            "charisma",
            "armor_class",
            "speed_ft",
            "max_hp",
        ):
            value = getattr(self, field)
            if value < 1:
                raise ValidationError(
                    f"statblock {field} must be at least 1, got {value}"
                )
```

`src/domain/rules/classes.py`:

```python
"""Class data row: identity and hit die; features arrive at R8."""

from __future__ import annotations

from dataclasses import dataclass

from domain.character.character import CharacterClass
from domain.common.errors import ValidationError
from domain.rules.dice import DIE_SIZES


@dataclass(frozen=True)
class ClassData:
    class_id: str
    name: str
    hit_die_size: int

    def __post_init__(self) -> None:
        if self.class_id not in {member.value for member in CharacterClass}:
            raise ValidationError(
                f"class_id {self.class_id!r} is not a CharacterClass value"
            )
        if not self.name.strip():
            raise ValidationError("class name must be a non-empty string")
        if self.hit_die_size not in DIE_SIZES:
            raise ValidationError(
                f"hit die size must be one of {DIE_SIZES}, got d{self.hit_die_size}"
            )
```

`src/domain/rules/ruleset.py`:

```python
"""The Ruleset port (CLAUDE.md §13): rules data behind an interface."""

from __future__ import annotations

from typing import Protocol

from domain.character.weapon import Weapon
from domain.rules.classes import ClassData
from domain.rules.statblock import Statblock


class Ruleset(Protocol):
    """Queries the rules engine makes against the active ruleset's data."""

    @property
    def ruleset_id(self) -> str: ...

    @property
    def diagonal_rule(self) -> str: ...

    def weapon(self, weapon_id: str) -> Weapon: ...

    def statblock(self, statblock_id: str) -> Statblock: ...

    def character_class(self, class_id: str) -> ClassData: ...
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_ruleset_port.py -v`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add src/domain/rules/errors.py src/domain/rules/statblock.py src/domain/rules/classes.py src/domain/rules/ruleset.py tests/domain/test_ruleset_port.py
git commit -m "feat(domain): add the Ruleset port with statblock and class data"
```

---

### Task 2: The `dnd5e-srd-5.2` data files and NOTICE

**Files:**
- Create: `data/rules/dnd5e-srd-5.2/ruleset.toml`
- Create: `data/rules/dnd5e-srd-5.2/weapons.toml`
- Create: `data/rules/dnd5e-srd-5.2/classes.toml`
- Create: `data/rules/dnd5e-srd-5.2/statblocks.toml`
- Create: `data/rules/NOTICE`
- Test: `tests/domain/test_ruleset_data_files.py`

**Interfaces:**
- Consumes: nothing (tests read the TOML directly with `tomllib`).
- Produces: the shipped data files every later task loads; the ids pinned here are the migration's contract — weapons `longsword`, `shortsword`, `mace`, `scimitar`, `greataxe`; classes `fighter`, `rogue`, `wizard`, `cleric`; statblocks `goblin_scout`, `goblin_skulker`, `orc_brute`.

- [ ] **Step 1: Write the failing test**

`tests/domain/test_ruleset_data_files.py`:

```python
"""The shipped SRD 5.2 data files parse and carry the ids the configs reference."""

import tomllib
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data/rules/dnd5e-srd-5.2"


def _rows(name: str) -> list[dict[str, object]]:
    with (DATA / name).open("rb") as handle:
        document = tomllib.load(handle)
    return next(iter(document.values()))  # single array-of-tables per file


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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/domain/test_ruleset_data_files.py -v`
Expected: FAIL — the data files do not exist.

- [ ] **Step 3: Write the data files**

`data/rules/dnd5e-srd-5.2/ruleset.toml`:

```toml
# The active ruleset's identity and engine parameters (R2 spec §4).
id = "dnd5e-srd-5.2"
name = "Dungeons & Dragons 5e, System Reference Document 5.2"

[grid]
# 5-10-5: the first diagonal step costs 5 ft, the second 10, alternating.
# The alternative SRD variant ("5_5_5") costs 5 ft per diagonal step.
diagonal_rule = "5_10_5"
```

`data/rules/dnd5e-srd-5.2/weapons.toml`:

```toml
# Weapons in play, SRD 5.2 (CC-BY-4.0; see data/rules/NOTICE).
# damage_type is recorded for R3/R9; the loader validates presence only.

[[weapon]]
weapon_id = "longsword"
name = "Longsword"
damage_die_count = 1
damage_die_size = 8
ability = "strength"
damage_type = "slashing"
range_ft = 5

[[weapon]]
weapon_id = "shortsword"
name = "Shortsword"
damage_die_count = 1
damage_die_size = 6
ability = "dexterity"
damage_type = "piercing"
range_ft = 5

[[weapon]]
weapon_id = "mace"
name = "Mace"
damage_die_count = 1
damage_die_size = 6
ability = "strength"
damage_type = "bludgeoning"
range_ft = 5

[[weapon]]
weapon_id = "scimitar"
name = "Scimitar"
damage_die_count = 1
damage_die_size = 6
ability = "dexterity"
damage_type = "slashing"
range_ft = 5

[[weapon]]
weapon_id = "greataxe"
name = "Greataxe"
damage_die_count = 1
damage_die_size = 12
ability = "strength"
damage_type = "slashing"
range_ft = 5
```

`data/rules/dnd5e-srd-5.2/classes.toml`:

```toml
# The four playable classes (SRD 5.2); features arrive at R8.

[[class]]
class_id = "fighter"
name = "Fighter"
hit_die_size = 10

[[class]]
class_id = "rogue"
name = "Rogue"
hit_die_size = 8

[[class]]
class_id = "wizard"
name = "Wizard"
hit_die_size = 6

[[class]]
class_id = "cleric"
name = "Cleric"
hit_die_size = 8
```

`data/rules/dnd5e-srd-5.2/statblocks.toml`:

```toml
# The MVP-0 enemies, byte-equivalent to config/encounter.toml before migration.

[[statblock]]
statblock_id = "goblin_scout"
name = "Goblin Scout"
level = 1
strength = 8
dexterity = 14
constitution = 10
intelligence = 10
wisdom = 8
charisma = 8
armor_class = 13
speed_ft = 30
max_hp = 7
weapon_id = "scimitar"

[[statblock]]
statblock_id = "goblin_skulker"
name = "Goblin Skulker"
level = 1
strength = 8
dexterity = 14
constitution = 10
intelligence = 10
wisdom = 8
charisma = 8
armor_class = 13
speed_ft = 30
max_hp = 7
weapon_id = "scimitar"

[[statblock]]
statblock_id = "orc_brute"
name = "Orc Brute"
level = 1
strength = 16
dexterity = 12
constitution = 14
intelligence = 7
wisdom = 10
charisma = 8
armor_class = 15
speed_ft = 30
max_hp = 15
weapon_id = "greataxe"
```

`data/rules/NOTICE`:

```text
Rules data in this directory tree is derived from the System Reference
Document 5.2 ("SRD 5.2") for Dungeons & Dragons, published by Wizards of
the Coast under the Creative Commons Attribution 4.0 International
licence (CC-BY-4.0):
https://creativecommons.org/licenses/by/4.0/

This project is not affiliated with or endorsed by Wizards of the Coast.
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/domain/test_ruleset_data_files.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add data/rules tests/domain/test_ruleset_data_files.py
git commit -m "feat(rules): ship the dnd5e-srd-5.2 data files with CC-BY-4.0 NOTICE"
```

---

### Task 3: The validating TOML loader

**Files:**
- Create: `src/infrastructure/rules/__init__.py` (empty)
- Create: `src/infrastructure/rules/loader.py`
- Test: `tests/infrastructure/rules/test_ruleset_loader.py`

**Interfaces:**
- Consumes: the Task 1 domain objects (`Ruleset`, `Statblock`, `ClassData`, `RulesetError`, `UnknownRuleEntry`); `domain.character.weapon.Weapon`; `domain.character.abilities.AbilityType`; `domain.rules.dice.DIE_SIZES`.
- Produces, for Tasks 4-6: `TomlRuleset` (implements `Ruleset`; frozen) and `load_ruleset(directory: Path) -> TomlRuleset`. Load-time failures raise `RulesetError` naming the file and entry; resolve-time misses raise `UnknownRuleEntry`.

- [ ] **Step 1: Write the failing tests**

`tests/infrastructure/rules/test_ruleset_loader.py`:

```python
"""The loader validates strictly: malformed data fails at load, not mid-game."""

from pathlib import Path

import pytest

from domain.character.abilities import AbilityType
from domain.rules.errors import RulesetError, UnknownRuleEntry
from infrastructure.rules.loader import load_ruleset

SHIPPED = Path(__file__).resolve().parents[3] / "data/rules/dnd5e-srd-5.2"


def test_loads_the_shipped_ruleset() -> None:
    ruleset = load_ruleset(SHIPPED)
    assert ruleset.ruleset_id == "dnd5e-srd-5.2"
    assert ruleset.diagonal_rule == "5_10_5"


def test_shipped_weapons_resolve_to_domain_objects() -> None:
    ruleset = load_ruleset(SHIPPED)
    longsword = ruleset.weapon("longsword")
    assert longsword.damage_die_size == 8
    assert longsword.ability is AbilityType.STRENGTH
    scimitar = ruleset.weapon("scimitar")
    assert scimitar.ability is AbilityType.DEXTERITY


def test_shipped_statblocks_and_classes_resolve() -> None:
    ruleset = load_ruleset(SHIPPED)
    orc = ruleset.statblock("orc_brute")
    assert orc.max_hp == 15
    assert orc.weapon_id == "greataxe"
    fighter = ruleset.character_class("fighter")
    assert fighter.hit_die_size == 10


def test_unknown_ids_raise_unknown_rule_entry() -> None:
    ruleset = load_ruleset(SHIPPED)
    with pytest.raises(UnknownRuleEntry):
        ruleset.weapon("mace2")
    with pytest.raises(UnknownRuleEntry):
        ruleset.statblock("goblin-9")


def test_missing_directory_names_the_path() -> None:
    with pytest.raises(RulesetError, match="no-such-ruleset"):
        load_ruleset(Path("/tmp/rules-data/no-such-ruleset"))


def _write(tmp_path: Path, name: str, text: str) -> None:
    directory = tmp_path / "test-ruleset"
    directory.mkdir(exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


def _minimal_ruleset(tmp_path: Path, overrides: dict[str, str] | None = None) -> Path:
    """A tiny valid ruleset; entries in `overrides` replace whole files."""
    files = {
        "ruleset.toml": 'id = "test"\nname = "Test"\n[grid]\ndiagonal_rule = "5_10_5"\n',
        "weapons.toml": (
            '[[weapon]]\nweapon_id = "club"\nname = "Club"\n'
            "damage_die_count = 1\ndamage_die_size = 4\nability = \"strength\"\n"
            'damage_type = "bludgeoning"\nrange_ft = 5\n'
        ),
        "classes.toml": (
            '[[class]]\nclass_id = "fighter"\nname = "Fighter"\nhit_die_size = 10\n'
        ),
        "statblocks.toml": (
            '[[statblock]]\nstatblock_id = "dummy"\nname = "Dummy"\nlevel = 1\n'
            "strength = 10\ndexterity = 10\nconstitution = 10\nintelligence = 10\n"
            "wisdom = 10\ncharisma = 10\narmor_class = 10\nspeed_ft = 30\n"
            'max_hp = 4\nweapon_id = "club"\n'
        ),
    }
    files.update(overrides or {})
    for name, text in files.items():
        _write(tmp_path, name, text)
    return tmp_path / "test-ruleset"


def test_missing_required_file_is_a_load_error(tmp_path: Path) -> None:
    (tmp_path / "test-ruleset").mkdir()
    with pytest.raises(RulesetError, match="weapons.toml"):
        load_ruleset(tmp_path / "test-ruleset")


def test_unknown_die_size_is_a_load_error(tmp_path: Path) -> None:
    directory = _minimal_ruleset(
        tmp_path,
        {"weapons.toml": '[[weapon]]\nweapon_id = "club"\nname = "Club"\n'
                         "damage_die_count = 1\ndamage_die_size = 7\n"
                         'ability = "strength"\ndamage_type = "bludgeoning"\n'
                         "range_ft = 5\n"},
    )
    with pytest.raises(RulesetError, match="die size"):
        load_ruleset(directory)


def test_unknown_ability_is_a_load_error(tmp_path: Path) -> None:
    directory = _minimal_ruleset(
        tmp_path,
        {"weapons.toml": '[[weapon]]\nweapon_id = "club"\nname = "Club"\n'
                         "damage_die_count = 1\ndamage_die_size = 4\n"
                         'ability = "charisma"\ndamage_type = "bludgeoning"\n'
                         "range_ft = 5\n"},
    )
    with pytest.raises(RulesetError, match="ability"):
        load_ruleset(directory)


def test_dangling_statblock_weapon_fails_at_load(tmp_path: Path) -> None:
    directory = _minimal_ruleset(
        tmp_path,
        {"statblocks.toml": '[[statblock]]\nstatblock_id = "dummy"\nname = "Dummy"\n'
                            "level = 1\nstrength = 10\ndexterity = 10\n"
                            "constitution = 10\nintelligence = 10\nwisdom = 10\n"
                            "charisma = 10\narmor_class = 10\nspeed_ft = 30\n"
                            'max_hp = 4\nweapon_id = "greatclub"\n'},
    )
    with pytest.raises(RulesetError, match="dummy"):
        load_ruleset(directory)


def test_duplicate_weapon_id_is_a_load_error(tmp_path: Path) -> None:
    directory = _minimal_ruleset(
        tmp_path,
        {"weapons.toml": (
            '[[weapon]]\nweapon_id = "club"\nname = "Club"\n'
            "damage_die_count = 1\ndamage_die_size = 4\nability = \"strength\"\n"
            'damage_type = "bludgeoning"\nrange_ft = 5\n'
            '[[weapon]]\nweapon_id = "club"\nname = "Club II"\n'
            "damage_die_count = 1\ndamage_die_size = 6\nability = \"strength\"\n"
            'damage_type = "bludgeoning"\nrange_ft = 5\n'
        )},
    )
    with pytest.raises(RulesetError, match="duplicate"):
        load_ruleset(directory)


def test_unknown_diagonal_rule_is_a_load_error(tmp_path: Path) -> None:
    directory = _minimal_ruleset(
        tmp_path, {"ruleset.toml": 'id = "test"\n[grid]\ndiagonal_rule = "3_3_3"\n'}
    )
    with pytest.raises(RulesetError, match="diagonal_rule"):
        load_ruleset(directory)


def test_wrong_value_type_is_a_load_error(tmp_path: Path) -> None:
    directory = _minimal_ruleset(
        tmp_path,
        {"classes.toml": '[[class]]\nclass_id = "fighter"\nname = "Fighter"\n'
                         'hit_die_size = "ten"\n'},
    )
    with pytest.raises(RulesetError):
        load_ruleset(directory)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/rules/test_ruleset_loader.py -v`
Expected: FAIL — `infrastructure.rules.loader` does not exist.

- [ ] **Step 3: Write the loader**

`src/infrastructure/rules/loader.py`:

```python
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
    return rows  # type: ignore[return-value]


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/infrastructure/rules/test_ruleset_loader.py -v`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add src/infrastructure/rules tests/infrastructure/rules
git commit -m "feat(infrastructure): add the validating ruleset TOML loader"
```

---

### Task 4: The diagonal rule becomes data, wired end-to-end

**Files:**
- Modify: `src/domain/space/geometry.py` (`distance_ft`)
- Modify: `src/domain/combat/engine.py` (`CombatEngine.__init__`, the range check at `engine.py:159`)
- Modify: `src/application/game_service.py` (`GameService.__init__`, `_engine`)
- Modify: `src/application/commands.py` (`WeaponSpec` gains `range_ft: int = 5`)
- Modify: `src/application/game_service.py` (build the domain `Weapon` with the spec's range)
- Modify: `src/session/factory.py` (ruleset selection helpers + wiring)
- Test: `tests/domain/test_geometry.py` (create; R1's geometry tests may already live here — append), `tests/domain/test_combat.py` (append), `tests/application/test_game_service.py` (append), `tests/session/test_ruleset_selection.py` (create)

**Interfaces:**
- Consumes: Task 1's `Ruleset` protocol; Task 3's `load_ruleset`.
- Produces: `distance_ft(a, b, *, diagonal_rule: str = "5_10_5") -> int`; `CombatEngine(dice, diagonal_rule: str = "5_10_5")`; `GameService(..., ruleset: Ruleset | None = None)`; `WeaponSpec(..., range_ft: int = 5)`; `ruleset_id_from_config(config_dir: Path) -> str` and `load_session_ruleset(config_dir: Path, data_root: Path) -> TomlRuleset` in `session.factory`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/test_geometry.py` (create the file if R1 did not):

```python
import pytest

from domain.common.errors import ValidationError
from domain.space.geometry import distance_ft
from domain.space.square import Square


def test_two_diagonal_steps_cost_fifteen_by_default() -> None:
    assert distance_ft(Square(0, 0), Square(2, 2)) == 15


def test_the_5_5_5_variant_costs_five_per_diagonal() -> None:
    assert distance_ft(Square(0, 0), Square(2, 2), diagonal_rule="5_5_5") == 10


def test_unknown_diagonal_rule_is_rejected() -> None:
    with pytest.raises(ValidationError):
        distance_ft(Square(0, 0), Square(2, 2), diagonal_rule="3_3_3")
```

Append to `tests/domain/test_combat.py` (reuses that file's `_fighter`, `_goblin`, `_board`, `_spawns`, `_start` helpers; the target must sit two diagonal squares from the attacker):

```python
def test_engine_honours_a_non_default_diagonal_rule() -> None:
    """Two diagonal steps: 15 ft under 5-10-5, 10 ft under 5-5-5."""
    from domain.character.weapon import Weapon as W
    from domain.rules.actions import AttackProposal

    engine_10 = CombatEngine(DiceRoller(seed=1))  # default 5_10_5
    engine_5 = CombatEngine(DiceRoller(seed=1), diagonal_rule="5_5_5")

    attacker = _fighter()
    attacker.equipped_weapon = W(
        weapon_id="pike", name="Pike", damage_die_count=1,
        damage_die_size=10, range_ft=10,
    )
    game = _game_with(attacker, _goblin())
    board = _board()
    spawns = _spawns(party=(Square(0, 0),), enemies=(Square(2, 2),))

    _, combat_10, collector_10 = _start(
        engine_10, DiceRoller(seed=1), game, board=board, spawns=spawns
    )
    proposal = AttackProposal(
        actor_id=game.party_ids[0], target_id=game.enemy_ids[0], weapon_id="pike"
    )
    assert engine_10.validate(game, combat_10, proposal).code == "out_of_range"

    _, combat_5, _ = _start(
        engine_5, DiceRoller(seed=1), game, board=board, spawns=spawns
    )
    assert engine_5.validate(game, combat_5, proposal).valid
```

If `_start`, `_game_with`, `_spawns` helpers differ in signature or name from this
call shape, adapt the call sites to the file's actual helpers — the assertion
pair (out_of_range under the default, valid under `5_5_5`) is the contract.

Append to `tests/application/test_game_service.py`:

```python
class _FiveFiveRuleset:
    """A Ruleset stub carrying only the diagonal rule the engine reads."""

    ruleset_id = "test-5_5_5"
    diagonal_rule = "5_5_5"

    def weapon(self, weapon_id: str) -> object:
        raise AssertionError("not used in this test")

    def statblock(self, statblock_id: str) -> object:
        raise AssertionError("not used in this test")

    def character_class(self, class_id: str) -> object:
        raise AssertionError("not used in this test")


def test_the_rulesets_diagonal_rule_reaches_grid_combat() -> None:
    event_store = InMemoryEventRepository()
    battle_map = BattleMap(
        board=Board(width=10, height=10),
        spawns=Spawns(party=(Square(0, 0),), enemies=(Square(2, 2),)),
    )
    service = GameService(
        InMemoryGameRepository(event_store),
        event_store,
        battle_map=battle_map,
        ruleset=_FiveFiveRuleset(),  # type: ignore[arg-type]
    )
    game_id = service.create_game(CreateGameCommand(seed=1))
    service.add_character(game_id, _fighter_command(range_ft=10))
    service.add_character(game_id, _goblin_command())

    view = service.start_combat(game_id)

    assert view.combat is not None
    # Under the default 5-10-5 rule this attack is out of range (15 ft);
    # under the ruleset's 5-5-5 it is legal (10 ft).
    assert view.combat.map is not None
```

plus a companion assertion (same fixture, no ruleset) that the default rule
still rejects the attack — extend `_fighter_command`/`_goblin_command` in that
file with an optional `range_ft` parameter defaulting to today's value.

`tests/session/test_ruleset_selection.py`:

```python
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
    root = tmp_path / "data" / "rules"
    shipped = root / "dnd5e-srd-5.2"
    shipped.mkdir(parents=True)
    (shipped / "ruleset.toml").write_text(
        'id = "dnd5e-srd-5.2"\nname = "SRD"\n[grid]\ndiagonal_rule = "5_10_5"\n',
        encoding="utf-8",
    )
    (shipped / "weapons.toml").write_text("", encoding="utf-8")
    (shipped / "classes.toml").write_text("", encoding="utf-8")
    (shipped / "statblocks.toml").write_text("", encoding="utf-8")
    return root.parent.parent


def test_config_without_a_ruleset_defaults_to_srd_5_2(tmp_path: Path) -> None:
    assert ruleset_id_from_config(_config(tmp_path, None)) == "dnd5e-srd-5.2"


def test_config_names_the_ruleset_id(tmp_path: Path) -> None:
    assert ruleset_id_from_config(_config(tmp_path, "alt")) == "alt"


def test_selection_loads_the_named_directory(tmp_path: Path) -> None:
    data_root = _data_root(tmp_path)
    ruleset = load_session_ruleset(_config(tmp_path, "dnd5e-srd-5.2"), data_root)
    assert ruleset.ruleset_id == "dnd5e-srd-5.2"


def test_swapping_the_id_is_config_only(tmp_path: Path) -> None:
    data_root = _data_root(tmp_path)
    with pytest.raises(RulesetError, match="alt"):
        load_session_ruleset(_config(tmp_path, "alt"), data_root)
```

Note: the last two tests need `weapons.toml`/`classes.toml`/`statblocks.toml`
content the loader accepts (empty arrays are fine — `_rows` accepts an empty
array); if the loader rejects an empty file, give each file one minimal row as
in Task 3's `_minimal_ruleset`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_geometry.py tests/domain/test_combat.py tests/application/test_game_service.py tests/session/test_ruleset_selection.py -v`
Expected: the new tests FAIL (`distance_ft` takes no `diagonal_rule`; `CombatEngine` and `GameService` take no ruleset; the factory helpers do not exist).

- [ ] **Step 3: Implement**

`src/domain/space/geometry.py` — replace `distance_ft` with:

```python
def distance_ft(a: Square, b: Square, *, diagonal_rule: str = "5_10_5") -> int:
    """Distance in feet; the diagonal cost model is a ruleset parameter (R2).

    "5_10_5": each diagonal step alternates 5, 10 (R1 behaviour, the default).
    "5_5_5": every diagonal step costs 5 (the SRD's simpler variant).
    """
    if diagonal_rule not in ("5_10_5", "5_5_5"):
        raise ValidationError(f"unknown diagonal rule {diagonal_rule!r}")
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    diagonals = min(dx, dy)
    straight = max(dx, dy) - diagonals
    if diagonal_rule == "5_5_5":
        return 5 * (diagonals + straight)
    total = 0
    for index in range(diagonals):
        total += 5 if index % 2 == 0 else 10
    return total + 5 * straight
```

(import `ValidationError` from `domain.common.errors`.)

`src/domain/combat/engine.py`:

```python
class CombatEngine:
    def __init__(self, dice: DiceRoller, diagonal_rule: str = "5_10_5") -> None:
        self._dice = dice
        self._diagonal_rule = diagonal_rule
```

and at the range check:

```python
        if (
            distance_ft(actor_square, target_square, diagonal_rule=self._diagonal_rule)
            > weapon.range_ft
        ):
```

`src/application/commands.py` — `WeaponSpec` gains:

```python
    range_ft: int = 5
```

`src/application/game_service.py` — `GameService.__init__` gains
`ruleset: Ruleset | None = None` (stored as `self._ruleset`; import the protocol
from `domain.rules.ruleset`); `_engine` becomes:

```python
    def _engine(self, game: Game) -> CombatEngine:
        dice = self._dice.get(game.game_id)
        if dice is None:
            dice = DiceRoller(seed=game.seed)
            self._dice[game.game_id] = dice
        diagonal = (
            self._ruleset.diagonal_rule if self._ruleset is not None else "5_10_5"
        )
        return CombatEngine(dice, diagonal_rule=diagonal)
```

and where `add_character` builds the domain `Weapon` from the command's
`WeaponSpec`, pass `range_ft=spec.range_ft` through (find the construction site
with `grep -n "Weapon(" src/application/game_service.py`).

`src/session/factory.py` — add module constants and helpers:

```python
DATA_RULES_DIR = Path(__file__).resolve().parents[2] / "data" / "rules"
DEFAULT_RULESET_ID = "dnd5e-srd-5.2"


def ruleset_id_from_config(config_dir: Path) -> str:
    """The [ruleset] id from config/game.toml; the SRD 5.2 default when absent."""
    import tomllib

    try:
        document = tomllib.loads((config_dir / "game.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return DEFAULT_RULESET_ID
    table = document.get("ruleset")
    if not isinstance(table, dict):
        return DEFAULT_RULESET_ID
    ruleset_id = table.get("id", DEFAULT_RULESET_ID)
    if not isinstance(ruleset_id, str) or not ruleset_id.strip():
        return DEFAULT_RULESET_ID
    return ruleset_id


def load_session_ruleset(config_dir: Path, data_root: Path) -> TomlRuleset:
    """Resolve the configured id against the rules-data root (R2 spec §5)."""
    return load_ruleset(data_root / "rules" / ruleset_id_from_config(config_dir))
```

(import `load_ruleset` and `TomlRuleset` from `infrastructure.rules.loader`;
`Ruleset` is already imported from `domain.rules.ruleset`.) Then in
`build_session` and `build_service`, load the ruleset once and pass it through:

```python
    ruleset = load_session_ruleset(CONFIG_DIR, DATA_RULES_DIR.parents[1])
    service = build_service(config.db, world=world, battle_map=battle_map, ruleset=ruleset)
```

`build_service` gains `ruleset: Ruleset | None = None` and forwards it to
`GameService` in both backends. `config/game.toml` gains:

```toml
[ruleset]
id = "dnd5e-srd-5.2"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_geometry.py tests/domain/test_combat.py tests/application/test_game_service.py tests/session/test_ruleset_selection.py -v`
Expected: all pass, including every pre-existing test in those files (byte-for-byte default behaviour).

- [ ] **Step 5: Commit**

```bash
git add src/domain/space/geometry.py src/domain/combat/engine.py src/application/commands.py src/application/game_service.py src/session/factory.py config/game.toml tests/domain tests/application/test_game_service.py tests/session/test_ruleset_selection.py
git commit -m "feat(rules): make the diagonal rule a ruleset parameter wired end-to-end"
```

---

### Task 5: Monsters become statblock data

**Files:**
- Modify: `config/encounter.toml`
- Modify: `src/application/encounter.py`
- Test: `tests/application/test_encounter.py` (modify/extend)

**Interfaces:**
- Consumes: Task 1's `Statblock` and `Ruleset`; Task 3's `load_ruleset`.
- Produces: `load_encounter(path: Path, ruleset: Ruleset) -> list[AddCharacterCommand]` — the signature every caller (currently `session.factory`) uses from now on.

- [ ] **Step 1: Write the failing tests**

In `tests/application/test_encounter.py`, add (keeping every existing test that
still applies; inline-weapon tests are replaced by these):

```python
"""Enemies reference ruleset statblocks; the loader resolves them to commands."""

import pytest

from application.commands import AddCharacterCommand
from application.encounter import EncounterError, load_encounter
from domain.rules.errors import UnknownRuleEntry
from infrastructure.rules.loader import load_ruleset

SHIPPED = Path(__file__).resolve().parents[2] / "data/rules/dnd5e-srd-5.2"
ENCOUNTER = Path(__file__).resolve().parents[2] / "config/encounter.toml"


@pytest.fixture
def ruleset() -> object:
    return load_ruleset(SHIPPED)


def test_load_resolves_the_three_enemies_from_statblocks(ruleset: object) -> None:
    commands = load_encounter(ENCOUNTER, ruleset)  # type: ignore[arg-type]
    assert [command.name for command in commands] == [
        "Goblin Scout",
        "Goblin Skulker",
        "Orc Brute",
    ]


def test_statblock_numbers_survive_the_migration(ruleset: object) -> None:
    """Byte-equivalence with the pre-migration encounter.toml values."""
    commands = load_encounter(ENCOUNTER, ruleset)  # type: ignore[arg-type]
    scout, skulker, orc = commands
    for command in (scout, skulker):
        assert (command.strength, command.dexterity, command.constitution) == (8, 14, 10)
        assert command.armor_class == 13
        assert command.max_hp == 7
        assert command.weapon is not None
        assert command.weapon.weapon_id == "scimitar"
        assert command.weapon.damage_die_size == 6
    assert (orc.strength, orc.dexterity, orc.constitution) == (16, 12, 14)
    assert orc.armor_class == 15
    assert orc.max_hp == 15
    assert orc.weapon is not None
    assert orc.weapon.weapon_id == "greataxe"
    assert orc.weapon.damage_die_size == 12


def test_unknown_statblock_id_is_rejected(tmp_path: Path, ruleset: object) -> None:
    path = tmp_path / "encounter.toml"
    path.write_text('[[enemies]]\nstatblock = "dragon_boss"\n', encoding="utf-8")
    with pytest.raises((EncounterError, UnknownRuleEntry)):
        load_encounter(path, ruleset)  # type: ignore[arg-type]


def test_missing_statblock_key_is_rejected(tmp_path: Path, ruleset: object) -> None:
    path = tmp_path / "encounter.toml"
    path.write_text("[[enemies]]\nname = \"Lone\"\n", encoding="utf-8")
    with pytest.raises(EncounterError):
        load_encounter(path, ruleset)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/test_encounter.py -v`
Expected: the new tests FAIL (`load_encounter` takes no ruleset; the config still carries inline stats).

- [ ] **Step 3: Migrate the config and the loader**

`config/encounter.toml` becomes:

```toml
# The MVP-0 encounter (specs/2026-09-06-multi-agent-party-design.md §3.3).
# The fight is game content; enemy stats live in the active ruleset (R2).

map = "eastern_tower"

[[enemies]]
statblock = "goblin_scout"

[[enemies]]
statblock = "goblin_skulker"

[[enemies]]
statblock = "orc_brute"
```

`src/application/encounter.py` — `load_encounter` gains the ruleset parameter
and the enemy branch resolves a statblock:

```python
def load_encounter(path: Path, ruleset: Ruleset) -> list[AddCharacterCommand]:
    ...
```

For each `[[enemies]]` entry: read `statblock` (missing or blank →
`EncounterError` naming the entry index); `ruleset.statblock(id)` (an
`UnknownRuleEntry` propagates — it names the id); map the `Statblock` onto
`AddCharacterCommand` exactly as `_enemy_command` does today (same
`character_type`, same field names), with the weapon built from
`ruleset.weapon(statblock.weapon_id)` as a `WeaponSpec` carrying the weapon's
dice, ability value string and `range_ft`. Delete `_weapon` and the inline
stat parsing once nothing calls them. Import `Ruleset` from
`domain.rules.ruleset`.

Then update the callers: `grep -rn "load_encounter(" src tests --include=*.py`
— `session.factory.build_session` passes the session ruleset; tests pass the
shipped ruleset.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/test_encounter.py tests/session -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add config/encounter.toml src/application/encounter.py src/session/factory.py tests/application/test_encounter.py
git commit -m "feat(application): resolve encounter enemies from ruleset statblocks"
```

---

### Task 6: Weapons become ruleset ids at every call site

**Files:**
- Modify: `config/agents.toml`
- Modify: `src/application/agents/profiles.py`
- Modify: `src/session/factory.py` (`_fighter`)
- Test: `tests/application/agents/test_profiles.py` (extend), `tests/session/test_ruleset_selection.py` (extend)

**Interfaces:**
- Consumes: Task 1's `Ruleset`; Task 3's `load_ruleset`; the shipped weapon ids from Task 2.
- Produces: `load_agent_profiles(path: Path, ruleset: Ruleset) -> AgentProfileCatalog`; a `weapon_id: str` field on the parsed agent stats; a shared `weapon_spec(ruleset: Ruleset, weapon_id: str) -> WeaponSpec` helper in `application.commands` used by `profiles.py`, `encounter.py` and `factory.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/application/agents/test_profiles.py`:

```python
def test_stats_carry_a_weapon_id_resolved_through_the_ruleset() -> None:
    ruleset = load_ruleset(SHIPPED)
    catalog = load_agent_profiles(AGENTS_TOML, ruleset)
    brix = catalog.agents["brix"]
    assert brix.stats.weapon_id == "longsword"
    assert brix.stats.weapon is not None
    assert brix.stats.weapon.damage_die_size == 8
    assert brix.stats.weapon.weapon_id == "longsword"


def test_unknown_agent_weapon_id_is_rejected(tmp_path: Path) -> None:
    ruleset = load_ruleset(SHIPPED)
    text = AGENTS_TOML.read_text(encoding="utf-8").replace(
        'weapon_id = "longsword"', 'weapon_id = "vorpal_blade"'
    )
    path = tmp_path / "agents.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(UnknownRuleEntry):
        load_agent_profiles(path, ruleset)
```

(adapt the imports and the `AGENTS_TOML`/`SHIPPED` constants to that file's
existing style — it already loads `config/agents.toml`; point `SHIPPED` at
`data/rules/dnd5e-srd-5.2`.)

Append to `tests/session/test_ruleset_selection.py`:

```python
def test_weapon_spec_helper_resolves_through_the_ruleset() -> None:
    from application.commands import weapon_spec

    ruleset = load_ruleset(SHIPPED)
    spec = weapon_spec(ruleset, "longsword")
    assert spec.weapon_id == "longsword"
    assert spec.damage_die_count == 1
    assert spec.damage_die_size == 8
    assert spec.ability == "strength"
    assert spec.range_ft == 5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/agents/test_profiles.py tests/session/test_ruleset_selection.py -v`
Expected: the new tests FAIL (`load_agent_profiles` takes no ruleset; `weapon_spec` does not exist).

- [ ] **Step 3: Implement**

`src/application/commands.py` — add the shared resolver:

```python
from domain.character.abilities import AbilityType
from domain.rules.ruleset import Ruleset


def weapon_spec(ruleset: Ruleset, weapon_id: str) -> WeaponSpec:
    """Resolve a ruleset weapon id into the command carry-type (R2 spec §2)."""
    weapon = ruleset.weapon(weapon_id)
    return WeaponSpec(
        weapon_id=weapon.weapon_id,
        name=weapon.name,
        damage_die_count=weapon.damage_die_count,
        damage_die_size=weapon.damage_die_size,
        ability=weapon.ability.value
        if isinstance(weapon.ability, AbilityType)
        else str(weapon.ability),
        range_ft=weapon.range_ft,
    )
```

`config/agents.toml` — replace each `[agents.<id>.stats.weapon]` table with a
scalar `weapon_id` on the stats table (`brix` → `"longsword"`, `mira` →
`"shortsword"`, `sera` → `"mace"`), e.g.:

```toml
[agents.brix.stats]
# ...ability scores, armor_class, speed_ft, max_hp as today...
weapon_id = "longsword"
```

`src/application/agents/profiles.py` — the stats dataclass replaces its
`weapon: WeaponSpec` field with `weapon_id: str`; parsing reads the scalar
(missing/blank → the file's existing profile-parse error type, naming the
agent); `load_agent_profiles(path, ruleset)` builds
`weapon=weapon_spec(ruleset, stats.weapon_id)` alongside it so downstream
consumers of `stats.weapon` are untouched. Update `grep -rn
"load_agent_profiles(" src tests --include=*.py` call sites —
`session.factory._wire_party` passes the session ruleset.

`src/session/factory.py` — `_fighter(name)` becomes `_fighter(name, ruleset)`
(or a module-level helper) building the command with
`weapon=weapon_spec(ruleset, "longsword")`; `build_session` passes the ruleset
it already loaded in Task 4. Update any direct `_fighter(` call sites in tests.

- [ ] **Step 4: Run the tests to verify they pass, then the full gate**

Run: `.venv/bin/python -m pytest tests/application/agents/test_profiles.py tests/session/test_ruleset_selection.py -v`
Expected: the new tests pass.

Run the full gate:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy
```

Expected: full suite green, ruff clean, mypy clean (FROZEN ADAPTER LICENCE: if
an `ai/` test breaks only because a loader signature gained a parameter, adapt
the call site; add no capability).

- [ ] **Step 5: Commit**

```bash
git add config/agents.toml src/application/commands.py src/application/agents/profiles.py src/session/factory.py tests
git commit -m "feat(application): resolve all weapons through the ruleset port"
```

---

### Task 7: Mark the roadmap row and run the completion gate

**Files:**
- Modify: `docs/superpowers/plans/README.md` (row 15)
- Modify: `docs/Agentic Conclave-Implementation Plan.md` (the R2 section's status line, if the restructure gave R-sections status markers — mirror whatever row 14 did for R1)

**Interfaces:**
- Consumes: nothing.
- Produces: the roadmap reflecting R2 complete.

- [ ] **Step 1: Update the roadmap**

In `docs/superpowers/plans/README.md`, row 15's plan file becomes
`2026-10-07-rules-core-r2-ruleset.md` and its status becomes `Complete`,
matching how the R1 row (`2026-10-06-rules-core-r1-grid.md`) was marked. Keep
the "R2 Ruleset & data - Ruleset port, `data/rules/*.toml`, loader, SRD NOTICE"
covers text. Mirror the equivalent status marking in the Implementation Plan's
R2 section if one exists.

- [ ] **Step 2: Run the full gate**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy
```

Expected: full suite green, ruff clean, mypy clean. The roadmap-consistency
tests in `tests/docs/test_roadmap_consistency.py` must still pass (row text is
unchanged except file name and status).

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/README.md "docs/Agentic Conclave-Implementation Plan.md" docs/superpowers/plans/2026-10-07-rules-core-r2-ruleset.md
git commit -m "docs(plans): mark R2 ruleset and data complete"
```

---

## Self-review notes (written at plan time)

- **Spec coverage:** port (T1), data files + NOTICE (T2), loader (T3), selection
  + diagonal-rule wiring (T4), monster migration (T5), weapon + class migration
  (T6; `classes.toml` is loaded and validated by T3 but consumed only from R8 —
  that is the spec's stated scope). Exit criterion: after T4-T6 the ruleset id
  in `config/game.toml` is the only place the ruleset is named.
- **Type consistency:** `Ruleset`, `TomlRuleset`, `Statblock`, `ClassData`,
  `RulesetError`, `UnknownRuleEntry`, `weapon_spec`, `load_encounter(path,
  ruleset)`, `load_agent_profiles(path, ruleset)`, `load_session_ruleset`,
  `ruleset_id_from_config`, `distance_ft(..., diagonal_rule=)`,
  `CombatEngine(dice, diagonal_rule=)` — used identically across tasks.
- **Review Focus pins:** dangling reference → T3; unknown id → T1 + T3; migration
  drift → T2 + T5 byte-equivalence; config-only swap → T4; optional-ruleset rot →
  T4's default-behaviour tests plus the full-suite runs in T6/T7.
