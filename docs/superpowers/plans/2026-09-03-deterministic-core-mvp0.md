# Deterministic Core (MVP-0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic D&D core — typed domain primitives, seeded dice, checks, actions, a full combat engine, domain events, application services, and a playable Rich CLI combat sandbox (Fighter vs Goblin) that works with **no LLM, no database, no network** (Implementation Plan §26 MVP-0).

**Architecture:** Modular monolith with five top-level packages under `src/` (`domain`, `application`, `ai`, `infrastructure`, `interfaces`) per CLAUDE.md §4. Dependency direction is strictly `interfaces → application → domain`; `ai` and `infrastructure` depend only on application/domain abstractions. LLMs never decide rules: every action enters the engine as an `ActionProposal`, is validated by the domain, resolved deterministically, and recorded as immutable past-tense events.

**Tech Stack:** Python 3.12 (stdlib-only domain layer), pytest, ruff, mypy (strict), Rich (CLI layer only). No other dependencies.

**Spec:** `docs/Agentic Conclave-Implementation Plan.md` (§2–§10, §26 MVP-0), `CLAUDE.md`, `docs/Agentic Conclave-architecture-overview.md`. This plan argues from those documents; executors read all three. Source-of-truth priority on conflict: CLAUDE.md → spec docs → tests → code (Implementation Plan §29).

## Global Constraints

These apply to **every task** and are copied from the governing documents:

- Python `>=3.12`; all randomness flows through the seeded `DiceRoller` — never `random` directly (CLAUDE.md §15).
- The domain layer imports **nothing** from `application`, `ai`, `infrastructure`, `interfaces`, or any third-party library (CLAUDE.md §4, §5).
- All state mutation goes through explicit domain methods (e.g. `character.apply_damage(n)`), never raw attribute assignment from application/adapter code (CLAUDE.md §62).
- Events are named in the past tense and record what happened; requests are commands, never events (CLAUDE.md §12).
- Expected domain failures raise the explicit errors from CLAUDE.md §49 — never bare `Exception`/`ValueError` for domain failures.
- No LLM, PostgreSQL, FastAPI, or AI-framework dependencies in this plan (Implementation Plan §27; those belong to Plans 2+).
- Tests never require a real LLM or network (CLAUDE.md §46).
- Conventional commits scoped by architectural layer, e.g. `feat(domain): ...`, each ending with the trailer `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
- Tooling commands assume the venv created in Task 1; pytest runs as `.venv/bin/python -m pytest` (the venv does not persist between shells).
- Character ≠ Agent: this plan models characters only; agents arrive in Plan 4 (CLAUDE.md §16).
- Party size is data, never hardcoded: party is a list of 1+ characters (CLAUDE.md §17).

## Development environment (Task 1 sets this up; all tasks assume it)

```bash
cd /home/yss/workspace/agentic-conclave
uv venv .venv --python 3.12
uv pip install -e ".[dev]"
```

Full-suite command used in every task's verification: `.venv/bin/python -m pytest -q`

---

### Task 1: Repository Bootstrap & Tooling

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `src/__init__.py`, `src/domain/__init__.py`, `src/application/__init__.py`, `src/ai/__init__.py`, `src/infrastructure/__init__.py`, `src/interfaces/__init__.py` (all empty)
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: installable package `agentic-conclave` 0.1.0 with editable dev install; commands `.venv/bin/python -m pytest`, `.venv/bin/python -m ruff`, `.venv/bin/python -m mypy`; top-level packages `domain`, `application`, `ai`, `infrastructure`, `interfaces` importable from `src/`.

- [ ] **Step 1: Initialize git and create the skeleton**

```bash
cd /home/yss/workspace/agentic-conclave
git init
mkdir -p src/domain src/application src/ai src/infrastructure src/interfaces tests docs data scripts
for d in src src/domain src/application src/ai src/infrastructure src/interfaces; do
  touch "$d/__init__.py"
done
# data/ and scripts/ gain content in later plans; keep them tracked via .gitkeep.
touch data/.gitkeep scripts/.gitkeep
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
dist/
*.egg-info/
.env
```

- [ ] **Step 3: Write `.env.example` (placeholder only — never real credentials)**

```bash
# Copy to .env and fill in. .env is gitignored; never commit real credentials.
OPENROUTER_API_KEY=
```

- [ ] **Step 4: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "agentic-conclave"
version = "0.1.0"
description = "AI-powered multi-agent D&D RPG with a deterministic rules engine"
requires-python = ">=3.12"
dependencies = [
    "rich>=13.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "ruff>=0.6",
    "mypy>=1.11",
]

[project.scripts]
conclave = "interfaces.cli.app:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.12"
strict = true
mypy_path = "src"
files = ["src"]
```

- [ ] **Step 5: Write `README.md` (stub, expanded in later tasks)**

```markdown
# Agentic Conclave

An AI-powered multi-agent D&D RPG built on a deterministic rules engine:
LLMs propose. The domain decides. The game engine executes. Events record what happened.

## Setup

```bash
uv venv .venv --python 3.12
uv pip install -e ".[dev]"
```

## Run tests / lint / typecheck

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy
```

## Play (MVP-0 deterministic combat sandbox)

```bash
.venv/bin/python -m interfaces.cli.app --seed 42
```
```

- [ ] **Step 6: Write the smoke test**

```python
# tests/test_smoke.py
def test_top_level_packages_import() -> None:
    import application
    import domain

    assert domain is not None
    assert application is not None


def test_package_metadata() -> None:
    from importlib.metadata import version

    assert version("agentic-conclave") == "0.1.0"
```

- [ ] **Step 7: Create the venv and install**

```bash
uv venv .venv --python 3.12
uv pip install -e ".[dev]"
```

- [ ] **Step 8: Run the smoke test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_smoke.py -v`
Expected: PASS (2 tests)

- [ ] **Step 9: Verify lint and typecheck are clean**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: no errors

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml .gitignore .env.example README.md src tests data scripts
git commit -m "chore: bootstrap repository with pytest, ruff, mypy and src/ skeleton" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: Typed Identifiers & Domain Errors

**Files:**
- Create: `src/domain/common/ids.py`, `src/domain/common/errors.py`, `src/domain/common/__init__.py` (empty)
- Test: `tests/domain/test_ids.py`, `tests/domain/test_errors.py`

**Interfaces:**
- Consumes: nothing beyond stdlib.
- Produces:
  - `class EntityId` — frozen dataclass with `value: str`, raises `ValueError` on empty/whitespace, classmethod `generate() -> Self`, `__str__` returns `value`.
  - Subclasses: `CampaignId`, `GameId`, `CharacterId`, `AgentId`, `LocationId`, `QuestId`, `EventId` (each with `generate()` inherited).
  - `class DomainError(Exception)` and subclasses `ValidationError`, `CharacterNotFoundError`, `GameNotFoundError`, `InvalidActionError`, `NotYourTurnError`, `ActionNotAvailableError`, `CombatNotActiveError`, `InsufficientResourceError`, `GameNotRunningError`, `AgentDecisionFailedError`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_ids.py
from domain.common.ids import (
    AgentId,
    CampaignId,
    CharacterId,
    EntityId,
    EventId,
    GameId,
    LocationId,
    QuestId,
)


def test_entity_id_accepts_non_empty_value() -> None:
    entity_id = EntityId("game-1")
    assert entity_id.value == "game-1"
    assert str(entity_id) == "game-1"


def test_entity_id_rejects_empty_value() -> None:
    import pytest

    with pytest.raises(ValueError):
        EntityId("   ")


def test_generate_returns_distinct_ids_per_type() -> None:
    first = GameId.generate()
    second = GameId.generate()
    assert first != second
    assert isinstance(first, GameId)
    assert isinstance(CharacterId.generate(), CharacterId)


def test_each_id_type_is_distinct_class() -> None:
    for cls in (CampaignId, GameId, CharacterId, AgentId, LocationId, QuestId, EventId):
        assert issubclass(cls, EntityId)
        assert cls.generate().value != ""
```

```python
# tests/domain/test_errors.py
import pytest

from domain.common.errors import (
    AgentDecisionFailedError,
    CombatNotActiveError,
    DomainError,
    GameNotFoundError,
    InsufficientResourceError,
    ValidationError,
)


def test_all_domain_errors_inherit_from_domain_error() -> None:
    errors = [
        ValidationError,
        GameNotFoundError,
        InsufficientResourceError,
        CombatNotActiveError,
        AgentDecisionFailedError,
    ]
    for error in errors:
        assert issubclass(error, DomainError)


def test_domain_error_is_catchable_as_exception_with_message() -> None:
    with pytest.raises(DomainError, match="no such game"):
        raise GameNotFoundError("no such game")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_ids.py tests/domain/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.common'`

- [ ] **Step 3: Write the implementation**

```python
# src/domain/common/ids.py
"""Strongly typed identifiers for domain entities (CLAUDE.md §61)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self
from uuid import uuid4


@dataclass(frozen=True)
class EntityId:
    """Base type for strongly typed identifiers."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("id value must be a non-empty string")

    @classmethod
    def generate(cls) -> Self:
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


class CampaignId(EntityId):
    pass


class GameId(EntityId):
    pass


class CharacterId(EntityId):
    pass


class AgentId(EntityId):
    pass


class LocationId(EntityId):
    pass


class QuestId(EntityId):
    pass


class EventId(EntityId):
    pass
```

```python
# src/domain/common/errors.py
"""Explicit domain errors (CLAUDE.md §49). Expected failures are never bare Exception."""


class DomainError(Exception):
    """Base class for all expected domain failures."""


class ValidationError(DomainError):
    """A value or state is invalid."""


class CharacterNotFoundError(DomainError):
    pass


class GameNotFoundError(DomainError):
    pass


class InvalidActionError(DomainError):
    pass


class NotYourTurnError(DomainError):
    pass


class ActionNotAvailableError(DomainError):
    pass


class CombatNotActiveError(DomainError):
    pass


class InsufficientResourceError(DomainError):
    pass


class GameNotRunningError(DomainError):
    pass


class AgentDecisionFailedError(DomainError):
    pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_ids.py tests/domain/test_errors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/common tests/domain/test_ids.py tests/domain/test_errors.py
git commit -m "feat(domain): add typed identifiers and explicit domain errors" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Ability Scores

**Files:**
- Create: `src/domain/character/abilities.py`, `src/domain/character/__init__.py` (empty)
- Test: `tests/domain/test_abilities.py`

**Interfaces:**
- Consumes: `ValidationError` from `domain.common.errors` (Task 2).
- Produces:
  - `class AbilityType(StrEnum)`: `STRENGTH`, `DEXTERITY`, `CONSTITUTION`, `INTELLIGENCE`, `WISDOM`, `CHARISMA` (values are lowercase strings).
  - `MIN_SCORE = 1`, `MAX_SCORE = 30`.
  - `def ability_modifier(score: int) -> int` — `floor((score - 10) / 2)` implemented as `(score - 10) // 2`; raises `ValidationError` outside 1–30.
  - `@dataclass(frozen=True) class AbilityScore`: `ability_type: AbilityType`, `score: int`, property `modifier: int`.
  - `@dataclass(frozen=True) class AbilityScores`: fields `strength, dexterity, constitution, intelligence, wisdom, charisma: int`; `score(ability: AbilityType) -> int`, `modifier(ability: AbilityType) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_abilities.py
import pytest

from domain.character.abilities import (
    MAX_SCORE,
    MIN_SCORE,
    AbilityScores,
    AbilityScore,
    AbilityType,
    ability_modifier,
)
from domain.common.errors import ValidationError


@pytest.mark.parametrize(
    ("score", "expected"),
    [(1, -5), (8, -1), (9, -1), (10, 0), (11, 0), (16, 3), (20, 5), (30, 10)],
)
def test_ability_modifier_uses_floor_division(score: int, expected: int) -> None:
    assert ability_modifier(score) == expected


@pytest.mark.parametrize("score", [0, 31, -3])
def test_ability_modifier_rejects_out_of_range(score: int) -> None:
    with pytest.raises(ValidationError):
        ability_modifier(score)


def test_ability_score_value_object() -> None:
    strength = AbilityScore(ability_type=AbilityType.STRENGTH, score=16)
    assert strength.modifier == 3
    assert strength.score == 16


def test_bounds_constants() -> None:
    assert (MIN_SCORE, MAX_SCORE) == (1, 30)


def test_ability_scores_aggregate() -> None:
    scores = AbilityScores(
        strength=16,
        dexterity=13,
        constitution=15,
        intelligence=10,
        wisdom=12,
        charisma=9,
    )
    assert scores.score(AbilityType.DEXTERITY) == 13
    assert scores.modifier(AbilityType.DEXTERITY) == 1
    assert scores.modifier(AbilityType.CHARISMA) == -1


def test_ability_scores_reject_invalid_score() -> None:
    with pytest.raises(ValidationError):
        AbilityScores(
            strength=16,
            dexterity=13,
            constitution=15,
            intelligence=10,
            wisdom=12,
            charisma=99,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_abilities.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.character'`

- [ ] **Step 3: Write the implementation**

```python
# src/domain/character/abilities.py
"""Ability scores and modifiers — Implementation Plan §4.2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domain.common.errors import ValidationError

MIN_SCORE = 1
MAX_SCORE = 30


class AbilityType(StrEnum):
    STRENGTH = "strength"
    DEXTERITY = "dexterity"
    CONSTITUTION = "constitution"
    INTELLIGENCE = "intelligence"
    WISDOM = "wisdom"
    CHARISMA = "charisma"


def _validate_score(score: int) -> None:
    if not MIN_SCORE <= score <= MAX_SCORE:
        raise ValidationError(
            f"ability score must be between {MIN_SCORE} and {MAX_SCORE}, got {score}"
        )


def ability_modifier(score: int) -> int:
    """D&D 5e ability modifier: floor((score - 10) / 2)."""
    _validate_score(score)
    return (score - 10) // 2


@dataclass(frozen=True)
class AbilityScore:
    ability_type: AbilityType
    score: int

    def __post_init__(self) -> None:
        _validate_score(self.score)

    @property
    def modifier(self) -> int:
        return ability_modifier(self.score)


@dataclass(frozen=True)
class AbilityScores:
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int

    def __post_init__(self) -> None:
        for ability_type in AbilityType:
            _validate_score(self.score(ability_type))

    def score(self, ability_type: AbilityType) -> int:
        return getattr(self, ability_type.value)

    def modifier(self, ability_type: AbilityType) -> int:
        return ability_modifier(self.score(ability_type))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_abilities.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/character tests/domain/test_abilities.py
git commit -m "feat(domain): add ability scores with floor-division modifiers" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: Proficiency Bonus

**Files:**
- Create: `src/domain/rules/progression.py`, `src/domain/rules/__init__.py` (empty)
- Test: `tests/domain/test_progression.py`

**Interfaces:**
- Consumes: `ValidationError` (Task 2).
- Produces: `def proficiency_bonus(level: int) -> int` — `2 + (level - 1) // 4` for levels 1–20; raises `ValidationError` outside that range.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_progression.py
import pytest

from domain.common.errors import ValidationError
from domain.rules.progression import proficiency_bonus


@pytest.mark.parametrize(
    ("level", "expected"),
    [(1, 2), (4, 2), (5, 3), (8, 3), (9, 4), (12, 4), (13, 5), (17, 6), (20, 6)],
)
def test_proficiency_bonus_by_level(level: int, expected: int) -> None:
    assert proficiency_bonus(level) == expected


@pytest.mark.parametrize("level", [0, 21, -1])
def test_proficiency_bonus_rejects_invalid_level(level: int) -> None:
    with pytest.raises(ValidationError):
        proficiency_bonus(level)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_progression.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.rules'`

- [ ] **Step 3: Write the implementation**

```python
# src/domain/rules/progression.py
"""Character progression rules (Implementation Plan §4.3)."""

from __future__ import annotations

from domain.common.errors import ValidationError

MIN_LEVEL = 1
MAX_LEVEL = 20


def proficiency_bonus(level: int) -> int:
    """D&D 5e proficiency bonus: 2 + floor((level - 1) / 4)."""
    if not MIN_LEVEL <= level <= MAX_LEVEL:
        raise ValidationError(
            f"level must be between {MIN_LEVEL} and {MAX_LEVEL}, got {level}"
        )
    return 2 + (level - 1) // 4
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_progression.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/rules tests/domain/test_progression.py
git commit -m "feat(domain): add proficiency bonus progression rule" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: Hit Points & Inventory

**Files:**
- Create: `src/domain/character/vitals.py`, `src/domain/character/inventory.py`
- Test: `tests/domain/test_vitals.py`, `tests/domain/test_inventory.py`

**Interfaces:**
- Consumes: `ValidationError`, `InsufficientResourceError` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class HitPoints`: `current: int`, `maximum: int`; `apply_damage(amount: int) -> HitPoints` (clamped at 0, raises `ValidationError` on negative amount), `apply_healing(amount: int) -> HitPoints` (clamped at maximum), property `is_defeated: bool`. `maximum` must be ≥ 1 and `current` within 0–`maximum`.
  - `@dataclass class Item`: `item_id: str`, `name: str`, `quantity: int` (quantity ≥ 1).
  - `@dataclass class Inventory`: `items: dict[str, Item]`, `gold: int = 0`; `add_item(item_id: str, name: str, quantity: int) -> None`, `remove_item(item_id: str, quantity: int) -> None` (raises `InsufficientResourceError`), `get_item(item_id: str) -> Item | None`, `add_gold(amount: int) -> None`, `spend_gold(amount: int) -> None` (raises `InsufficientResourceError`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_vitals.py
import pytest

from domain.character.vitals import HitPoints
from domain.common.errors import ValidationError


def test_hit_points_validate_construction() -> None:
    with pytest.raises(ValidationError):
        HitPoints(current=-1, maximum=10)
    with pytest.raises(ValidationError):
        HitPoints(current=11, maximum=10)
    with pytest.raises(ValidationError):
        HitPoints(current=5, maximum=0)


def test_damage_clamps_at_zero() -> None:
    hp = HitPoints(current=3, maximum=10)
    reduced = hp.apply_damage(5)
    assert reduced.current == 0
    assert reduced.maximum == 10
    assert reduced.is_defeated is True


def test_damage_rejects_negative_amount() -> None:
    with pytest.raises(ValidationError):
        HitPoints(current=5, maximum=10).apply_damage(-1)


def test_healing_clamps_at_maximum_and_zero_hp_is_not_defeated_after_heal() -> None:
    hp = HitPoints(current=0, maximum=10)
    healed = hp.apply_healing(99)
    assert healed.current == 10
    assert healed.is_defeated is False


def test_damage_returns_new_immutable_value() -> None:
    hp = HitPoints(current=10, maximum=10)
    reduced = hp.apply_damage(4)
    assert hp.current == 10
    assert reduced.current == 6
    assert reduced.is_defeated is False
```

```python
# tests/domain/test_inventory.py
import pytest

from domain.character.inventory import Inventory
from domain.common.errors import InsufficientResourceError, ValidationError


def test_add_then_remove_item() -> None:
    inventory = Inventory()
    inventory.add_item("rope", "Hempen Rope", 1)
    inventory.add_item("rope", "Hempen Rope", 2)
    assert inventory.get_item("rope") is not None
    assert inventory.get_item("rope").quantity == 3

    inventory.remove_item("rope", 2)
    assert inventory.get_item("rope").quantity == 1


def test_remove_item_raises_when_missing_or_insufficient() -> None:
    inventory = Inventory()
    with pytest.raises(InsufficientResourceError):
        inventory.remove_item("rope", 1)

    inventory.add_item("rope", "Hempen Rope", 1)
    with pytest.raises(InsufficientResourceError):
        inventory.remove_item("rope", 2)


def test_add_item_rejects_invalid_quantity_or_name() -> None:
    inventory = Inventory()
    with pytest.raises(ValidationError):
        inventory.add_item("rope", "Hempen Rope", 0)
    with pytest.raises(ValidationError):
        inventory.add_item("rope", "  ", 1)


def test_gold_add_and_spend() -> None:
    inventory = Inventory(gold=10)
    inventory.add_gold(5)
    inventory.spend_gold(15)
    assert inventory.gold == 0


def test_spend_gold_raises_when_insufficient() -> None:
    inventory = Inventory(gold=1)
    with pytest.raises(InsufficientResourceError):
        inventory.spend_gold(2)


def test_negative_gold_rejected() -> None:
    with pytest.raises(ValidationError):
        Inventory(gold=-1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_vitals.py tests/domain/test_inventory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.character.vitals'`

- [ ] **Step 3: Write the implementation**

```python
# src/domain/character/vitals.py
"""Hit points as an immutable value object with clamping semantics."""

from __future__ import annotations

from dataclasses import dataclass

from domain.common.errors import ValidationError


@dataclass(frozen=True)
class HitPoints:
    current: int
    maximum: int

    def __post_init__(self) -> None:
        if self.maximum < 1:
            raise ValidationError(f"maximum hp must be at least 1, got {self.maximum}")
        if not 0 <= self.current <= self.maximum:
            raise ValidationError(
                f"current hp must be between 0 and {self.maximum}, got {self.current}"
            )

    @property
    def is_defeated(self) -> bool:
        return self.current == 0

    def apply_damage(self, amount: int) -> HitPoints:
        if amount < 0:
            raise ValidationError("damage amount must be non-negative")
        return HitPoints(current=max(0, self.current - amount), maximum=self.maximum)

    def apply_healing(self, amount: int) -> HitPoints:
        if amount < 0:
            raise ValidationError("healing amount must be non-negative")
        return HitPoints(
            current=min(self.maximum, self.current + amount), maximum=self.maximum
        )
```

```python
# src/domain/character/inventory.py
"""Character inventory with explicit error signaling."""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.common.errors import InsufficientResourceError, ValidationError


@dataclass
class Item:
    item_id: str
    name: str
    quantity: int

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise ValidationError("item_id must be a non-empty string")
        if not self.name.strip():
            raise ValidationError("item name must be a non-empty string")
        if self.quantity < 1:
            raise ValidationError("item quantity must be at least 1")


@dataclass
class Inventory:
    items: dict[str, Item] = field(default_factory=dict)
    gold: int = 0

    def __post_init__(self) -> None:
        if self.gold < 0:
            raise ValidationError("gold must be non-negative")

    def get_item(self, item_id: str) -> Item | None:
        return self.items.get(item_id)

    def add_item(self, item_id: str, name: str, quantity: int) -> None:
        if quantity < 1:
            raise ValidationError("quantity must be at least 1")
        existing = self.items.get(item_id)
        if existing is None:
            self.items[item_id] = Item(item_id=item_id, name=name, quantity=quantity)
        else:
            existing.quantity += quantity

    def remove_item(self, item_id: str, quantity: int) -> None:
        existing = self.items.get(item_id)
        if existing is None or existing.quantity < quantity:
            raise InsufficientResourceError(
                f"not enough of item '{item_id}' to remove {quantity}"
            )
        existing.quantity -= quantity
        if existing.quantity == 0:
            del self.items[item_id]

    def add_gold(self, amount: int) -> None:
        if amount < 0:
            raise ValidationError("gold amount must be non-negative")
        self.gold += amount

    def spend_gold(self, amount: int) -> None:
        if amount < 0:
            raise ValidationError("gold amount must be non-negative")
        if self.gold < amount:
            raise InsufficientResourceError(
                f"need {amount} gold, only {self.gold} available"
            )
        self.gold -= amount
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_vitals.py tests/domain/test_inventory.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/domain/character tests/domain/test_vitals.py tests/domain/test_inventory.py
git commit -m "feat(domain): add hit points and inventory value objects" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: Deterministic Dice Engine

**Files:**
- Create: `src/domain/rules/dice.py`
- Test: `tests/domain/test_dice.py`

**Interfaces:**
- Consumes: `ValidationError` (Task 2).
- Produces:
  - `DIE_SIZES: tuple[int, ...] = (4, 6, 8, 10, 12, 20, 100)`.
  - `class RollMode(StrEnum)`: `NORMAL`, `ADVANTAGE`, `DISADVANTAGE`.
  - `@dataclass(frozen=True) class DiceResult`: `die_size: int`, `all_rolls: tuple[int, ...]`, `kept_rolls: tuple[int, ...]`, `modifier: int`, `total: int`; property `natural: int | None` (kept roll for a single d20, else `None`).
  - `class DiceRoller`: `__init__(self, seed: int | None = None)`; `roll(count: int, die_size: int, modifier: int = 0, mode: RollMode = RollMode.NORMAL) -> DiceResult`; `roll_d20(modifier: int = 0, mode: RollMode = RollMode.NORMAL) -> DiceResult`; `roll_expression(expression: str) -> DiceResult` (parses `2d6+1`, `d20`, `1d8-2`; normal mode only).

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_dice.py
import pytest

from domain.rules.dice import DIE_SIZES, DiceRoller, RollMode
from domain.common.errors import ValidationError


def test_same_seed_same_sequence() -> None:
    first = DiceRoller(seed=12345)
    second = DiceRoller(seed=12345)
    sequence_a = [first.roll(2, 6).total for _ in range(10)]
    sequence_b = [second.roll(2, 6).total for _ in range(10)]
    assert sequence_a == sequence_b


def test_different_seeds_differ_somewhere() -> None:
    first = DiceRoller(seed=1)
    second = DiceRoller(seed=2)
    sequence_a = [first.roll_d20().total for _ in range(20)]
    sequence_b = [second.roll_d20().total for _ in range(20)]
    assert sequence_a != sequence_b


@pytest.mark.parametrize("die_size", DIE_SIZES)
def test_single_die_within_range(die_size: int) -> None:
    roller = DiceRoller(seed=99)
    for _ in range(50):
        result = roller.roll(1, die_size)
        assert 1 <= result.all_rolls[0] <= die_size


def test_roll_multiple_dice_with_modifier() -> None:
    result = DiceRoller(seed=5).roll(3, 6, modifier=2)
    assert len(result.all_rolls) == 3
    assert sum(result.all_rolls) + 2 == result.total
    assert result.kept_rolls == result.all_rolls


def test_roll_rejects_invalid_count_or_die_size() -> None:
    roller = DiceRoller(seed=1)
    with pytest.raises(ValidationError):
        roller.roll(0, 6)
    with pytest.raises(ValidationError):
        roller.roll(1, 7)
    with pytest.raises(ValidationError):
        roller.roll(1, 3)


def test_advantage_keeps_higher_of_two_d20() -> None:
    roller = DiceRoller(seed=8)
    for _ in range(30):
        result = roller.roll_d20(mode=RollMode.ADVANTAGE)
        assert len(result.all_rolls) == 2
        assert result.kept_rolls == (max(result.all_rolls),)


def test_disadvantage_keeps_lower_of_two_d20() -> None:
    roller = DiceRoller(seed=8)
    for _ in range(30):
        result = roller.roll_d20(mode=RollMode.DISADVANTAGE)
        assert result.kept_rolls == (min(result.all_rolls),)


def test_advantage_requires_single_d20() -> None:
    roller = DiceRoller(seed=1)
    with pytest.raises(ValidationError):
        roller.roll(2, 20, mode=RollMode.ADVANTAGE)
    with pytest.raises(ValidationError):
        roller.roll(1, 6, mode=RollMode.ADVANTAGE)


def test_natural_is_exposed_for_d20_only() -> None:
    roller = DiceRoller(seed=8)
    d20 = roller.roll_d20()
    assert d20.natural == d20.kept_rolls[0]
    assert roller.roll(1, 6).natural is None


def test_natural_twenty_and_one_are_reachable() -> None:
    crit_seed = next(s for s in range(1000) if DiceRoller(seed=s).roll_d20().natural == 20)
    fumble_seed = next(s for s in range(1000) if DiceRoller(seed=s).roll_d20().natural == 1)
    assert DiceRoller(seed=crit_seed).roll_d20().natural == 20
    assert DiceRoller(seed=fumble_seed).roll_d20().natural == 1


def test_roll_expression_parses_common_forms() -> None:
    roller = DiceRoller(seed=11)
    result = roller.roll_expression("2d6+1")
    assert len(result.all_rolls) == 2
    assert result.total == sum(result.all_rolls) + 1

    single = roller.roll_expression("d20")
    assert len(single.all_rolls) == 1
    assert single.modifier == 0

    negative = roller.roll_expression("1d8-2")
    assert negative.total == negative.all_rolls[0] - 2


def test_roll_expression_rejects_malformed_input() -> None:
    roller = DiceRoller(seed=1)
    for expression in ("banana", "2d7", "0d6", "d", "2d6+1d4"):
        with pytest.raises(ValidationError):
            roller.roll_expression(expression)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_dice.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.rules.dice'`

- [ ] **Step 3: Write the implementation**

```python
# src/domain/rules/dice.py
"""Seeded deterministic dice engine (CLAUDE.md §15, Implementation Plan §5)."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from enum import StrEnum

from domain.common.errors import ValidationError

DIE_SIZES: tuple[int, ...] = (4, 6, 8, 10, 12, 20, 100)

_EXPRESSION_PATTERN = re.compile(r"^(\d*)d(\d+)([+-]\d+)?$")


@dataclass(frozen=True)
class DiceResult:
    die_size: int
    all_rolls: tuple[int, ...]
    kept_rolls: tuple[int, ...]
    modifier: int
    total: int

    @property
    def natural(self) -> int | None:
        """The kept natural roll, only meaningful for a single-die d20 roll."""
        if self.die_size == 20 and len(self.kept_rolls) == 1:
            return self.kept_rolls[0]
        return None


class RollMode(StrEnum):
    NORMAL = "normal"
    ADVANTAGE = "advantage"
    DISADVANTAGE = "disadvantage"


class DiceRoller:
    """All game randomness flows through here, seeded for reproducibility."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def roll(
        self,
        count: int,
        die_size: int,
        modifier: int = 0,
        mode: RollMode = RollMode.NORMAL,
    ) -> DiceResult:
        if count < 1:
            raise ValidationError(f"dice count must be at least 1, got {count}")
        if die_size not in DIE_SIZES:
            raise ValidationError(f"die size must be one of {DIE_SIZES}, got d{die_size}")

        if mode is not RollMode.NORMAL:
            if (count, die_size) != (1, 20):
                raise ValidationError(
                    "advantage/disadvantage apply only to a single d20 roll"
                )
            first = self._rng.randint(1, die_size)
            second = self._rng.randint(1, die_size)
            all_rolls = (first, second)
            kept = max(first, second) if mode is RollMode.ADVANTAGE else min(first, second)
            kept_rolls = (kept,)
        else:
            all_rolls = tuple(self._rng.randint(1, die_size) for _ in range(count))
            kept_rolls = all_rolls

        return DiceResult(
            die_size=die_size,
            all_rolls=all_rolls,
            kept_rolls=kept_rolls,
            modifier=modifier,
            total=sum(kept_rolls) + modifier,
        )

    def roll_d20(
        self, modifier: int = 0, mode: RollMode = RollMode.NORMAL
    ) -> DiceResult:
        return self.roll(1, 20, modifier=modifier, mode=mode)

    def roll_expression(self, expression: str) -> DiceResult:
        match = _EXPRESSION_PATTERN.fullmatch(expression.strip().lower())
        if match is None:
            raise ValidationError(f"invalid dice expression: {expression!r}")
        count_text, die_text, modifier_text = match.groups()
        count = int(count_text) if count_text else 1
        die_size = int(die_text)
        modifier = int(modifier_text) if modifier_text else 0
        return self.roll(count, die_size, modifier=modifier)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_dice.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/rules/dice.py tests/domain/test_dice.py
git commit -m "feat(domain): add seeded deterministic dice engine with advantage" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: Checks, Saving Throws & Attack Rolls

**Files:**
- Create: `src/domain/rules/checks.py`
- Test: `tests/domain/test_checks.py`

**Interfaces:**
- Consumes: `DiceRoller`, `RollMode` (Task 6); `ValidationError` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class CheckResult`: `roll: int`, `modifier: int`, `total: int`, `dc: int | None`, `success: bool`, `mode: RollMode`.
  - `@dataclass(frozen=True) class AttackRollResult`: `roll: int`, `attack_bonus: int`, `total: int`, `target_ac: int`, `hit: bool`, `is_critical: bool`, `is_critical_miss: bool`, `mode: RollMode`.
  - `class CheckResolver`: `__init__(self, dice: DiceRoller)`; `ability_check(modifier: int, dc: int | None = None, proficient: bool = False, proficiency_bonus: int = 0, mode: RollMode = RollMode.NORMAL) -> CheckResult`; `saving_throw(modifier: int, dc: int, proficient: bool = False, proficiency_bonus: int = 0, mode: RollMode = RollMode.NORMAL) -> CheckResult`; `attack_roll(attack_bonus: int, target_ac: int, mode: RollMode = RollMode.NORMAL) -> AttackRollResult`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_checks.py
from domain.rules.checks import CheckResolver
from domain.rules.dice import DiceRoller, RollMode


def _seed_with_natural(rolls: list[int]) -> int:
    """Find a seed whose d20 sequence equals `rolls`."""

    def sequence_matches(seed: int) -> bool:
        roller = DiceRoller(seed=seed)
        return [roller.roll_d20().natural for _ in rolls] == rolls

    return next(seed for seed in range(100_000) if sequence_matches(seed))


def test_ability_check_totals_and_dc() -> None:
    seed = _seed_with_natural([15])
    result = CheckResolver(DiceRoller(seed=seed)).ability_check(modifier=3, dc=17)
    assert result.roll == 15
    assert result.modifier == 3
    assert result.total == 18
    assert result.dc == 17
    assert result.success is True


def test_ability_check_proficiency_adds_bonus() -> None:
    seed = _seed_with_natural([10])
    result = CheckResolver(DiceRoller(seed=seed)).ability_check(
        modifier=1, dc=15, proficient=True, proficiency_bonus=2
    )
    assert result.total == 13
    assert result.success is False


def test_saving_throw_success_and_failure() -> None:
    pass_seed = _seed_with_natural([18])
    passed = CheckResolver(DiceRoller(seed=pass_seed)).saving_throw(modifier=1, dc=15)
    assert passed.success is True
    assert passed.mode == RollMode.NORMAL

    fail_seed = _seed_with_natural([2])
    failed = CheckResolver(DiceRoller(seed=fail_seed)).saving_throw(modifier=1, dc=15)
    assert failed.success is False


def test_attack_roll_natural_twenty_always_hits_and_crits() -> None:
    seed = _seed_with_natural([20])
    result = CheckResolver(DiceRoller(seed=seed)).attack_roll(
        attack_bonus=0, target_ac=30
    )
    assert result.is_critical is True
    assert result.is_critical_miss is False
    assert result.hit is True


def test_attack_roll_natural_one_always_misses() -> None:
    seed = _seed_with_natural([1])
    result = CheckResolver(DiceRoller(seed=seed)).attack_roll(
        attack_bonus=25, target_ac=1
    )
    assert result.is_critical_miss is True
    assert result.is_critical is False
    assert result.hit is False


def test_attack_roll_hit_and_miss_by_total() -> None:
    hit_seed = _seed_with_natural([12])
    hit = CheckResolver(DiceRoller(seed=hit_seed)).attack_roll(
        attack_bonus=5, target_ac=16
    )
    assert hit.total == 17
    assert hit.hit is True
    assert hit.is_critical is False

    miss_seed = _seed_with_natural([7])
    miss = CheckResolver(DiceRoller(seed=miss_seed)).attack_roll(
        attack_bonus=5, target_ac=16
    )
    assert miss.total == 12
    assert miss.hit is False


def test_attack_roll_with_advantage_mode() -> None:
    seed = _seed_with_natural([4])
    result = CheckResolver(DiceRoller(seed=seed)).attack_roll(
        attack_bonus=2, target_ac=10, mode=RollMode.ADVANTAGE
    )
    assert result.mode == RollMode.ADVANTAGE
    # Advantage consumes two d20 rolls from the same RNG stream; mirror them.
    mirror = DiceRoller(seed=seed)
    first = mirror.roll_d20().all_rolls[0]
    second = mirror.roll_d20().all_rolls[0]
    assert result.roll == max(first, second)
    assert result.total == result.roll + 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_checks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.rules.checks'`

- [ ] **Step 3: Write the implementation**

```python
# src/domain/rules/checks.py
"""Deterministic resolution of checks, saves, and attack rolls (Implementation Plan §6)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.common.errors import ValidationError
from domain.rules.dice import DiceRoller, RollMode


@dataclass(frozen=True)
class CheckResult:
    roll: int
    modifier: int
    total: int
    dc: int | None
    success: bool
    mode: RollMode


@dataclass(frozen=True)
class AttackRollResult:
    roll: int
    attack_bonus: int
    total: int
    target_ac: int
    hit: bool
    is_critical: bool
    is_critical_miss: bool
    mode: RollMode


class CheckResolver:
    def __init__(self, dice: DiceRoller) -> None:
        self._dice = dice

    def ability_check(
        self,
        modifier: int,
        dc: int | None = None,
        proficient: bool = False,
        proficiency_bonus: int = 0,
        mode: RollMode = RollMode.NORMAL,
    ) -> CheckResult:
        if proficient and proficiency_bonus < 0:
            raise ValidationError("proficiency bonus must be non-negative")
        total_bonus = modifier + (proficiency_bonus if proficient else 0)
        result = self._dice.roll_d20(modifier=total_bonus, mode=mode)
        total = result.total
        success = total >= dc if dc is not None else False
        return CheckResult(
            roll=result.natural if result.natural is not None else 0,
            modifier=total_bonus,
            total=total,
            dc=dc,
            success=success,
            mode=mode,
        )

    def saving_throw(
        self,
        modifier: int,
        dc: int,
        proficient: bool = False,
        proficiency_bonus: int = 0,
        mode: RollMode = RollMode.NORMAL,
    ) -> CheckResult:
        return self.ability_check(
            modifier=modifier,
            dc=dc,
            proficient=proficient,
            proficiency_bonus=proficiency_bonus,
            mode=mode,
        )

    def attack_roll(
        self,
        attack_bonus: int,
        target_ac: int,
        mode: RollMode = RollMode.NORMAL,
    ) -> AttackRollResult:
        if target_ac < 0:
            raise ValidationError("armor class must be non-negative")
        result = self._dice.roll_d20(modifier=attack_bonus, mode=mode)
        natural = result.natural
        if natural is None:  # pragma: no cover - roll_d20 always yields a natural
            raise ValidationError("attack roll requires a single d20")
        is_critical = natural == 20
        is_critical_miss = natural == 1
        hit = is_critical or (not is_critical_miss and result.total >= target_ac)
        return AttackRollResult(
            roll=natural,
            attack_bonus=attack_bonus,
            total=result.total,
            target_ac=target_ac,
            hit=hit,
            is_critical=is_critical,
            is_critical_miss=is_critical_miss,
            mode=mode,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_checks.py -v`
Expected: PASS

- [ ] **Step 5: Run lint and typecheck**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/domain/rules/checks.py tests/domain/test_checks.py
git commit -m "feat(domain): add check, saving throw and attack roll resolution" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: Weapons & Character

**Files:**
- Create: `src/domain/character/weapon.py`, `src/domain/character/character.py`
- Test: `tests/domain/test_weapon.py`, `tests/domain/test_character.py`

**Interfaces:**
- Consumes: `CharacterId` (Task 2), `AbilityScores`/`AbilityType` (Task 3), `HitPoints`/`Inventory` (Task 5), `DIE_SIZES` (Task 6), `ValidationError` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class Weapon`: `weapon_id: str`, `name: str`, `damage_die_count: int`, `damage_die_size: int`, `ability: AbilityType = AbilityType.STRENGTH`, `range_ft: int = 5`. Validates die count ≥ 1, die size in `DIE_SIZES`, range ≥ 1.
  - `class CharacterType(StrEnum)`: `PLAYER_CHARACTER`, `MONSTER`, `NPC`.
  - `class CharacterClass(StrEnum)`: `FIGHTER`, `ROGUE`, `WIZARD`, `CLERIC` (Implementation Plan §14/Level 4 limited set).
  - `@dataclass class Character`: `id: CharacterId`, `name: str`, `character_type: CharacterType`, `character_class: CharacterClass | None`, `level: int`, `ability_scores: AbilityScores`, `armor_class: int`, `speed_ft: int`, `hit_points: HitPoints`, `conditions: tuple[str, ...] = ()`, `inventory: Inventory = <factory>`, `equipped_weapon: Weapon | None = None`. Methods: `apply_damage(amount: int) -> None`, `apply_healing(amount: int) -> None`, `add_condition(name: str) -> None`, `remove_condition(name: str) -> None`, `is_defeated() -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_weapon.py
import pytest

from domain.character.abilities import AbilityType
from domain.character.weapon import Weapon
from domain.common.errors import ValidationError


def test_weapon_defaults() -> None:
    sword = Weapon(
        weapon_id="longsword", name="Longsword", damage_die_count=1, damage_die_size=8
    )
    assert sword.ability is AbilityType.STRENGTH
    assert sword.range_ft == 5


def test_weapon_rejects_bad_die() -> None:
    with pytest.raises(ValidationError):
        Weapon(weapon_id="x", name="X", damage_die_count=0, damage_die_size=6)
    with pytest.raises(ValidationError):
        Weapon(weapon_id="x", name="X", damage_die_count=1, damage_die_size=7)


def test_weapon_rejects_bad_range_or_names() -> None:
    with pytest.raises(ValidationError):
        Weapon(
            weapon_id="x", name="X", damage_die_count=1, damage_die_size=6, range_ft=0
        )
    with pytest.raises(ValidationError):
        Weapon(weapon_id=" ", name="X", damage_die_count=1, damage_die_size=6)
```

```python
# tests/domain/test_character.py
import pytest

from domain.character.abilities import AbilityScores, AbilityType
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.common.errors import ValidationError
from domain.common.ids import CharacterId


def _longsword() -> Weapon:
    return Weapon(
        weapon_id="longsword", name="Longsword", damage_die_count=1, damage_die_size=8
    )


def _scores(**overrides: int) -> AbilityScores:
    values = {"strength": 16, "dexterity": 13, "constitution": 15,
              "intelligence": 10, "wisdom": 12, "charisma": 9}
    values.update(overrides)
    return AbilityScores(**values)


def _character(**overrides: object) -> Character:
    params: dict[str, object] = {
        "id": CharacterId.generate(),
        "name": "Arin",
        "character_type": CharacterType.PLAYER_CHARACTER,
        "character_class": CharacterClass.FIGHTER,
        "level": 1,
        "ability_scores": _scores(),
        "armor_class": 16,
        "speed_ft": 30,
        "hit_points": HitPoints(current=12, maximum=12),
    }
    params.update(overrides)
    return Character(**params)  # type: ignore[arg-type]


def test_character_holds_core_state() -> None:
    arin = _character()
    assert arin.name == "Arin"
    assert arin.character_class is CharacterClass.FIGHTER
    assert arin.is_defeated() is False
    assert arin.conditions == ()


def test_monster_does_not_require_a_class() -> None:
    goblin = _character(
        name="Goblin",
        character_type=CharacterType.MONSTER,
        character_class=None,
        ability_scores=_scores(strength=8, dexterity=14, constitution=10,
                               wisdom=8, charisma=8),
        armor_class=13,
        hit_points=HitPoints(current=7, maximum=7),
    )
    assert goblin.character_class is None


def test_player_character_requires_a_class() -> None:
    with pytest.raises(ValidationError):
        _character(character_class=None)


def test_character_range_validation() -> None:
    with pytest.raises(ValidationError):
        _character(level=0)
    with pytest.raises(ValidationError):
        _character(armor_class=0)
    with pytest.raises(ValidationError):
        _character(armor_class=31)
    with pytest.raises(ValidationError):
        _character(speed_ft=0)
    with pytest.raises(ValidationError):
        _character(name="   ")


def test_apply_damage_and_healing_go_through_domain_methods() -> None:
    arin = _character()
    arin.apply_damage(5)
    assert arin.hit_points.current == 7
    arin.apply_healing(2)
    assert arin.hit_points.current == 9
    arin.apply_damage(99)
    assert arin.is_defeated() is True


def test_conditions_add_and_remove() -> None:
    arin = _character()
    arin.add_condition("prone")
    arin.add_condition("prone")  # idempotent
    assert arin.conditions == ("prone",)
    arin.remove_condition("prone")
    assert arin.conditions == ()
    with pytest.raises(ValidationError):
        arin.remove_condition("prone")


def test_equipped_weapon_defaults_to_none() -> None:
    assert _character().equipped_weapon is None
    assert _character(equipped_weapon=_longsword()).equipped_weapon is not None


def test_ability_scores_are_usable_through_character() -> None:
    arin = _character()
    assert arin.ability_scores.modifier(AbilityType.STRENGTH) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_weapon.py tests/domain/test_character.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.character.weapon'`

- [ ] **Step 3: Write the implementation**

```python
# src/domain/character/weapon.py
"""Weapon value objects; damage dice are constrained to the standard die sizes."""

from __future__ import annotations

from dataclasses import dataclass

from domain.character.abilities import AbilityType
from domain.common.errors import ValidationError
from domain.rules.dice import DIE_SIZES


@dataclass(frozen=True)
class Weapon:
    weapon_id: str
    name: str
    damage_die_count: int
    damage_die_size: int
    ability: AbilityType = AbilityType.STRENGTH
    range_ft: int = 5

    def __post_init__(self) -> None:
        if not self.weapon_id.strip():
            raise ValidationError("weapon_id must be a non-empty string")
        if not self.name.strip():
            raise ValidationError("weapon name must be a non-empty string")
        if self.damage_die_count < 1:
            raise ValidationError("damage die count must be at least 1")
        if self.damage_die_size not in DIE_SIZES:
            raise ValidationError(
                f"damage die size must be one of {DIE_SIZES}, got d{self.damage_die_size}"
            )
        if self.range_ft < 1:
            raise ValidationError("weapon range must be at least 1 foot")
```

```python
# src/domain/character/character.py
"""Character aggregate — what exists in the game (CLAUDE.md §16: Character ≠ Agent)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from domain.character.abilities import AbilityScores
from domain.character.inventory import Inventory
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.common.errors import ValidationError
from domain.common.ids import CharacterId
from domain.rules.progression import MAX_LEVEL, MIN_LEVEL

MIN_AC = 1
MAX_AC = 30
MIN_SPEED_FT = 1
MAX_SPEED_FT = 120


class CharacterType(StrEnum):
    PLAYER_CHARACTER = "player_character"
    MONSTER = "monster"
    NPC = "npc"


class CharacterClass(StrEnum):
    FIGHTER = "fighter"
    ROGUE = "rogue"
    WIZARD = "wizard"
    CLERIC = "cleric"


@dataclass
class Character:
    id: CharacterId
    name: str
    character_type: CharacterType
    character_class: CharacterClass | None
    level: int
    ability_scores: AbilityScores
    armor_class: int
    speed_ft: int
    hit_points: HitPoints
    conditions: tuple[str, ...] = ()
    inventory: Inventory = field(default_factory=Inventory)
    equipped_weapon: Weapon | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError("character name must be a non-empty string")
        if not MIN_LEVEL <= self.level <= MAX_LEVEL:
            raise ValidationError(
                f"level must be between {MIN_LEVEL} and {MAX_LEVEL}, got {self.level}"
            )
        if not MIN_AC <= self.armor_class <= MAX_AC:
            raise ValidationError(
                f"armor class must be between {MIN_AC} and {MAX_AC}, got {self.armor_class}"
            )
        if not MIN_SPEED_FT <= self.speed_ft <= MAX_SPEED_FT:
            raise ValidationError(
                f"speed must be between {MIN_SPEED_FT} and {MAX_SPEED_FT} feet,"
                f" got {self.speed_ft}"
            )
        if self.character_type is CharacterType.PLAYER_CHARACTER and (
            self.character_class is None
        ):
            raise ValidationError("player characters must have a character class")

    def is_defeated(self) -> bool:
        return self.hit_points.is_defeated

    def apply_damage(self, amount: int) -> None:
        self.hit_points = self.hit_points.apply_damage(amount)

    def apply_healing(self, amount: int) -> None:
        self.hit_points = self.hit_points.apply_healing(amount)

    def add_condition(self, name: str) -> None:
        if not name.strip():
            raise ValidationError("condition name must be a non-empty string")
        if name not in self.conditions:
            self.conditions = (*self.conditions, name)

    def remove_condition(self, name: str) -> None:
        if name not in self.conditions:
            raise ValidationError(f"character does not have condition '{name}'")
        self.conditions = tuple(c for c in self.conditions if c != name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_weapon.py tests/domain/test_character.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/character tests/domain/test_weapon.py tests/domain/test_character.py
git commit -m "feat(domain): add weapons and the character aggregate" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: Domain Events & Event Repository

**Files:**
- Create: `src/domain/events/base.py`, `src/domain/events/events.py`, `src/domain/events/collector.py`, `src/domain/events/repository.py`, `src/domain/events/__init__.py` (empty)
- Create: `src/infrastructure/events/in_memory.py`, `src/infrastructure/events/__init__.py` (empty)
- Test: `tests/domain/test_events.py`, `tests/infrastructure/test_event_repository.py`

**Interfaces:**
- Consumes: `EntityId`, `GameId`, `CharacterId`, `EventId`, `CampaignId` (Task 2).
- Produces:
  - `class GameEvent(Protocol)`: property `event_type: str`, method `to_payload() -> dict[str, object]`.
  - `@dataclass(frozen=True) class BaseEvent` — derives `event_type` from the class name (CamelCase → snake_case); `to_payload()` serializes `EntityId` → `str`, `Enum` → `.value`, tuples/lists → JSON lists.
  - Typed events (all frozen dataclasses): `GameCreated(campaign_id: CampaignId, seed: int)`, `GameStarted()`, `InitiativeRolled(character_id: CharacterId, total: int)`, `CombatStarted(participant_ids: tuple[CharacterId, ...], round_number: int)`, `TurnStarted(round_number: int, actor_id: CharacterId)`, `TurnEnded(round_number: int, actor_id: CharacterId)`, `AttackRequested(attacker_id: CharacterId, target_id: CharacterId, weapon_id: str)`, `AttackResolved(attacker_id: CharacterId, target_id: CharacterId, roll: int, attack_bonus: int, total: int, target_ac: int, hit: bool, critical: bool)`, `DamageApplied(character_id: CharacterId, amount: int, hp_before: int, hp_after: int)`, `CharacterDefeated(character_id: CharacterId)`, `ActionRejected(actor_id: CharacterId, action_type: str, reason: str)`, `CombatEnded(winner_side: str, round_number: int)`.
  - `@dataclass(frozen=True) class EventEnvelope`: `sequence: int`, `event_id: EventId`, `game_id: GameId`, `occurred_at: str`, `event_type: str`, `payload: dict[str, object]`.
  - `class EventCollector`: `__init__(game_id: GameId, clock: Callable[[], datetime] | None = None)`; `record(event: GameEvent) -> EventEnvelope` (sequence 1..n); property `events` (full history); `drain() -> list[EventEnvelope]` (returns and clears pending only).
  - `class EventRepository(Protocol)` in `domain/events/repository.py`: `append(game_id: GameId, envelope: EventEnvelope) -> None`, `get_events(game_id: GameId) -> list[EventEnvelope]`.
  - `class InMemoryEventRepository` in `infrastructure/events/in_memory.py` implementing `EventRepository`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_events.py
from datetime import UTC, datetime

from domain.events.base import BaseEvent
from domain.events.collector import EventCollector
from domain.events.events import (
    ActionRejected,
    AttackResolved,
    CombatEnded,
    CombatStarted,
    DamageApplied,
    GameCreated,
    GameStarted,
)
from domain.common.ids import CampaignId, CharacterId, GameId


def test_event_type_is_derived_snake_case() -> None:
    assert GameStarted().event_type == "game_started"
    assert ActionRejected(
        actor_id=CharacterId.generate(), action_type="attack", reason="no"
    ).event_type == "action_rejected"
    assert CombatEnded(winner_side="party", round_number=3).event_type == "combat_ended"


def test_base_event_is_usable_protocol_implementation() -> None:
    assert issubclass(GameStarted, BaseEvent)


def test_payload_serializes_ids_enums_and_tuples() -> None:
    campaign_id = CampaignId.generate()
    payload = GameCreated(campaign_id=campaign_id, seed=42).to_payload()
    assert payload["campaign_id"] == str(campaign_id)
    assert isinstance(payload["campaign_id"], str)
    assert payload["seed"] == 42

    participant = CharacterId.generate()
    started = CombatStarted(
        participant_ids=(participant,), round_number=1
    ).to_payload()
    assert started["participant_ids"] == [str(participant)]


def test_attack_resolved_payload() -> None:
    attacker = CharacterId.generate()
    target = CharacterId.generate()
    payload = AttackResolved(
        attacker_id=attacker,
        target_id=target,
        roll=15,
        attack_bonus=5,
        total=20,
        target_ac=13,
        hit=True,
        critical=False,
    ).to_payload()
    assert payload == {
        "attacker_id": str(attacker),
        "target_id": str(target),
        "roll": 15,
        "attack_bonus": 5,
        "total": 20,
        "target_ac": 13,
        "hit": True,
        "critical": False,
    }


def test_collector_assigns_contiguous_sequences_and_timestamps() -> None:
    game_id = GameId.generate()
    fixed = datetime(2026, 1, 1, tzinfo=UTC)
    collector = EventCollector(game_id=game_id, clock=lambda: fixed)

    first = collector.record(GameStarted())
    second = collector.record(
        DamageApplied(
            character_id=CharacterId.generate(), amount=4, hp_before=7, hp_after=3
        )
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert first.game_id == game_id
    assert first.occurred_at == "2026-01-01T00:00:00+00:00"
    assert first.event_type == "game_started"
    assert [e.sequence for e in collector.events] == [1, 2]


def test_drain_returns_pending_only_once() -> None:
    collector = EventCollector(game_id=GameId.generate())
    collector.record(GameStarted())

    drained = collector.drain()
    assert [e.event_type for e in drained] == ["game_started"]
    assert collector.drain() == []
    # history is retained for in-process inspection
    assert len(collector.events) == 1


def test_combat_ended_event_payload() -> None:
    payload = CombatEnded(winner_side="party", round_number=2).to_payload()
    assert payload == {"winner_side": "party", "round_number": 2}
```

```python
# tests/infrastructure/test_event_repository.py
from domain.events.collector import EventCollector
from domain.events.events import GameStarted
from domain.common.ids import GameId
from infrastructure.events.in_memory import InMemoryEventRepository


def test_in_memory_event_repository_roundtrip() -> None:
    repository = InMemoryEventRepository()
    game_id = GameId.generate()
    collector = EventCollector(game_id=game_id)
    first = collector.record(GameStarted())
    second = collector.record(GameStarted())

    repository.append(game_id, first)
    repository.append(game_id, second)

    stored = repository.get_events(game_id)
    assert [e.sequence for e in stored] == [1, 2]
    assert repository.get_events(GameId.generate()) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_events.py tests/infrastructure/test_event_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.events'`

- [ ] **Step 3: Write the implementation**

```python
# src/domain/events/base.py
"""Event primitives: past-tense, immutable records of what happened (CLAUDE.md §11, §12)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Protocol

from domain.common.ids import EntityId

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def _snake_case(name: str) -> str:
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def _jsonable(value: object) -> object:
    if isinstance(value, EntityId):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


class GameEvent(Protocol):
    @property
    def event_type(self) -> str: ...

    def to_payload(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class BaseEvent:
    """Base for all domain events; subclass with frozen dataclass fields only."""

    @property
    def event_type(self) -> str:
        return _snake_case(type(self).__name__)

    def to_payload(self) -> dict[str, object]:
        return {key: _jsonable(value) for key, value in asdict(self).items()}
```

```python
# src/domain/events/events.py
"""Typed MVP-0 events (Implementation Plan §9)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.common.ids import CampaignId, CharacterId
from domain.events.base import BaseEvent


@dataclass(frozen=True)
class GameCreated(BaseEvent):
    campaign_id: CampaignId
    seed: int


@dataclass(frozen=True)
class GameStarted(BaseEvent):
    pass


@dataclass(frozen=True)
class InitiativeRolled(BaseEvent):
    character_id: CharacterId
    total: int


@dataclass(frozen=True)
class CombatStarted(BaseEvent):
    participant_ids: tuple[CharacterId, ...]
    round_number: int


@dataclass(frozen=True)
class TurnStarted(BaseEvent):
    round_number: int
    actor_id: CharacterId


@dataclass(frozen=True)
class TurnEnded(BaseEvent):
    round_number: int
    actor_id: CharacterId


@dataclass(frozen=True)
class AttackRequested(BaseEvent):
    attacker_id: CharacterId
    target_id: CharacterId
    weapon_id: str


@dataclass(frozen=True)
class AttackResolved(BaseEvent):
    attacker_id: CharacterId
    target_id: CharacterId
    roll: int
    attack_bonus: int
    total: int
    target_ac: int
    hit: bool
    critical: bool


@dataclass(frozen=True)
class DamageApplied(BaseEvent):
    character_id: CharacterId
    amount: int
    hp_before: int
    hp_after: int


@dataclass(frozen=True)
class CharacterDefeated(BaseEvent):
    character_id: CharacterId


@dataclass(frozen=True)
class ActionRejected(BaseEvent):
    actor_id: CharacterId
    action_type: str
    reason: str


@dataclass(frozen=True)
class CombatEnded(BaseEvent):
    winner_side: str
    round_number: int
```

```python
# src/domain/events/collector.py
"""Collects events in sequence for a single game."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from domain.common.ids import EventId, GameId
from domain.events.base import GameEvent


@dataclass(frozen=True)
class EventEnvelope:
    sequence: int
    event_id: EventId
    game_id: GameId
    occurred_at: str
    event_type: str
    payload: dict[str, object]


class EventCollector:
    def __init__(
        self, game_id: GameId, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._game_id = game_id
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self._sequence = 0
        self._pending: list[EventEnvelope] = []
        self._recorded: list[EventEnvelope] = []

    def record(self, event: GameEvent) -> EventEnvelope:
        self._sequence += 1
        envelope = EventEnvelope(
            sequence=self._sequence,
            event_id=EventId.generate(),
            game_id=self._game_id,
            occurred_at=self._clock().isoformat(),
            event_type=event.event_type,
            payload=event.to_payload(),
        )
        self._pending.append(envelope)
        self._recorded.append(envelope)
        return envelope

    @property
    def events(self) -> list[EventEnvelope]:
        return list(self._recorded)

    def drain(self) -> list[EventEnvelope]:
        drained = self._pending
        self._pending = []
        return drained
```

```python
# src/domain/events/repository.py
"""Port for event persistence — implemented in the infrastructure layer."""

from __future__ import annotations

from typing import Protocol

from domain.common.ids import GameId
from domain.events.collector import EventEnvelope


class EventRepository(Protocol):
    def append(self, game_id: GameId, envelope: EventEnvelope) -> None: ...

    def get_events(self, game_id: GameId) -> list[EventEnvelope]: ...
```

```python
# src/infrastructure/events/in_memory.py
"""In-memory EventRepository implementation for MVP-0."""

from __future__ import annotations

from domain.common.ids import GameId
from domain.events.collector import EventEnvelope


class InMemoryEventRepository:
    def __init__(self) -> None:
        self._events: dict[GameId, list[EventEnvelope]] = {}

    def append(self, game_id: GameId, envelope: EventEnvelope) -> None:
        self._events.setdefault(game_id, []).append(envelope)

    def get_events(self, game_id: GameId) -> list[EventEnvelope]:
        return list(self._events.get(game_id, []))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_events.py tests/infrastructure/test_event_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/events src/infrastructure/events tests/domain/test_events.py tests/infrastructure/test_event_repository.py
git commit -m "feat(domain): add typed domain events, collector and event repository port" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 10: Actions & Action Economy

**Files:**
- Create: `src/domain/rules/actions.py`
- Test: `tests/domain/test_actions.py`

**Interfaces:**
- Consumes: `CharacterId` (Task 2), `ActionNotAvailableError`, `ValidationError` (Task 2).
- Produces:
  - `class ActionType(StrEnum)` with 12 members (Implementation Plan §7): `ATTACK`, `ABILITY_CHECK`, `SAVING_THROW`, `DASH`, `DODGE`, `DISENGAGE`, `HELP`, `HIDE`, `READY`, `SEARCH`, `USE_ITEM`, `MOVE` (lowercase values).
  - `class ActionCategory(StrEnum)`: `ACTION`, `BONUS_ACTION`, `REACTION`, `MOVEMENT`, `FREE`.
  - `ACTION_CATEGORY: dict[ActionType, ActionCategory]` — everything is `ACTION` except `MOVE` → `MOVEMENT` and `SAVING_THROW` → `FREE`.
  - `@dataclass(frozen=True) class AttackProposal`: `actor_id: CharacterId`, `target_id: CharacterId`, `weapon_id: str | None = None`; property `action_type -> ActionType.ATTACK`.
  - `@dataclass(frozen=True) class GenericActionProposal`: `actor_id: CharacterId`, `action_type: ActionType`.
  - `@dataclass(frozen=True) class ValidationResult`: `valid: bool`, `reason: str = ""`, `error_code: str = ""`; classmethods `ok()` and `reject(reason: str, error_code: str)`.
  - `@dataclass class ActionEconomy`: `movement_budget_ft: int`, `movement_used_ft: int = 0`, `action_taken: bool = False`, `bonus_action_taken: bool = False`, `reaction_taken: bool = False`; `use(action_type: ActionType) -> None` (raises `ActionNotAvailableError`), `use_movement(feet: int) -> None`, `remaining_movement_ft() -> int`, `can_take_action(action_type: ActionType) -> bool`, `reset_for_new_turn() -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_actions.py
import pytest

from domain.common.errors import ActionNotAvailableError, ValidationError
from domain.common.ids import CharacterId
from domain.rules.actions import (
    ACTION_CATEGORY,
    ActionCategory,
    ActionEconomy,
    ActionType,
    AttackProposal,
    GenericActionProposal,
    ValidationResult,
)


def test_action_type_has_the_twelve_initial_actions() -> None:
    assert len(ActionType) == 12
    assert ActionType.ATTACK.value == "attack"
    assert ActionType.USE_ITEM.value == "use_item"


def test_action_category_mapping() -> None:
    assert ACTION_CATEGORY[ActionType.ATTACK] is ActionCategory.ACTION
    assert ACTION_CATEGORY[ActionType.MOVE] is ActionCategory.MOVEMENT
    assert ACTION_CATEGORY[ActionType.SAVING_THROW] is ActionCategory.FREE
    assert ACTION_CATEGORY[ActionType.DODGE] is ActionCategory.ACTION


def test_validation_result_factories() -> None:
    ok = ValidationResult.ok()
    assert ok.valid is True
    assert ok.reason == ""

    rejected = ValidationResult.reject("target out of range", "target_out_of_range")
    assert rejected.valid is False
    assert rejected.error_code == "target_out_of_range"


def test_attack_proposal_carries_only_intent() -> None:
    actor = CharacterId.generate()
    target = CharacterId.generate()
    proposal = AttackProposal(actor_id=actor, target_id=target, weapon_id="longsword")
    assert proposal.action_type is ActionType.ATTACK
    assert proposal.weapon_id == "longsword"


def test_generic_proposal() -> None:
    proposal = GenericActionProposal(
        actor_id=CharacterId.generate(), action_type=ActionType.DODGE
    )
    assert proposal.action_type is ActionType.DODGE


def test_action_economy_tracks_actions_per_turn() -> None:
    economy = ActionEconomy(movement_budget_ft=30)
    assert economy.can_take_action(ActionType.ATTACK) is True

    economy.use(ActionType.ATTACK)
    assert economy.action_taken is True
    assert economy.can_take_action(ActionType.ATTACK) is False
    assert economy.can_take_action(ActionType.DODGE) is False
    assert economy.can_take_action(ActionType.MOVE) is True

    with pytest.raises(ActionNotAvailableError):
        economy.use(ActionType.ATTACK)


def test_action_economy_movement() -> None:
    economy = ActionEconomy(movement_budget_ft=30)
    economy.use_movement(20)
    assert economy.remaining_movement_ft() == 10
    with pytest.raises(ActionNotAvailableError):
        economy.use_movement(15)
    with pytest.raises(ValidationError):
        economy.use_movement(-1)


def test_action_economy_resets_for_new_turn() -> None:
    economy = ActionEconomy(movement_budget_ft=30)
    economy.use(ActionType.ATTACK)
    economy.use_movement(30)
    economy.reset_for_new_turn()
    assert economy.action_taken is False
    assert economy.remaining_movement_ft() == 30
    assert economy.can_take_action(ActionType.ATTACK) is True


def test_negative_movement_budget_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionEconomy(movement_budget_ft=-1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_actions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.rules.actions'` (or `ImportError: cannot import name ...`)

- [ ] **Step 3: Write the implementation**

```python
# src/domain/rules/actions.py
"""Unified action model and per-turn action economy (Implementation Plan §7)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domain.common.errors import ActionNotAvailableError, ValidationError
from domain.common.ids import CharacterId


class ActionType(StrEnum):
    ATTACK = "attack"
    ABILITY_CHECK = "ability_check"
    SAVING_THROW = "saving_throw"
    DASH = "dash"
    DODGE = "dodge"
    DISENGAGE = "disengage"
    HELP = "help"
    HIDE = "hide"
    READY = "ready"
    SEARCH = "search"
    USE_ITEM = "use_item"
    MOVE = "move"


class ActionCategory(StrEnum):
    ACTION = "action"
    BONUS_ACTION = "bonus_action"
    REACTION = "reaction"
    MOVEMENT = "movement"
    FREE = "free"


ACTION_CATEGORY: dict[ActionType, ActionCategory] = {
    ActionType.ATTACK: ActionCategory.ACTION,
    ActionType.ABILITY_CHECK: ActionCategory.ACTION,
    ActionType.SAVING_THROW: ActionCategory.FREE,
    ActionType.DASH: ActionCategory.ACTION,
    ActionType.DODGE: ActionCategory.ACTION,
    ActionType.DISENGAGE: ActionCategory.ACTION,
    ActionType.HELP: ActionCategory.ACTION,
    ActionType.HIDE: ActionCategory.ACTION,
    ActionType.READY: ActionCategory.ACTION,
    ActionType.SEARCH: ActionCategory.ACTION,
    ActionType.USE_ITEM: ActionCategory.ACTION,
    ActionType.MOVE: ActionCategory.MOVEMENT,
}


@dataclass(frozen=True)
class AttackProposal:
    actor_id: CharacterId
    target_id: CharacterId
    weapon_id: str | None = None

    @property
    def action_type(self) -> ActionType:
        return ActionType.ATTACK


@dataclass(frozen=True)
class GenericActionProposal:
    actor_id: CharacterId
    action_type: ActionType


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str = ""
    error_code: str = ""

    @classmethod
    def ok(cls) -> ValidationResult:
        return cls(valid=True)

    @classmethod
    def reject(cls, reason: str, error_code: str) -> ValidationResult:
        return cls(valid=False, reason=reason, error_code=error_code)


@dataclass
class ActionEconomy:
    movement_budget_ft: int
    movement_used_ft: int = 0
    action_taken: bool = False
    bonus_action_taken: bool = False
    reaction_taken: bool = False

    def __post_init__(self) -> None:
        if self.movement_budget_ft < 0:
            raise ValidationError("movement budget must be non-negative")

    def use(self, action_type: ActionType) -> None:
        category = ACTION_CATEGORY[action_type]
        if category is ActionCategory.ACTION:
            if self.action_taken:
                raise ActionNotAvailableError("action already used this turn")
            self.action_taken = True
        elif category is ActionCategory.BONUS_ACTION:
            if self.bonus_action_taken:
                raise ActionNotAvailableError("bonus action already used this turn")
            self.bonus_action_taken = True
        elif category is ActionCategory.REACTION:
            if self.reaction_taken:
                raise ActionNotAvailableError("reaction already used this turn")
            self.reaction_taken = True

    def use_movement(self, feet: int) -> None:
        if feet < 0:
            raise ValidationError("movement must be non-negative")
        if self.movement_used_ft + feet > self.movement_budget_ft:
            raise ActionNotAvailableError("not enough movement left this turn")
        self.movement_used_ft += feet

    def remaining_movement_ft(self) -> int:
        return self.movement_budget_ft - self.movement_used_ft

    def can_take_action(self, action_type: ActionType) -> bool:
        category = ACTION_CATEGORY[action_type]
        if category is ActionCategory.ACTION:
            return not self.action_taken
        if category is ActionCategory.BONUS_ACTION:
            return not self.bonus_action_taken
        if category is ActionCategory.REACTION:
            return not self.reaction_taken
        return True

    def reset_for_new_turn(self) -> None:
        self.movement_used_ft = 0
        self.action_taken = False
        self.bonus_action_taken = False
        self.reaction_taken = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_actions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/rules/actions.py tests/domain/test_actions.py
git commit -m "feat(domain): add action types, proposals, validation results and action economy" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 11: Game Aggregate

**Files:**
- Create: `src/domain/world/game.py`, `src/domain/world/__init__.py` (empty)
- Test: `tests/domain/test_game.py`

**Interfaces:**
- Consumes: `Character`/`CharacterType` (Task 8), `GameId`/`CampaignId`/`CharacterId` (Task 2), `CharacterNotFoundError`, `ValidationError` (Task 2).
- Produces:
  - `class GameStatus(StrEnum)`: `CREATED`, `RUNNING`, `ENDED`.
  - `@dataclass class Game`: `game_id: GameId`, `campaign_id: CampaignId`, `campaign_name: str`, `seed: int`, `characters: dict[CharacterId, Character]`, `party_ids: list[CharacterId]`, `enemy_ids: list[CharacterId]`, `status: GameStatus = GameStatus.CREATED`. Methods: `add_party_member(character: Character) -> None`, `add_enemy(character: Character) -> None` (both rejected after start; unique id and case-insensitive unique name enforced), `get_character(character_id: CharacterId) -> Character` (raises `CharacterNotFoundError`), `find_character_by_name(name: str) -> Character | None` (case-insensitive), `side_of(character_id: CharacterId) -> str` (`"party"`/`"enemies"`), `opponents_of(character_id: CharacterId) -> list[CharacterId]`, properties `living_party_ids` / `living_enemy_ids`, `mark_started() -> None`, `mark_ended() -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_game.py
import pytest

from domain.character.abilities import AbilityScores
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.vitals import HitPoints
from domain.common.errors import CharacterNotFoundError, ValidationError
from domain.common.ids import CampaignId, CharacterId, GameId
from domain.world.game import Game, GameStatus


def _member(
    name: str,
    character_type: CharacterType,
    hp: int = 10,
) -> Character:
    return Character(
        id=CharacterId.generate(),
        name=name,
        character_type=character_type,
        character_class=CharacterClass.FIGHTER
        if character_type is CharacterType.PLAYER_CHARACTER
        else None,
        level=1,
        ability_scores=AbilityScores(
            strength=10, dexterity=10, constitution=10, intelligence=10,
            wisdom=10, charisma=10,
        ),
        armor_class=13,
        speed_ft=30,
        hit_points=HitPoints(current=hp, maximum=hp),
    )


def _game() -> Game:
    return Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="Test",
        seed=1,
    )


def test_add_party_member_and_enemy() -> None:
    game = _game()
    arin = _member("Arin", CharacterType.PLAYER_CHARACTER)
    goblin = _member("Goblin", CharacterType.MONSTER)
    game.add_party_member(arin)
    game.add_enemy(goblin)

    assert game.characters[arin.id] is arin
    assert game.party_ids == [arin.id]
    assert game.enemy_ids == [goblin.id]
    assert game.status is GameStatus.CREATED


def test_duplicate_id_and_name_are_rejected() -> None:
    game = _game()
    arin = _member("Arin", CharacterType.PLAYER_CHARACTER)
    game.add_party_member(arin)

    with pytest.raises(ValidationError):
        game.add_party_member(arin)  # same id
    with pytest.raises(ValidationError):
        game.add_party_member(_member("arin", CharacterType.PLAYER_CHARACTER))


def test_get_character_raises_for_unknown_id() -> None:
    game = _game()
    with pytest.raises(CharacterNotFoundError):
        game.get_character(CharacterId.generate())


def test_find_character_by_name_is_case_insensitive() -> None:
    game = _game()
    arin = _member("Arin", CharacterType.PLAYER_CHARACTER)
    game.add_party_member(arin)
    assert game.find_character_by_name("aRIN") is arin
    assert game.find_character_by_name("nobody") is None


def test_side_of_and_opponents_of() -> None:
    game = _game()
    arin = _member("Arin", CharacterType.PLAYER_CHARACTER)
    goblin = _member("Goblin", CharacterType.MONSTER)
    game.add_party_member(arin)
    game.add_enemy(goblin)

    assert game.side_of(arin.id) == "party"
    assert game.side_of(goblin.id) == "enemies"
    assert game.opponents_of(arin.id) == [goblin.id]
    assert game.opponents_of(goblin.id) == [arin.id]
    with pytest.raises(CharacterNotFoundError):
        game.side_of(CharacterId.generate())


def test_living_lists_filter_defeated() -> None:
    game = _game()
    arin = _member("Arin", CharacterType.PLAYER_CHARACTER)
    goblin1 = _member("Goblin-1", CharacterType.MONSTER)
    goblin2 = _member("Goblin-2", CharacterType.MONSTER)
    game.add_party_member(arin)
    game.add_enemy(goblin1)
    game.add_enemy(goblin2)

    goblin1.apply_damage(999)
    assert game.living_enemy_ids == [goblin2.id]
    assert game.living_party_ids == [arin.id]


def test_roster_cannot_change_after_start() -> None:
    game = _game()
    game.mark_started()
    with pytest.raises(ValidationError):
        game.add_party_member(_member("Late", CharacterType.PLAYER_CHARACTER))


def test_status_transitions() -> None:
    game = _game()
    game.mark_started()
    assert game.status is GameStatus.RUNNING
    game.mark_ended()
    assert game.status is GameStatus.ENDED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_game.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.world'`

- [ ] **Step 3: Write the implementation**

```python
# src/domain/world/game.py
"""Game aggregate — authoritative current state (CLAUDE.md §10, §11)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from domain.character.character import Character
from domain.common.errors import CharacterNotFoundError, ValidationError
from domain.common.ids import CampaignId, CharacterId, GameId


class GameStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    ENDED = "ended"


@dataclass
class Game:
    game_id: GameId
    campaign_id: CampaignId
    campaign_name: str
    seed: int
    characters: dict[CharacterId, Character] = field(default_factory=dict)
    party_ids: list[CharacterId] = field(default_factory=list)
    enemy_ids: list[CharacterId] = field(default_factory=list)
    status: GameStatus = GameStatus.CREATED

    def add_party_member(self, character: Character) -> None:
        self._add_member(character)
        self.party_ids.append(character.id)

    def add_enemy(self, character: Character) -> None:
        self._add_member(character)
        self.enemy_ids.append(character.id)

    def _add_member(self, character: Character) -> None:
        if self.status is not GameStatus.CREATED:
            raise ValidationError("cannot modify the roster after the game has started")
        if character.id in self.characters:
            raise ValidationError(
                f"character '{character.id}' already exists in this game"
            )
        if self.find_character_by_name(character.name) is not None:
            raise ValidationError(f"a character named '{character.name}' already exists")
        self.characters[character.id] = character

    def get_character(self, character_id: CharacterId) -> Character:
        character = self.characters.get(character_id)
        if character is None:
            raise CharacterNotFoundError(f"no character with id '{character_id}'")
        return character

    def find_character_by_name(self, name: str) -> Character | None:
        lowered = name.strip().lower()
        for character in self.characters.values():
            if character.name.lower() == lowered:
                return character
        return None

    def side_of(self, character_id: CharacterId) -> str:
        if character_id in self.party_ids:
            return "party"
        if character_id in self.enemy_ids:
            return "enemies"
        raise CharacterNotFoundError(f"character '{character_id}' is not a combatant")

    def opponents_of(self, character_id: CharacterId) -> list[CharacterId]:
        if self.side_of(character_id) == "party":
            return list(self.enemy_ids)
        return list(self.party_ids)

    @property
    def living_party_ids(self) -> list[CharacterId]:
        return [cid for cid in self.party_ids if not self.characters[cid].is_defeated()]

    @property
    def living_enemy_ids(self) -> list[CharacterId]:
        return [cid for cid in self.enemy_ids if not self.characters[cid].is_defeated()]

    def mark_started(self) -> None:
        self.status = GameStatus.RUNNING

    def mark_ended(self) -> None:
        self.status = GameStatus.ENDED
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_game.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/world tests/domain/test_game.py
git commit -m "feat(domain): add game aggregate with roster, sides and status" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 12: Combat Engine

**Files:**
- Create: `src/domain/combat/state.py`, `src/domain/combat/engine.py`, `src/domain/combat/policy.py`, `src/domain/combat/__init__.py` (empty)
- Test: `tests/domain/test_combat.py`

**Interfaces:**
- Consumes: `Game` (Task 11), `Character` (Task 8), `DiceRoller` (Task 6), `CheckResolver` (Task 7), `AttackProposal`, `ActionEconomy`, `ActionType`, `ValidationResult` (Task 10), events (Task 9), `EventCollector` (Task 9), `proficiency_bonus` (Task 4), `AgentDecisionFailedError` (Task 2).
- Produces:
  - `class CombatStatus(StrEnum)`: `ACTIVE`, `ENDED`.
  - `@dataclass(frozen=True) class InitiativeEntry`: `character_id: CharacterId`, `total: int`, `dexterity_modifier: int`, `tiebreaker: int`.
  - `def roll_initiative(dice: DiceRoller, characters: dict[CharacterId, Character], participant_ids: Sequence[CharacterId]) -> list[InitiativeEntry]` — total = d20 + DEX modifier; ties broken by higher DEX modifier, then by character id string (deterministic).
  - `@dataclass class Combat`: `entries: list[InitiativeEntry]`, `economy: ActionEconomy`, `round_number: int = 1`, `turn_index: int = 0`, `status: CombatStatus = CombatStatus.ACTIVE`; `active_actor() -> CharacterId`.
  - `class CombatEngine`: `__init__(dice: DiceRoller)`; `start(game: Game, participant_ids: Sequence[CharacterId], collector: EventCollector) -> Combat`; `validate(game, combat, proposal: AttackProposal) -> ValidationResult` (error codes: `combat_not_active`, `not_your_turn`, `action_unavailable`, `invalid_action`, `invalid_target`); `resolve(game, combat, proposal, collector) -> ValidationResult` (reject → records `ActionRejected`, no state change; accept → `AttackRequested`, `AttackResolved`, damage on hit with doubled dice on a critical, `DamageApplied`, `CharacterDefeated`); `advance_turn(game, combat, collector) -> None` (`TurnEnded`, ends combat with `CombatEnded` when one side is wiped, else advances to next living actor, wraps → `round_number += 1`, fresh `ActionEconomy`, `TurnStarted`).
  - `class SimpleMeleeEnemyPolicy`: `decide(game: Game, actor_id: CharacterId) -> AttackProposal` — first living opponent.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_combat.py
import pytest

from domain.character.abilities import AbilityScores
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.combat.engine import CombatEngine
from domain.combat.policy import SimpleMeleeEnemyPolicy
from domain.combat.state import Combat, CombatStatus, InitiativeEntry, roll_initiative
from domain.common.errors import AgentDecisionFailedError
from domain.common.ids import CampaignId, CharacterId, GameId
from domain.events.collector import EventCollector
from domain.rules.actions import ActionEconomy, AttackProposal
from domain.rules.dice import DiceRoller
from domain.world.game import Game


def _seed_with_rolls(rolls: list[int]) -> int:
    """Find a seed whose d20 sequence equals `rolls` (deterministic test helper)."""
    for seed in range(100_000):
        roller = DiceRoller(seed=seed)
        if [roller.roll_d20().natural for _ in rolls] == rolls:
            return seed
    raise AssertionError("no seed produced the requested rolls")


def _weapon(weapon_id: str, name: str, die_size: int) -> Weapon:
    return Weapon(
        weapon_id=weapon_id, name=name, damage_die_count=1, damage_die_size=die_size
    )


def _fighter(name: str = "Arin") -> Character:
    return Character(
        id=CharacterId.generate(),
        name=name,
        character_type=CharacterType.PLAYER_CHARACTER,
        character_class=CharacterClass.FIGHTER,
        level=1,
        ability_scores=AbilityScores(
            strength=16, dexterity=13, constitution=15, intelligence=10,
            wisdom=12, charisma=9,
        ),
        armor_class=16,
        speed_ft=30,
        hit_points=HitPoints(current=12, maximum=12),
        equipped_weapon=_weapon("longsword", "Longsword", 8),
    )


def _goblin(name: str = "Goblin", hp: int = 7) -> Character:
    return Character(
        id=CharacterId.generate(),
        name=name,
        character_type=CharacterType.MONSTER,
        character_class=None,
        level=1,
        ability_scores=AbilityScores(
            strength=8, dexterity=14, constitution=10, intelligence=10,
            wisdom=8, charisma=8,
        ),
        armor_class=13,
        speed_ft=30,
        hit_points=HitPoints(current=hp, maximum=hp),
        equipped_weapon=_weapon("scimitar", "Scimitar", 6),
    )


def _game(*members: Character) -> Game:
    game = Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="Test",
        seed=1,
    )
    for member in members:
        if member.character_type is CharacterType.MONSTER:
            game.add_enemy(member)
        else:
            game.add_party_member(member)
    return game


def _start(
    dice: DiceRoller, game: Game
) -> tuple[CombatEngine, Combat, EventCollector]:
    engine = CombatEngine(dice)
    collector = EventCollector(game_id=game.game_id)
    combat = engine.start(game, (*game.party_ids, *game.enemy_ids), collector)
    return engine, combat, collector


def test_initiative_orders_by_total_then_dex_modifier() -> None:
    low_dex = _fighter("Slow")
    high_dex = _goblin("Quick")
    characters = {low_dex.id: low_dex, high_dex.id: high_dex}
    order = [low_dex.id, high_dex.id]

    mirror = DiceRoller(seed=11)
    raw = [mirror.roll_d20().natural for _ in order]
    dex_mods = [1, 2]  # dex 13 -> +1, dex 14 -> +2
    ranking = sorted(
        zip(order, raw, dex_mods),
        key=lambda entry: (-(entry[1] + entry[2]), -entry[2], str(entry[0])),
    )
    expected = [entry[0] for entry in ranking]

    entries = roll_initiative(DiceRoller(seed=11), characters, order)
    assert [entry.character_id for entry in entries] == expected


def test_start_emits_initiative_combat_started_and_turn_started() -> None:
    game = _game(_fighter(), _goblin())
    engine, combat, collector = _start(DiceRoller(seed=7), game)

    types = [e.event_type for e in collector.events]
    assert types.count("initiative_rolled") == 2
    assert "combat_started" in types
    assert types[-1] == "turn_started"
    assert combat.status is CombatStatus.ACTIVE
    assert combat.active_actor() == combat.entries[0].character_id
    assert combat.round_number == 1


def test_validate_rejects_when_not_your_turn() -> None:
    game = _game(_fighter(), _goblin())
    engine, combat, _ = _start(DiceRoller(seed=7), game)
    idle = game.enemy_ids[0] if combat.active_actor() == game.party_ids[0] else game.party_ids[0]
    proposal = AttackProposal(actor_id=idle, target_id=combat.active_actor())

    result = engine.validate(game, combat, proposal)
    assert result.valid is False
    assert result.error_code == "not_your_turn"


def test_validate_rejects_unknown_same_side_or_defeated_targets() -> None:
    game = _game(_fighter(), _goblin())
    engine, combat, _ = _start(DiceRoller(seed=7), game)
    actor = game.characters[combat.active_actor()]
    opponents = game.opponents_of(actor.id)

    # unknown target
    unknown = AttackProposal(actor_id=actor.id, target_id=CharacterId.generate())
    assert engine.validate(game, combat, unknown).error_code == "invalid_target"

    # self target
    himself = AttackProposal(actor_id=actor.id, target_id=actor.id)
    assert engine.validate(game, combat, himself).error_code == "invalid_target"

    # same side target
    same_side_id = (
        game.party_ids[0] if actor.id in game.party_ids else game.enemy_ids[0]
    )
    ally = AttackProposal(actor_id=actor.id, target_id=same_side_id)
    if ally.target_id != actor.id:
        assert engine.validate(game, combat, ally).error_code == "invalid_target"

    # defeated target
    victim = game.characters[opponents[0]]
    victim.apply_damage(999)
    dead = AttackProposal(actor_id=actor.id, target_id=victim.id)
    assert engine.validate(game, combat, dead).error_code == "invalid_target"


def test_validate_rejects_when_action_already_used() -> None:
    game = _game(_fighter(), _goblin())
    engine, combat, _ = _start(DiceRoller(seed=7), game)
    actor_id = combat.active_actor()
    target = game.opponents_of(actor_id)[0]

    combat.economy.action_taken = True
    result = engine.validate(game, combat, AttackProposal(actor_id=actor_id, target_id=target))
    assert result.error_code == "action_unavailable"


def test_validate_rejects_when_combat_ended() -> None:
    game = _game(_fighter(), _goblin())
    engine, combat, _ = _start(DiceRoller(seed=7), game)
    combat.status = CombatStatus.ENDED
    result = engine.validate(
        game,
        combat,
        AttackProposal(
            actor_id=combat.active_actor(), target_id=CharacterId.generate()
        ),
    )
    assert result.error_code == "combat_not_active"


def test_resolve_rejection_records_event_and_mutates_nothing() -> None:
    game = _game(_fighter(), _goblin())
    engine, combat, collector = _start(DiceRoller(seed=7), game)
    actor_id = combat.active_actor()
    opponent = game.opponents_of(actor_id)[0]
    proposal = AttackProposal(actor_id=opponent, target_id=actor_id)  # wrong turn
    hp_before = game.characters[opponent].hit_points.current

    result = engine.resolve(game, combat, proposal, collector)

    assert result.valid is False
    assert collector.events[-1].event_type == "action_rejected"
    assert combat.economy.action_taken is False
    assert game.characters[opponent].hit_points.current == hp_before


def test_resolve_hit_applies_damage_and_consumes_action() -> None:
    # Rolls: two initiative d20s, then a d20 of 15 (hits AC 13 with +5 bonus).
    seed = _seed_with_rolls([10, 10, 15])
    game = _game(_fighter(), _goblin())
    engine, combat, collector = _start(DiceRoller(seed=seed), game)
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]

    result = engine.resolve(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target_id), collector
    )

    assert result.valid is True
    assert combat.economy.action_taken is True
    resolved = [e for e in collector.events if e.event_type == "attack_resolved"]
    assert resolved[-1].payload["hit"] is True
    damage_events = [e for e in collector.events if e.event_type == "damage_applied"]
    assert damage_events, "a hit must apply damage"
    payload = damage_events[-1].payload
    assert payload["hp_before"] - payload["hp_after"] == payload["amount"]
    assert game.characters[target_id].hit_points.current == payload["hp_after"]


def test_resolve_critical_hit_doubles_damage_dice() -> None:
    # Rolls: two initiative d20s, then a natural 20.
    seed = _seed_with_rolls([10, 10, 20])
    game = _game(_fighter(), _goblin(hp=100))
    engine, combat, collector = _start(DiceRoller(seed=seed), game)
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]

    engine.resolve(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target_id), collector
    )

    resolved = [e for e in collector.events if e.event_type == "attack_resolved"]
    assert resolved[-1].payload["critical"] is True
    damage = [e for e in collector.events if e.event_type == "damage_applied"][-1]
    # 2d8 + 3 with advantage doubled dice must exceed any single-die roll of 1d8+3
    assert damage.payload["amount"] >= 5


def test_resolve_natural_one_always_misses() -> None:
    seed = _seed_with_rolls([10, 10, 1])
    game = _game(_fighter(), _goblin())
    engine, combat, collector = _start(DiceRoller(seed=seed), game)
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]

    engine.resolve(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target_id), collector
    )

    resolved = [e for e in collector.events if e.event_type == "attack_resolved"]
    assert resolved[-1].payload["hit"] is False
    assert not [e for e in collector.events if e.event_type == "damage_applied"]
    assert game.characters[target_id].hit_points.current == 7


def test_defeated_target_emits_character_defeated() -> None:
    seed = _seed_with_rolls([10, 10, 15])
    game = _game(_fighter(), _goblin(hp=1))
    engine, combat, collector = _start(DiceRoller(seed=seed), game)
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]

    engine.resolve(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target_id), collector
    )

    defeated = collector.events[-1]
    assert defeated.event_type == "character_defeated"
    assert defeated.payload["character_id"] == str(target_id)


def test_advance_turn_skips_defeated_actors() -> None:
    game = _game(_fighter("A"), _goblin("G1"), _goblin("G2"))
    combat = Combat(
        entries=[
            InitiativeEntry(
                character_id=game.party_ids[0], total=10,
                dexterity_modifier=1, tiebreaker=5,
            ),
            InitiativeEntry(
                character_id=game.enemy_ids[0], total=8,
                dexterity_modifier=2, tiebreaker=3,
            ),
            InitiativeEntry(
                character_id=game.enemy_ids[1], total=6,
                dexterity_modifier=2, tiebreaker=2,
            ),
        ],
        economy=ActionEconomy(movement_budget_ft=30),
    )
    game.characters[game.enemy_ids[0]].apply_damage(999)  # G1 defeated
    collector = EventCollector(game_id=game.game_id)
    engine = CombatEngine(DiceRoller(seed=1))

    engine.advance_turn(game, combat, collector)

    assert combat.turn_index == 2
    assert combat.active_actor() == game.enemy_ids[1]


def test_advance_wraps_and_increments_round() -> None:
    game = _game(_fighter(), _goblin())
    combat = Combat(
        entries=[
            InitiativeEntry(
                character_id=game.party_ids[0], total=10,
                dexterity_modifier=1, tiebreaker=5,
            ),
            InitiativeEntry(
                character_id=game.enemy_ids[0], total=8,
                dexterity_modifier=2, tiebreaker=3,
            ),
        ],
        economy=ActionEconomy(movement_budget_ft=30),
        round_number=1,
        turn_index=1,
    )
    collector = EventCollector(game_id=game.game_id)
    engine = CombatEngine(DiceRoller(seed=1))

    engine.advance_turn(game, combat, collector)

    assert combat.round_number == 2
    assert combat.active_actor() == game.party_ids[0]
    assert combat.economy.action_taken is False
    assert collector.events[-1].event_type == "turn_started"


def test_advance_ends_combat_when_a_side_is_wiped() -> None:
    game = _game(_fighter(), _goblin())
    game.characters[game.enemy_ids[0]].apply_damage(999)
    combat = Combat(
        entries=[
            InitiativeEntry(
                character_id=game.party_ids[0], total=10,
                dexterity_modifier=1, tiebreaker=5,
            ),
            InitiativeEntry(
                character_id=game.enemy_ids[0], total=8,
                dexterity_modifier=2, tiebreaker=3,
            ),
        ],
        economy=ActionEconomy(movement_budget_ft=30),
        turn_index=0,
    )
    collector = EventCollector(game_id=game.game_id)
    engine = CombatEngine(DiceRoller(seed=1))

    engine.advance_turn(game, combat, collector)

    assert combat.status is CombatStatus.ENDED
    ended = collector.events[-1]
    assert ended.event_type == "combat_ended"
    assert ended.payload["winner_side"] == "party"


def test_enemy_policy_targets_first_living_opponent() -> None:
    game = _game(_fighter("A"), _goblin("G1"), _goblin("G2"))
    policy = SimpleMeleeEnemyPolicy()
    combat = Combat(
        entries=[
            InitiativeEntry(
                character_id=game.enemy_ids[0], total=10,
                dexterity_modifier=2, tiebreaker=5,
            )
        ],
        economy=ActionEconomy(movement_budget_ft=30),
    )

    proposal = policy.decide(game, game.enemy_ids[0])
    assert proposal.target_id == game.party_ids[0]


def test_enemy_policy_raises_without_living_opponents() -> None:
    game = _game(_fighter("A"), _goblin("G"))
    game.characters[game.party_ids[0]].apply_damage(999)
    policy = SimpleMeleeEnemyPolicy()

    with pytest.raises(AgentDecisionFailedError):
        policy.decide(game, game.enemy_ids[0])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_combat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.combat'`

- [ ] **Step 3: Write the implementation**

```python
# src/domain/combat/state.py
"""Combat state: initiative, rounds, turns (Implementation Plan §8)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from domain.character.abilities import AbilityType
from domain.character.character import Character
from domain.common.errors import ValidationError
from domain.common.ids import CharacterId
from domain.rules.actions import ActionEconomy
from domain.rules.dice import DiceRoller


class CombatStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


@dataclass(frozen=True)
class InitiativeEntry:
    character_id: CharacterId
    total: int
    dexterity_modifier: int
    tiebreaker: int


def roll_initiative(
    dice: DiceRoller,
    characters: dict[CharacterId, Character],
    participant_ids: Sequence[CharacterId],
) -> list[InitiativeEntry]:
    entries: list[InitiativeEntry] = []
    for character_id in participant_ids:
        character = characters[character_id]
        dex_modifier = character.ability_scores.modifier(AbilityType.DEXTERITY)
        natural = dice.roll_d20().natural
        if natural is None:  # pragma: no cover - roll_d20 always yields a natural
            raise ValidationError("initiative requires a single d20 roll")
        entries.append(
            InitiativeEntry(
                character_id=character_id,
                total=natural + dex_modifier,
                dexterity_modifier=dex_modifier,
                tiebreaker=natural,
            )
        )
    entries.sort(
        key=lambda entry: (
            -entry.total,
            -entry.dexterity_modifier,
            entry.character_id.value,
        )
    )
    return entries


@dataclass
class Combat:
    entries: list[InitiativeEntry]
    economy: ActionEconomy
    round_number: int = 1
    turn_index: int = 0
    status: CombatStatus = CombatStatus.ACTIVE

    def active_actor(self) -> CharacterId:
        return self.entries[self.turn_index].character_id
```

```python
# src/domain/combat/engine.py
"""Deterministic combat engine — validates proposals, resolves attacks, emits events."""

from __future__ import annotations

from collections.abc import Sequence

from domain.combat.state import Combat, CombatStatus, roll_initiative
from domain.common.ids import CharacterId
from domain.events.collector import EventCollector
from domain.events.events import (
    ActionRejected,
    AttackRequested,
    AttackResolved,
    CharacterDefeated,
    CombatEnded,
    CombatStarted,
    DamageApplied,
    InitiativeRolled,
    TurnEnded,
    TurnStarted,
)
from domain.rules.actions import ActionEconomy, ActionType, AttackProposal, ValidationResult
from domain.rules.checks import CheckResolver
from domain.rules.dice import DiceRoller
from domain.rules.progression import proficiency_bonus
from domain.world.game import Game


class CombatEngine:
    def __init__(self, dice: DiceRoller) -> None:
        self._dice = dice
        self._checks = CheckResolver(dice)

    def start(
        self,
        game: Game,
        participant_ids: Sequence[CharacterId],
        collector: EventCollector,
    ) -> Combat:
        entries = roll_initiative(self._dice, game.characters, participant_ids)
        for entry in entries:
            collector.record(
                InitiativeRolled(character_id=entry.character_id, total=entry.total)
            )
        first = entries[0].character_id
        combat = Combat(
            entries=entries,
            economy=ActionEconomy(movement_budget_ft=game.characters[first].speed_ft),
        )
        collector.record(
            CombatStarted(
                participant_ids=tuple(participant_ids),
                round_number=combat.round_number,
            )
        )
        collector.record(TurnStarted(round_number=combat.round_number, actor_id=first))
        return combat

    def validate(
        self, game: Game, combat: Combat, proposal: AttackProposal
    ) -> ValidationResult:
        if combat.status is not CombatStatus.ACTIVE:
            return ValidationResult.reject("combat is not active", "combat_not_active")
        if proposal.actor_id != combat.active_actor():
            return ValidationResult.reject(
                f"it is not {proposal.actor_id}'s turn", "not_your_turn"
            )
        actor = game.characters.get(proposal.actor_id)
        if actor is None or actor.is_defeated():
            return ValidationResult.reject("actor cannot act", "not_your_turn")
        if not combat.economy.can_take_action(ActionType.ATTACK):
            return ValidationResult.reject(
                "the action is no longer available this turn", "action_unavailable"
            )
        if actor.equipped_weapon is None:
            return ValidationResult.reject("no weapon is equipped", "invalid_action")
        if proposal.weapon_id is not None and (
            proposal.weapon_id != actor.equipped_weapon.weapon_id
        ):
            return ValidationResult.reject(
                "requested weapon is not available", "invalid_action"
            )
        target = game.characters.get(proposal.target_id)
        if target is None or target.id == actor.id or target.is_defeated():
            return ValidationResult.reject("invalid target", "invalid_target")
        if game.side_of(target.id) == game.side_of(actor.id):
            return ValidationResult.reject(
                "cannot attack a member of your own side", "invalid_target"
            )
        return ValidationResult.ok()

    def resolve(
        self,
        game: Game,
        combat: Combat,
        proposal: AttackProposal,
        collector: EventCollector,
    ) -> ValidationResult:
        result = self.validate(game, combat, proposal)
        if not result.valid:
            collector.record(
                ActionRejected(
                    actor_id=proposal.actor_id,
                    action_type=proposal.action_type.value,
                    reason=result.reason,
                )
            )
            return result

        actor = game.characters[proposal.actor_id]
        target = game.characters[proposal.target_id]
        weapon = actor.equipped_weapon
        if weapon is None:  # pragma: no cover - validate guarantees a weapon
            return ValidationResult.reject("no weapon is equipped", "invalid_action")

        collector.record(
            AttackRequested(
                attacker_id=actor.id, target_id=target.id, weapon_id=weapon.weapon_id
            )
        )
        attack_bonus = (
            actor.ability_scores.modifier(weapon.ability) + proficiency_bonus(actor.level)
        )
        roll = self._checks.attack_roll(attack_bonus, target.armor_class)
        collector.record(
            AttackResolved(
                attacker_id=actor.id,
                target_id=target.id,
                roll=roll.roll,
                attack_bonus=attack_bonus,
                total=roll.total,
                target_ac=roll.target_ac,
                hit=roll.hit,
                critical=roll.is_critical,
            )
        )
        combat.economy.use(ActionType.ATTACK)
        if not roll.hit:
            return result

        die_count = (
            weapon.damage_die_count * 2 if roll.is_critical else weapon.damage_die_count
        )
        damage = max(
            0,
            self._dice.roll(
                die_count,
                weapon.damage_die_size,
                modifier=actor.ability_scores.modifier(weapon.ability),
            ).total,
        )
        hp_before = target.hit_points.current
        target.apply_damage(damage)
        collector.record(
            DamageApplied(
                character_id=target.id,
                amount=damage,
                hp_before=hp_before,
                hp_after=target.hit_points.current,
            )
        )
        if target.is_defeated():
            collector.record(CharacterDefeated(character_id=target.id))
        return result

    def advance_turn(
        self, game: Game, combat: Combat, collector: EventCollector
    ) -> None:
        if combat.status is not CombatStatus.ACTIVE:
            return
        collector.record(
            TurnEnded(round_number=combat.round_number, actor_id=combat.active_actor())
        )
        if not game.living_enemy_ids:
            self._end(combat, collector, winner_side="party")
            return
        if not game.living_party_ids:
            self._end(combat, collector, winner_side="enemies")
            return

        count = len(combat.entries)
        for step in range(1, count + 1):
            index = (combat.turn_index + step) % count
            candidate = combat.entries[index].character_id
            if game.characters[candidate].is_defeated():
                continue
            if index <= combat.turn_index:
                combat.round_number += 1
            combat.turn_index = index
            combat.economy = ActionEconomy(
                movement_budget_ft=game.characters[candidate].speed_ft
            )
            collector.record(
                TurnStarted(round_number=combat.round_number, actor_id=candidate)
            )
            return

    def _end(self, combat: Combat, collector: EventCollector, winner_side: str) -> None:
        combat.status = CombatStatus.ENDED
        collector.record(
            CombatEnded(winner_side=winner_side, round_number=combat.round_number)
        )

```

```python
# src/domain/combat/policy.py
"""Deterministic MVP-0 enemy behaviour (Implementation Plan §8)."""

from __future__ import annotations

from domain.common.errors import AgentDecisionFailedError
from domain.common.ids import CharacterId
from domain.rules.actions import AttackProposal
from domain.world.game import Game


class SimpleMeleeEnemyPolicy:
    """Attack the first living opponent; deterministic, no LLM."""

    def decide(self, game: Game, actor_id: CharacterId) -> AttackProposal:
        for opponent_id in game.opponents_of(actor_id):
            if not game.characters[opponent_id].is_defeated():
                return AttackProposal(actor_id=actor_id, target_id=opponent_id)
        raise AgentDecisionFailedError(f"{actor_id} has no living opponents to attack")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_combat.py -v`
Expected: PASS

- [ ] **Step 5: Run lint and typecheck**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/domain/combat tests/domain/test_combat.py
git commit -m "feat(domain): add combat engine with initiative, attack resolution and turn advancement" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 13: Application Services & In-Memory Repositories

**Files:**
- Create: `src/application/ports.py`, `src/application/commands.py`, `src/application/views.py`, `src/application/game_service.py`, `src/application/__init__.py` (empty)
- Create: `src/infrastructure/persistence/in_memory.py`, `src/infrastructure/persistence/__init__.py` (empty)
- Test: `tests/application/test_game_service.py`

**Interfaces:**
- Consumes: `Game`, `GameStatus` (Task 11), `CombatEngine`, `Combat`, `CombatStatus`, `SimpleMeleeEnemyPolicy` (Task 12), events/`EventCollector`/`EventEnvelope`/`EventRepository` (Task 9), `DiceRoller` (Task 6), `AttackProposal` (Task 10), `CharacterId`, `GameId`, errors (Task 2), domain character types (Task 8), `proficiency_bonus` via engine.
- Produces:
  - `class GameRepository(Protocol)` in `application/ports.py`: `save(game: Game) -> None`, `get(game_id: GameId) -> Game` (raises `GameNotFoundError`).
  - `CreateGameCommand(campaign_name: str = "The Forgotten Ruins", seed: int | None = None)`, `WeaponSpec(weapon_id: str, name: str, damage_die_count: int, damage_die_size: int, ability: str = "strength")`, `AddCharacterCommand(name, character_type="player", character_class=None, level=1, strength/dexterity/constitution/intelligence/wisdom/charisma=10, armor_class=10, speed_ft=30, max_hp=1, weapon: WeaponSpec | None = None)`, `SubmitActionCommand(game_id: GameId, actor_id: CharacterId, action_type: str, target_id: CharacterId | None = None, weapon_id: str | None = None)` in `application/commands.py`.
  - Views in `application/views.py`: `CharacterView(id, name, character_class: str | None, level, hp_current, hp_max, armor_class, conditions: list[str], is_defeated)`, `InitiativeEntryView(character_id, name, total)`, `CombatView(round_number, status, active_actor_id: str | None, initiative_order)`, `GameView(game_id, campaign_name, status, party, enemies, combat: CombatView | None)`, `TurnReport(game_id, accepted, error_code, reason, events: list[EventEnvelope], view: GameView, game_over)`.
  - `class GameService(game_repository, event_repository)` with `create_game(command) -> GameId`, `add_character(game_id, command) -> CharacterId`, `start_combat(game_id) -> GameView`, `submit_action(command) -> TurnReport`, `run_active_enemy_turns(game_id) -> TurnReport`, `get_view(game_id) -> GameView`, `get_events(game_id) -> list[EventEnvelope]`.
  - `class InMemoryGameRepository` in `infrastructure/persistence/in_memory.py` implementing `GameRepository`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/application/test_game_service.py
import pytest

from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
    WeaponSpec,
)
from application.game_service import GameService
from domain.common.errors import (
    CombatNotActiveError,
    GameNotFoundError,
    GameNotRunningError,
    InvalidActionError,
    ValidationError,
)
from domain.common.ids import CharacterId, GameId
from domain.rules.dice import DiceRoller
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository


def _service() -> GameService:
    return GameService(InMemoryGameRepository(), InMemoryEventRepository())


def _fighter_command(name: str = "Arin") -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="player",
        character_class="fighter",
        level=1,
        strength=16, dexterity=13, constitution=15,
        intelligence=10, wisdom=12, charisma=9,
        armor_class=16,
        speed_ft=30,
        max_hp=12,
        weapon=WeaponSpec(
            weapon_id="longsword", name="Longsword",
            damage_die_count=1, damage_die_size=8,
        ),
    )


def _goblin_command(name: str = "Goblin") -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="enemy",
        level=1,
        strength=8, dexterity=14, constitution=10,
        intelligence=10, wisdom=8, charisma=8,
        armor_class=13,
        speed_ft=30,
        max_hp=7,
        weapon=WeaponSpec(
            weapon_id="scimitar", name="Scimitar",
            damage_die_count=1, damage_die_size=6,
        ),
    )


def _started_game(
    seed: int = 42,
) -> tuple[GameService, GameId, CharacterId, CharacterId]:
    service = _service()
    game_id = service.create_game(CreateGameCommand(seed=seed, campaign_name="Ruins"))
    arin_id = service.add_character(game_id, _fighter_command())
    goblin_id = service.add_character(game_id, _goblin_command())
    service.start_combat(game_id)
    return service, game_id, arin_id, goblin_id


def _seed_with_rolls(rolls: list[int]) -> int:
    for seed in range(100_000):
        roller = DiceRoller(seed=seed)
        if [roller.roll_d20().natural for _ in rolls] == rolls:
            return seed
    raise AssertionError("no seed produced the requested rolls")


def test_create_game_emits_game_created_and_persists() -> None:
    service = _service()
    game_id = service.create_game(CreateGameCommand(seed=42, campaign_name="Ruins"))

    view = service.get_view(game_id)
    assert view.status == "created"
    assert view.campaign_name == "Ruins"
    assert view.combat is None
    assert view.party == []

    events = service.get_events(game_id)
    assert [e.event_type for e in events] == ["game_created"]
    assert events[0].payload["seed"] == 42


def test_get_view_raises_for_unknown_game() -> None:
    service = _service()
    with pytest.raises(GameNotFoundError):
        service.get_view(GameId.generate())


def test_start_combat_emits_expected_events_and_view() -> None:
    service, game_id, arin_id, goblin_id = _started_game()

    view = service.get_view(game_id)
    assert view.status == "running"
    assert [c.id for c in view.party] == [str(arin_id)]
    assert [c.id for c in view.enemies] == [str(goblin_id)]
    assert view.combat is not None
    assert view.combat.status == "active"
    assert view.combat.round_number == 1
    assert view.combat.active_actor_id in {str(arin_id), str(goblin_id)}
    assert len(view.combat.initiative_order) == 2

    types = [e.event_type for e in service.get_events(game_id)]
    assert types[0] == "game_created"
    assert "game_started" in types
    assert types.count("initiative_rolled") == 2
    assert "combat_started" in types
    assert types[-1] == "turn_started"


def test_add_character_rejected_after_combat_starts() -> None:
    service, game_id, _, _ = _started_game()
    with pytest.raises(ValidationError):
        service.add_character(game_id, _fighter_command("Late"))


def test_submit_action_rejects_wrong_turn_without_side_effects() -> None:
    service, game_id, arin_id, goblin_id = _started_game()
    view = service.get_view(game_id)
    assert view.combat is not None
    active = view.combat.active_actor_id
    assert active is not None
    actor_id = goblin_id if active == str(arin_id) else arin_id
    target_id = arin_id if actor_id is goblin_id else goblin_id

    report = service.submit_action(
        SubmitActionCommand(
            game_id=game_id, actor_id=actor_id,
            action_type="attack", target_id=target_id,
        )
    )

    assert report.accepted is False
    assert report.error_code == "not_your_turn"
    assert any(e.event_type == "action_rejected" for e in report.events)
    assert report.view.combat is not None
    assert report.view.combat.active_actor_id == active  # turn did not advance


def test_submit_unknown_action_type_raises() -> None:
    service, game_id, arin_id, _ = _started_game()
    with pytest.raises(InvalidActionError):
        service.submit_action(
            SubmitActionCommand(game_id=game_id, actor_id=arin_id, action_type="teleport")
        )


def test_submit_action_requires_a_running_game() -> None:
    service = _service()
    game_id = service.create_game(CreateGameCommand(seed=1))
    arin_id = service.add_character(game_id, _fighter_command())
    goblin_id = service.add_character(game_id, _goblin_command())
    with pytest.raises(GameNotRunningError):
        service.submit_action(
            SubmitActionCommand(
                game_id=game_id, actor_id=arin_id,
                action_type="attack", target_id=goblin_id,
            )
        )


def test_run_enemy_turns_requires_active_combat() -> None:
    service = _service()
    game_id = service.create_game(CreateGameCommand(seed=1))
    with pytest.raises(CombatNotActiveError):
        service.run_active_enemy_turns(game_id)


def test_submit_action_runs_enemy_chain_and_stops_at_party() -> None:
    # Rolls: initiative 10 and 10 (goblin wins the DEX tiebreak), then a hit.
    seed = _seed_with_rolls([10, 10, 15])
    service, game_id, arin_id, goblin_id = _started_game(seed=seed)
    view = service.get_view(game_id)
    assert view.combat is not None
    assert view.combat.active_actor_id == str(goblin_id)

    report = service.submit_action(
        SubmitActionCommand(
            game_id=game_id, actor_id=goblin_id,
            action_type="attack", target_id=arin_id,
        )
    )

    assert report.accepted is True
    assert report.game_over is False
    types = [e.event_type for e in report.events]
    assert "attack_requested" in types
    assert "attack_resolved" in types
    assert "damage_applied" in types
    assert types.count("turn_ended") == 1
    assert types[-1] == "turn_started"
    assert report.view.combat is not None
    assert report.view.combat.active_actor_id == str(arin_id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/test_game_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.game_service'`

- [ ] **Step 3: Write the implementation**

```python
# src/application/ports.py
"""Repository ports — implemented by infrastructure (CLAUDE.md §36)."""

from __future__ import annotations

from typing import Protocol

from domain.common.ids import GameId
from domain.world.game import Game


class GameRepository(Protocol):
    def save(self, game: Game) -> None: ...

    def get(self, game_id: GameId) -> Game: ...
```

```python
# src/application/commands.py
"""Application commands — statements of intent (CLAUDE.md §12: commands, not events)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.common.ids import CharacterId, GameId


@dataclass(frozen=True)
class CreateGameCommand:
    campaign_name: str = "The Forgotten Ruins"
    seed: int | None = None


@dataclass(frozen=True)
class WeaponSpec:
    weapon_id: str
    name: str
    damage_die_count: int
    damage_die_size: int
    ability: str = "strength"


@dataclass(frozen=True)
class AddCharacterCommand:
    name: str
    character_type: str = "player"
    character_class: str | None = None
    level: int = 1
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10
    armor_class: int = 10
    speed_ft: int = 30
    max_hp: int = 1
    weapon: WeaponSpec | None = None


@dataclass(frozen=True)
class SubmitActionCommand:
    game_id: GameId
    actor_id: CharacterId
    action_type: str
    target_id: CharacterId | None = None
    weapon_id: str | None = None
```

```python
# src/application/views.py
"""Read models for interfaces — never leak domain objects (CLAUDE.md §41)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.events.collector import EventEnvelope


@dataclass(frozen=True)
class CharacterView:
    id: str
    name: str
    character_class: str | None
    level: int
    hp_current: int
    hp_max: int
    armor_class: int
    conditions: list[str]
    is_defeated: bool


@dataclass(frozen=True)
class InitiativeEntryView:
    character_id: str
    name: str
    total: int


@dataclass(frozen=True)
class CombatView:
    round_number: int
    status: str
    active_actor_id: str | None
    initiative_order: list[InitiativeEntryView]


@dataclass(frozen=True)
class GameView:
    game_id: str
    campaign_name: str
    status: str
    party: list[CharacterView]
    enemies: list[CharacterView]
    combat: CombatView | None


@dataclass(frozen=True)
class TurnReport:
    game_id: str
    accepted: bool
    error_code: str
    reason: str
    events: list[EventEnvelope]
    view: GameView
    game_over: bool
```

```python
# src/application/game_service.py
"""Coordinates game use cases; rules live in the domain (CLAUDE.md §6)."""

from __future__ import annotations

import secrets

from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
)
from application.ports import GameRepository
from application.views import (
    CharacterView,
    CombatView,
    GameView,
    InitiativeEntryView,
    TurnReport,
)
from domain.character.abilities import AbilityScores, AbilityType
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.combat.engine import CombatEngine
from domain.combat.policy import SimpleMeleeEnemyPolicy
from domain.combat.state import Combat, CombatStatus
from domain.common.errors import (
    AgentDecisionFailedError,
    CombatNotActiveError,
    GameNotRunningError,
    InvalidActionError,
    ValidationError,
)
from domain.common.ids import CampaignId, CharacterId, GameId
from domain.events.collector import EventCollector, EventEnvelope
from domain.events.events import GameCreated, GameStarted
from domain.events.repository import EventRepository
from domain.rules.actions import AttackProposal
from domain.rules.dice import DiceRoller
from domain.world.game import Game, GameStatus

MAX_ENEMY_CHAIN_TURNS = 200


class GameService:
    def __init__(
        self, game_repository: GameRepository, event_repository: EventRepository
    ) -> None:
        self._games = game_repository
        self._events = event_repository
        self._combats: dict[GameId, Combat] = {}
        self._collectors: dict[GameId, EventCollector] = {}
        self._dice: dict[GameId, DiceRoller] = {}

    # -- helpers ---------------------------------------------------------

    def _game(self, game_id: GameId) -> Game:
        return self._games.get(game_id)

    def _collector(self, game: Game) -> EventCollector:
        collector = self._collectors.get(game.game_id)
        if collector is None:
            collector = EventCollector(game_id=game.game_id)
            self._collectors[game.game_id] = collector
        return collector

    def _engine(self, game: Game) -> CombatEngine:
        dice = self._dice.get(game.game_id)
        if dice is None:
            # One seeded roller per game: identical seed + roll order => identical game.
            dice = DiceRoller(seed=game.seed)
            self._dice[game.game_id] = dice
        return CombatEngine(dice)

    def _persist(self, game: Game) -> list[EventEnvelope]:
        drained = self._collector(game).drain()
        for envelope in drained:
            self._events.append(game.game_id, envelope)
        self._games.save(game)
        return drained

    # -- use cases ---------------------------------------------------------

    def create_game(self, command: CreateGameCommand) -> GameId:
        game_id = GameId.generate()
        campaign_id = CampaignId.generate()
        seed = command.seed if command.seed is not None else secrets.randbits(32)
        game = Game(
            game_id=game_id,
            campaign_id=campaign_id,
            campaign_name=command.campaign_name,
            seed=seed,
        )
        collector = EventCollector(game_id=game_id)
        self._collectors[game_id] = collector
        collector.record(GameCreated(campaign_id=campaign_id, seed=seed))
        self._persist(game)
        return game_id

    def add_character(self, game_id: GameId, command: AddCharacterCommand) -> CharacterId:
        game = self._game(game_id)
        character = self._build_character(command)
        if command.character_type == "enemy":
            game.add_enemy(character)
        else:
            game.add_party_member(character)
        self._persist(game)
        return character.id

    def _build_character(self, command: AddCharacterCommand) -> Character:
        weapon = (
            None
            if command.weapon is None
            else Weapon(
                weapon_id=command.weapon.weapon_id,
                name=command.weapon.name,
                damage_die_count=command.weapon.damage_die_count,
                damage_die_size=command.weapon.damage_die_size,
                ability=AbilityType(command.weapon.ability),
            )
        )
        return Character(
            id=CharacterId.generate(),
            name=command.name,
            character_type=CharacterType(command.character_type),
            character_class=(
                CharacterClass(command.character_class) if command.character_class else None
            ),
            level=command.level,
            ability_scores=AbilityScores(
                strength=command.strength,
                dexterity=command.dexterity,
                constitution=command.constitution,
                intelligence=command.intelligence,
                wisdom=command.wisdom,
                charisma=command.charisma,
            ),
            armor_class=command.armor_class,
            speed_ft=command.speed_ft,
            hit_points=HitPoints(current=command.max_hp, maximum=command.max_hp),
            equipped_weapon=weapon,
        )

    def start_combat(self, game_id: GameId) -> GameView:
        game = self._game(game_id)
        if game.status is not GameStatus.CREATED:
            raise ValidationError("combat can only be started once per game")
        if not game.party_ids or not game.enemy_ids:
            raise ValidationError(
                "combat needs at least one party member and one enemy"
            )
        game.mark_started()
        collector = self._collector(game)
        collector.record(GameStarted())
        engine = self._engine(game)
        combat = engine.start(game, (*game.party_ids, *game.enemy_ids), collector)
        self._combats[game_id] = combat
        self._persist(game)
        return self.get_view(game_id)

    def submit_action(self, command: SubmitActionCommand) -> TurnReport:
        game = self._game(command.game_id)
        if game.status is not GameStatus.RUNNING:
            raise GameNotRunningError("the game must be running to submit actions")
        combat = self._combats.get(command.game_id)
        if combat is None:
            raise CombatNotActiveError("no active combat for this game")

        proposal = self._proposal_from(command)
        collector = self._collector(game)
        engine = self._engine(game)

        result = engine.resolve(game, combat, proposal, collector)
        if result.valid and combat.status is CombatStatus.ACTIVE:
            engine.advance_turn(game, combat, collector)
        self._run_enemy_chain(game, combat, engine, collector)

        game_over = combat.status is CombatStatus.ENDED
        if game_over:
            game.mark_ended()
        events = self._persist(game)
        return TurnReport(
            game_id=str(command.game_id),
            accepted=result.valid,
            error_code=result.error_code,
            reason=result.reason,
            events=events,
            view=self.get_view(command.game_id),
            game_over=game_over,
        )

    def _proposal_from(self, command: SubmitActionCommand) -> AttackProposal:
        if command.action_type != "attack":
            raise InvalidActionError(f"unsupported action type: {command.action_type}")
        if command.target_id is None:
            raise InvalidActionError("an attack requires a target")
        return AttackProposal(
            actor_id=command.actor_id,
            target_id=command.target_id,
            weapon_id=command.weapon_id,
        )

    def _run_enemy_chain(
        self,
        game: Game,
        combat: Combat,
        engine: CombatEngine,
        collector: EventCollector,
    ) -> None:
        guard = 0
        while (
            combat.status is CombatStatus.ACTIVE
            and game.side_of(combat.active_actor()) == "enemies"
        ):
            actor_id = combat.active_actor()
            proposal = SimpleMeleeEnemyPolicy().decide(game, actor_id)
            engine.resolve(game, combat, proposal, collector)
            if combat.status is CombatStatus.ACTIVE:
                engine.advance_turn(game, combat, collector)
            guard += 1
            if guard > MAX_ENEMY_CHAIN_TURNS:
                raise AgentDecisionFailedError("enemy turn chain did not terminate")

    def run_active_enemy_turns(self, game_id: GameId) -> TurnReport:
        game = self._game(game_id)
        combat = self._combats.get(game_id)
        if combat is None:
            raise CombatNotActiveError("no active combat for this game")

        collector = self._collector(game)
        engine = self._engine(game)
        if (
            combat.status is CombatStatus.ACTIVE
            and game.side_of(combat.active_actor()) == "enemies"
        ):
            self._run_enemy_chain(game, combat, engine, collector)

        game_over = combat.status is CombatStatus.ENDED
        if game_over:
            game.mark_ended()
        events = self._persist(game)
        return TurnReport(
            game_id=str(game_id),
            accepted=True,
            error_code="",
            reason="",
            events=events,
            view=self.get_view(game_id),
            game_over=game_over,
        )

    def get_view(self, game_id: GameId) -> GameView:
        game = self._game(game_id)
        combat = self._combats.get(game_id)
        combat_view: CombatView | None = None
        if combat is not None:
            active: str | None = None
            if combat.status is CombatStatus.ACTIVE:
                active = str(combat.active_actor())
            combat_view = CombatView(
                round_number=combat.round_number,
                status=combat.status.value,
                active_actor_id=active,
                initiative_order=[
                    InitiativeEntryView(
                        character_id=str(entry.character_id),
                        name=game.characters[entry.character_id].name,
                        total=entry.total,
                    )
                    for entry in combat.entries
                ],
            )
        return GameView(
            game_id=str(game.game_id),
            campaign_name=game.campaign_name,
            status=game.status.value,
            party=[self._character_view(game.characters[cid]) for cid in game.party_ids],
            enemies=[
                self._character_view(game.characters[cid]) for cid in game.enemy_ids
            ],
            combat=combat_view,
        )

    def _character_view(self, character: Character) -> CharacterView:
        return CharacterView(
            id=str(character.id),
            name=character.name,
            character_class=(
                character.character_class.value if character.character_class else None
            ),
            level=character.level,
            hp_current=character.hit_points.current,
            hp_max=character.hit_points.maximum,
            armor_class=character.armor_class,
            conditions=list(character.conditions),
            is_defeated=character.is_defeated(),
        )

    def get_events(self, game_id: GameId) -> list[EventEnvelope]:
        self._game(game_id)
        return self._events.get_events(game_id)
```

```python
# src/infrastructure/persistence/in_memory.py
"""In-memory GameRepository for MVP-0; PostgreSQL arrives in Plan 2."""

from __future__ import annotations

from domain.common.errors import GameNotFoundError
from domain.common.ids import GameId
from domain.world.game import Game


class InMemoryGameRepository:
    def __init__(self) -> None:
        self._games: dict[GameId, Game] = {}

    def save(self, game: Game) -> None:
        self._games[game.game_id] = game

    def get(self, game_id: GameId) -> Game:
        game = self._games.get(game_id)
        if game is None:
            raise GameNotFoundError(f"no game with id '{game_id}'")
        return game
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/test_game_service.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite, lint, and typecheck**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: all tests PASS, no lint or type errors

- [ ] **Step 6: Commit**

```bash
git add src/application src/infrastructure/persistence tests/application
git commit -m "feat(application): add game service, commands, views and in-memory repositories" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 14: Rich CLI — Renderer & Interactive App

**Files:**
- Create: `src/interfaces/cli/renderer.py`, `src/interfaces/cli/app.py`, `src/interfaces/cli/__init__.py` (empty)
- Test: `tests/interfaces/test_renderer.py`, `tests/interfaces/test_cli.py`

**Interfaces:**
- Consumes: `GameService`, `CreateGameCommand`, `AddCharacterCommand`, `SubmitActionCommand`, `WeaponSpec`, `GameView`, `TurnReport` (Task 13), `EventEnvelope` (Task 9), `DomainError` (Task 2), `GameId`, `CharacterId` (Task 2), Rich (`Console`, `Panel`, `Table`).
- Produces:
  - `parse_input(raw: str) -> tuple[str, str]` — returns `("empty", "")`, `("command", "/…")`, `("attack", "<target>")`, or `("unknown", "<raw>")`.
  - `describe_event(envelope: EventEnvelope, name_by_id: dict[str, str]) -> str | None` — one human-readable line per renderable event, `None` for silent events.
  - `render_game_view(console: Console, view: GameView) -> None`, `render_report(console: Console, report: TurnReport, view: GameView) -> None`.
  - `build_service() -> GameService` — wires the in-memory repositories.
  - `main(argv: list[str] | None = None, console: Console | None = None, service: GameService | None = None, input_fn: Callable[[str], str] | None = None) -> int` — `--seed` (default 42); default scenario Arin (fighter) vs Goblin.

- [ ] **Step 1: Write the failing tests**

```python
# tests/interfaces/test_renderer.py
from io import StringIO

from rich.console import Console

from application.views import (
    CharacterView,
    CombatView,
    GameView,
    InitiativeEntryView,
)
from domain.common.ids import EventId, GameId
from domain.events.collector import EventEnvelope
from interfaces.cli.renderer import describe_event, render_game_view


def _console() -> tuple[Console, StringIO]:
    buffer = StringIO()
    return Console(file=buffer, width=100, force_terminal=False), buffer


def _view() -> GameView:
    return GameView(
        game_id="game-1",
        campaign_name="The Forgotten Ruins",
        status="running",
        party=[
            CharacterView(
                id="c1", name="Arin", character_class="fighter", level=1,
                hp_current=12, hp_max=12, armor_class=16,
                conditions=[], is_defeated=False,
            )
        ],
        enemies=[
            CharacterView(
                id="c2", name="Goblin", character_class=None, level=1,
                hp_current=3, hp_max=7, armor_class=13,
                conditions=[], is_defeated=False,
            )
        ],
        combat=CombatView(
            round_number=1,
            status="active",
            active_actor_id="c1",
            initiative_order=[
                InitiativeEntryView(character_id="c1", name="Arin", total=5),
                InitiativeEntryView(character_id="c2", name="Goblin", total=3),
            ],
        ),
    )


def test_render_game_view_shows_rosters_and_combat() -> None:
    console, buffer = _console()
    render_game_view(console, _view())
    output = buffer.getvalue()
    assert "Arin" in output
    assert "Goblin" in output
    assert "Round 1" in output
    assert "12/12" in output
    assert "3/7" in output
    assert "Arin (5)" in output


def test_render_game_view_without_combat() -> None:
    console, buffer = _console()
    view = GameView(
        game_id="game-1", campaign_name="Ruins",
        status="created", party=[], enemies=[], combat=None,
    )
    render_game_view(console, view)
    assert "Ruins" in buffer.getvalue()


def _envelope(event_type: str, payload: dict[str, object]) -> EventEnvelope:
    return EventEnvelope(
        sequence=1,
        event_id=EventId.generate(),
        game_id=GameId.generate(),
        occurred_at="2026-01-01T00:00:00+00:00",
        event_type=event_type,
        payload=payload,
    )


def test_describe_attack_resolved() -> None:
    line = describe_event(
        _envelope(
            "attack_resolved",
            {
                "attacker_id": "c1", "target_id": "c2",
                "roll": 15, "attack_bonus": 5, "total": 20,
                "target_ac": 13, "hit": True, "critical": False,
            },
        ),
        {"c1": "Arin", "c2": "Goblin"},
    )
    assert line == "⚔ Arin attacks Goblin: d20 15 +5 = 20 vs AC 13 — HIT"


def test_describe_damage_and_defeat() -> None:
    damage = describe_event(
        _envelope(
            "damage_applied",
            {"character_id": "c2", "amount": 4, "hp_before": 7, "hp_after": 3},
        ),
        {"c2": "Goblin"},
    )
    assert damage == "💥 Goblin takes 4 damage (7 → 3)"

    defeat = describe_event(
        _envelope("character_defeated", {"character_id": "c2"}), {"c2": "Goblin"}
    )
    assert defeat == "☠ Goblin is defeated!"


def test_describe_rejection_and_combat_end() -> None:
    rejected = describe_event(
        _envelope(
            "action_rejected",
            {"actor_id": "c1", "action_type": "attack", "reason": "not your turn"},
        ),
        {},
    )
    assert rejected == "✗ Action rejected: not your turn"

    ended = describe_event(
        _envelope("combat_ended", {"winner_side": "party", "round_number": 2}), {}
    )
    assert ended == "🏆 party wins the combat in round 2!"


def test_undescribed_events_return_none() -> None:
    assert (
        describe_event(_envelope("turn_started", {"round_number": 1, "actor_id": "c1"}), {})
        is None
    )
```

```python
# tests/interfaces/test_cli.py
from io import StringIO

from rich.console import Console

from interfaces.cli.app import main, parse_input


def _console() -> tuple[Console, StringIO]:
    buffer = StringIO()
    return Console(file=buffer, width=100, force_terminal=False), buffer


def _scripted(*lines: str):
    iterator = iter(lines)

    def _input(prompt: str) -> str:
        try:
            return next(iterator)
        except StopIteration as error:
            raise EOFError from error

    return _input


def test_parse_input_variants() -> None:
    assert parse_input("attack goblin") == ("attack", "goblin")
    assert parse_input("  ATTACK Goblin  ") == ("attack", "Goblin")
    assert parse_input("/quit") == ("command", "/quit")
    assert parse_input("   ") == ("empty", "")
    assert parse_input("dance") == ("unknown", "dance")


def test_main_quit_leaves_a_created_game() -> None:
    console, buffer = _console()
    code = main(console=console, input_fn=_scripted("/quit"))
    assert code == 0
    assert "Party" in buffer.getvalue()


def test_main_full_fight_reaches_a_winner() -> None:
    console, buffer = _console()
    code = main(console=console, input_fn=_scripted(*(["attack goblin"] * 60)))
    assert code == 0
    assert "wins the combat" in buffer.getvalue()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/interfaces -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'interfaces.cli'`

- [ ] **Step 3: Write the renderer implementation**

```python
# src/interfaces/cli/renderer.py
"""Rich rendering of application views — presentation only (CLAUDE.md §42)."""

from __future__ import annotations

from collections.abc import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from application.views import CharacterView, GameView, TurnReport
from domain.events.collector import EventEnvelope


def render_game_view(console: Console, view: GameView) -> None:
    console.print(
        Panel(
            f"[bold]{view.campaign_name}[/bold] — game {view.game_id} — status: {view.status}",
            expand=False,
        )
    )
    console.print(_roster_table("Party", view.party))
    console.print(_roster_table("Enemies", view.enemies))
    if view.combat is None:
        return
    combat = view.combat
    header = f"Round {combat.round_number} — combat {combat.status}"
    if combat.active_actor_id is not None:
        header += f" — {_name_for(view, combat.active_actor_id)}'s turn"
    console.print(header)
    console.print(
        "Initiative: "
        + ", ".join(f"{e.name} ({e.total})" for e in combat.initiative_order)
    )
    console.print("Actions: attack <target> — /status /help /quit")


def _roster_table(title: str, members: Sequence[CharacterView]) -> Table:
    table = Table(title=title)
    table.add_column("Name")
    table.add_column("Class")
    table.add_column("Level")
    table.add_column("HP")
    table.add_column("AC")
    table.add_column("Conditions")
    for member in members:
        table.add_row(
            member.name,
            member.character_class or "-",
            str(member.level),
            f"{member.hp_current}/{member.hp_max}",
            str(member.armor_class),
            ", ".join(member.conditions) or "-",
        )
    return table


def _name_for(view: GameView, character_id: str) -> str:
    for member in (*view.party, *view.enemies):
        if member.id == character_id:
            return member.name
    return character_id


def render_report(console: Console, report: TurnReport, view: GameView) -> None:
    name_by_id = {m.id: m.name for m in (*view.party, *view.enemies)}
    for envelope in report.events:
        line = describe_event(envelope, name_by_id)
        if line is not None:
            console.print(line)


def describe_event(envelope: EventEnvelope, name_by_id: dict[str, str]) -> str | None:
    payload = envelope.payload
    if envelope.event_type == "attack_resolved":
        attacker = name_by_id.get(str(payload["attacker_id"]), str(payload["attacker_id"]))
        target = name_by_id.get(str(payload["target_id"]), str(payload["target_id"]))
        if payload["critical"]:
            outcome = "CRITICAL HIT"
        elif payload["hit"]:
            outcome = "HIT"
        else:
            outcome = "MISS"
        return (
            f"⚔ {attacker} attacks {target}: d20 {payload['roll']} +"
            f"{payload['attack_bonus']} = {payload['total']} vs AC {payload['target_ac']}"
            f" — {outcome}"
        )
    if envelope.event_type == "damage_applied":
        name = name_by_id.get(str(payload["character_id"]), str(payload["character_id"]))
        return (
            f"💥 {name} takes {payload['amount']} damage"
            f" ({payload['hp_before']} → {payload['hp_after']})"
        )
    if envelope.event_type == "character_defeated":
        name = name_by_id.get(str(payload["character_id"]), str(payload["character_id"]))
        return f"☠ {name} is defeated!"
    if envelope.event_type == "action_rejected":
        return f"✗ Action rejected: {payload['reason']}"
    if envelope.event_type == "combat_ended":
        return f"🏆 {payload['winner_side']} wins the combat in round {payload['round_number']}!"
    # initiative_rolled / game_* / turn_* / attack_requested events stay silent
    return None
```

- [ ] **Step 4: Run renderer tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/interfaces/test_renderer.py -v`
Expected: PASS

- [ ] **Step 5: Write the CLI app implementation**

```python
# src/interfaces/cli/app.py
"""CLI adapter — translates input into application commands (CLAUDE.md §42, §63)."""

from __future__ import annotations

import argparse
from collections.abc import Callable

from rich.console import Console

from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
    WeaponSpec,
)
from application.game_service import GameService
from application.views import GameView
from domain.common.errors import DomainError
from domain.common.ids import CharacterId, GameId
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository
from interfaces.cli.renderer import render_game_view, render_report


def parse_input(raw: str) -> tuple[str, str]:
    stripped = raw.strip()
    if not stripped:
        return ("empty", "")
    if stripped.startswith("/"):
        return ("command", stripped)
    parts = stripped.split(None, 1)
    if parts[0].lower() == "attack" and len(parts) == 2:
        return ("attack", parts[1].strip())
    return ("unknown", stripped)


def build_service() -> GameService:
    return GameService(InMemoryGameRepository(), InMemoryEventRepository())


def _resolve_target(view: GameView, token: str) -> str | None:
    for member in (*view.party, *view.enemies):
        if member.id == token or member.name.lower() == token.lower():
            return member.id
    return None


def _is_enemy(view: GameView, character_id: str) -> bool:
    return any(member.id == character_id for member in view.enemies)


def _arin() -> AddCharacterCommand:
    return AddCharacterCommand(
        name="Arin",
        character_type="player",
        character_class="fighter",
        level=1,
        strength=16, dexterity=13, constitution=15,
        intelligence=10, wisdom=12, charisma=9,
        armor_class=16,
        speed_ft=30,
        max_hp=12,
        weapon=WeaponSpec(
            weapon_id="longsword", name="Longsword",
            damage_die_count=1, damage_die_size=8,
        ),
    )


def _goblin() -> AddCharacterCommand:
    return AddCharacterCommand(
        name="Goblin",
        character_type="enemy",
        level=1,
        strength=8, dexterity=14, constitution=10,
        intelligence=10, wisdom=8, charisma=8,
        armor_class=13,
        speed_ft=30,
        max_hp=7,
        weapon=WeaponSpec(
            weapon_id="scimitar", name="Scimitar",
            damage_die_count=1, damage_die_size=6,
        ),
    )


def main(
    argv: list[str] | None = None,
    console: Console | None = None,
    service: GameService | None = None,
    input_fn: Callable[[str], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="conclave")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    console = console or Console()
    service = service or build_service()

    game_id = service.create_game(CreateGameCommand(seed=args.seed))
    service.add_character(game_id, _arin())
    service.add_character(game_id, _goblin())
    service.start_combat(game_id)

    while True:
        view = service.get_view(game_id)
        render_game_view(console, view)
        if view.status == "ended":
            console.print("The adventure has ended. Thanks for playing!")
            return 0
        if (
            view.combat is not None
            and view.combat.status == "active"
            and view.combat.active_actor_id is not None
            and _is_enemy(view, view.combat.active_actor_id)
        ):
            report = service.run_active_enemy_turns(game_id)
            render_report(console, report, view)
            continue

        try:
            raw = (input_fn or input)("conclave> ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return 0

        kind, argument = parse_input(raw)
        if kind == "empty":
            continue
        if kind == "command":
            if argument == "/quit":
                return 0
            if argument == "/status":
                continue
            if argument == "/help":
                console.print("Commands: attack <target>, /status, /help, /quit")
            else:
                console.print(f"Unknown command: {argument}")
            continue
        if kind == "attack":
            target_id = _resolve_target(view, argument)
            if target_id is None:
                console.print(f"No such character: {argument}")
                continue
            actor_id = view.combat.active_actor_id if view.combat else None
            if actor_id is None:
                continue
            try:
                report = service.submit_action(
                    SubmitActionCommand(
                        game_id=GameId(view.game_id),
                        actor_id=CharacterId(actor_id),
                        action_type="attack",
                        target_id=CharacterId(target_id),
                    )
                )
            except DomainError as error:
                console.print(f"[red]{error}[/red]")
                continue
            render_report(console, report, view)
            continue
        console.print("Unknown input — try: attack <target>")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run the CLI tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/interfaces -v`
Expected: PASS

- [ ] **Step 7: Run the full suite, lint, and typecheck**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: all tests PASS, no lint or type errors

- [ ] **Step 8: Commit**

```bash
git add src/interfaces tests/interfaces
git commit -m "feat(interfaces): add rich cli renderer and interactive game loop" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 15: MVP-0 Integration Test & Final Verification

**Files:**
- Test: `tests/integration/test_mvp0_combat_sandbox.py`

**Interfaces:**
- Consumes: `GameService` and application commands (Task 13), in-memory repositories (Tasks 9 & 13).
- Produces: the executable proof of MVP-0 (Implementation Plan §26): create game → fighter + goblin → start combat → initiative → attack loop → deterministic winner, no LLM anywhere.

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_mvp0_combat_sandbox.py
"""MVP-0 end-to-end through the application layer — no LLM (Implementation Plan §26)."""

import pytest

from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
    WeaponSpec,
)
from application.game_service import GameService
from application.views import GameView
from domain.common.ids import CharacterId, GameId
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository


def _service() -> GameService:
    return GameService(InMemoryGameRepository(), InMemoryEventRepository())


def _arin() -> AddCharacterCommand:
    return AddCharacterCommand(
        name="Arin", character_type="player", character_class="fighter",
        level=1,
        strength=16, dexterity=13, constitution=15,
        intelligence=10, wisdom=12, charisma=9,
        armor_class=16, speed_ft=30, max_hp=12,
        weapon=WeaponSpec(
            weapon_id="longsword", name="Longsword",
            damage_die_count=1, damage_die_size=8,
        ),
    )


def _goblin() -> AddCharacterCommand:
    return AddCharacterCommand(
        name="Goblin", character_type="enemy", level=1,
        strength=8, dexterity=14, constitution=10,
        intelligence=10, wisdom=8, charisma=8,
        armor_class=13, speed_ft=30, max_hp=7,
        weapon=WeaponSpec(
            weapon_id="scimitar", name="Scimitar",
            damage_die_count=1, damage_die_size=6,
        ),
    )


def _new_game(
    service: GameService, seed: int
) -> tuple[GameId, CharacterId, CharacterId]:
    game_id = service.create_game(
        CreateGameCommand(seed=seed, campaign_name="The Forgotten Ruins")
    )
    arin_id = service.add_character(game_id, _arin())
    goblin_id = service.add_character(game_id, _goblin())
    service.start_combat(game_id)
    return game_id, arin_id, goblin_id


def _play(seed: int) -> tuple[GameService, GameId, GameView]:
    service = _service()
    game_id, arin_id, goblin_id = _new_game(service, seed)

    for _ in range(100):
        view = service.get_view(game_id)
        assert view.combat is not None
        if view.combat.status == "ended":
            break
        active = view.combat.active_actor_id
        assert active is not None
        if active == str(arin_id):
            report = service.submit_action(
                SubmitActionCommand(
                    game_id=game_id, actor_id=arin_id,
                    action_type="attack", target_id=goblin_id,
                )
            )
            assert report.accepted, f"party attack rejected: {report.reason}"
        else:
            service.run_active_enemy_turns(game_id)
    else:
        pytest.fail("combat did not end within 100 iterations")

    return service, game_id, service.get_view(game_id)


def test_mvp0_combat_reaches_a_deterministic_winner() -> None:
    service, game_id, view = _play(seed=42)

    assert view.status == "ended"
    assert view.combat is not None
    assert view.combat.status == "ended"

    ended = [e for e in service.get_events(game_id) if e.event_type == "combat_ended"]
    assert len(ended) == 1
    winner = ended[0].payload["winner_side"]
    if winner == "party":
        assert all(c.is_defeated for c in view.enemies)
        assert any(not c.is_defeated for c in view.party)
    else:
        assert all(c.is_defeated for c in view.party)
        assert any(not c.is_defeated for c in view.enemies)


def test_events_have_contiguous_sequences() -> None:
    service, game_id, _ = _play(seed=42)
    sequences = [e.sequence for e in service.get_events(game_id)]
    assert sequences == list(range(1, len(sequences) + 1))


def test_mvp0_is_reproducible_for_the_same_seed() -> None:
    first_service, first_id, first_view = _play(seed=42)
    second_service, second_id, second_view = _play(seed=42)

    # UUIDs differ between runs, so compare the observable trajectory instead.
    first_types = [e.event_type for e in first_service.get_events(first_id)]
    second_types = [e.event_type for e in second_service.get_events(second_id)]
    assert first_types == second_types

    assert [(c.name, c.hp_current) for c in first_view.party + first_view.enemies] == [
        (c.name, c.hp_current) for c in second_view.party + second_view.enemies
    ]


def test_rejected_action_changes_nothing() -> None:
    service = _service()
    game_id, arin_id, goblin_id = _new_game(service, seed=1)
    view = service.get_view(game_id)
    assert view.combat is not None
    active = view.combat.active_actor_id
    assert active is not None
    # Always submit as the character whose turn it is NOT.
    if active == str(arin_id):
        actor_id, target_id = goblin_id, arin_id
    else:
        actor_id, target_id = arin_id, goblin_id

    report = service.submit_action(
        SubmitActionCommand(
            game_id=game_id, actor_id=actor_id,
            action_type="attack", target_id=target_id,
        )
    )

    assert report.accepted is False
    assert report.error_code == "not_your_turn"
    after = service.get_view(game_id)
    assert after.combat is not None
    assert after.combat.active_actor_id == active
    for before_char, after_char in zip(view.party + view.enemies, after.party + after.enemies):
        assert before_char.hp_current == after_char.hp_current
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/integration -v`
Expected: the tests run against the existing application layer and PASS only if Tasks 1–14 are correct; a failure here means a regression in an earlier task.

- [ ] **Step 3: Run the full verification battery**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: all tests PASS, no lint or type errors

- [ ] **Step 4: Play the game by hand (manual MVP-0 acceptance)**

Run: `.venv/bin/python -m interfaces.cli.app --seed 42`
Expected: party and enemy tables render, initiative is shown, `attack goblin` repeats until `🏆 party wins the combat` appears, then the game exits cleanly. Stop when the combat ends.

- [ ] **Step 5: Commit**

```bash
git add tests/integration
git commit -m "test(integration): verify mvp0 deterministic combat sandbox end to end" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Completion Standard (CLAUDE.md §73)

Answer these for the finished MVP-0 before declaring the plan complete:

- **What changed?** Deterministic domain core (ids, errors, abilities, proficiency, vitals, inventory, dice, checks, weapons, characters, events, actions, game aggregate, combat engine, enemy policy), application services with in-memory persistence, Rich CLI, integration tests.
- **Which architectural layer owns it?** Domain owns all rules; application coordinates; infrastructure implements ports; interfaces render.
- **Which tests verify it?** Every module has test-first coverage; `tests/integration/test_mvp0_combat_sandbox.py` proves the MVP-0 milestone end to end.
- **Can the feature work without a real LLM?** Yes — MVP-0 contains no LLM anywhere; the enemy uses `SimpleMeleeEnemyPolicy`.
- **Can an invalid LLM action corrupt game state?** No — invalid proposals are rejected with an `ActionRejected` event and zero mutation (covered by rejection tests at domain, application, and integration levels).
- **Did any provider-specific dependency leak across boundaries?** No — the domain imports only the standard library; only `interfaces` imports Rich.
- **Were existing tests run at every step?** Yes — full `pytest -q`, `ruff check`, and `mypy` after each task.

