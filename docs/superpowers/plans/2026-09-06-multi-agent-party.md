# Multi-Agent Party (Plan 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single-agent demo into a three-agent AI party (Brix, Mira, Sera + human Arin) fighting a configured 2-goblin + orc encounter, with a first slice of §32 party communication (optional `party_message` broadcast on accepted turns, shared board, chatter in every agent's prompt).

**Architecture:** Extend the Plan 4 stack — no new LLM calls per turn, no domain changes, no new dependencies. Party statlines and the encounter become configuration (`agents.toml` `[stats]` blocks, new `encounter.toml` loaded in every CLI mode). A `PartyMessageBoard` (application layer) stores accepted chatter; `AgentTurnService` reads the last 8 messages into each prompt and posts after accepted model turns.

**Tech Stack:** Python 3.12 stdlib (dataclasses, tomllib), pytest, mypy strict, ruff (line length 100), Rich CLI, FakeModelGateway for all offline tests.

**Spec:** `docs/superpowers/specs/2026-09-06-multi-agent-party-design.md` (binding; decisions 1–9)

## Global Constraints

- Domain layer untouched: `git log master..HEAD --oneline -- src/domain` must stay empty after every task.
- `src/ai/agents/` stays game-free (purity test `tests/ai/agents/test_purity.py` keeps passing).
- No new runtime dependencies; stdlib only (tomllib, dataclasses).
- Provider names/model ids only under `src/infrastructure/llm/` and as config values in `config/*.toml`; all model profiles remain `z-ai/glm-5.3-flash`.
- Secrets from environment only (`OPENROUTER_API_KEY`, `DATABASE_URL`); never committed or logged.
- No private chain-of-thought requested, displayed, or persisted (§33).
- Offline tests only: `FakeModelGateway` / `ScriptedAgentGateway`; `asyncio.run` bridging; no pytest-asyncio. The only live call is the pre-existing Plan 3 smoke test (runs when `OPENROUTER_API_KEY` is set).
- Repo conventions: pytest `pythonpath=["src"]`; **no `__init__.py` in test dirs → test file basenames must be unique repo-wide**; mypy strict; ruff line length 100; conventional commits ending `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
- Gate command (every task): `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
- Offline test counts per task (baseline 280): T1 → 285, T2 → 290, T3 → 296, T4 → 304, T5 → 307, T6 → 308, T7 → 308. With `OPENROUTER_API_KEY` set, add +1 (live smoke). If a count drifts, stop and reconcile before committing.

---

### Task 1: `PartyMessageBoard` — the §32 broadcast board

**Files:**
- Create: `src/application/agents/party_board.py`
- Test: `tests/application/agents/test_party_board.py`

**Interfaces:**
- Consumes: nothing (stdlib dataclasses).
- Produces: `PartyMessage(actor_name: str, text: str, round_number: int)` frozen dataclass; `PartyMessageBoard` with `post(message: PartyMessage) -> None` and `recent(limit: int = 8) -> tuple[PartyMessage, ...]` (chronological order, last `limit`; `limit <= 0` → `()`). Tasks 4 and 5 import both from `application.agents.party_board`.

- [ ] **Step 1: Write the failing tests**

Create `tests/application/agents/test_party_board.py`:

```python
"""PartyMessageBoard tests — the §32 broadcast board (agent-layer, not game truth)."""

from application.agents.party_board import PartyMessage, PartyMessageBoard


def _message(
    name: str = "Brix", text: str = "Focus the orc.", round_number: int = 1
) -> PartyMessage:
    return PartyMessage(actor_name=name, text=text, round_number=round_number)


def test_empty_board_returns_no_messages() -> None:
    assert PartyMessageBoard().recent() == ()


def test_recent_returns_messages_in_chronological_order() -> None:
    board = PartyMessageBoard()
    board.post(_message(text="first"))
    board.post(_message(name="Mira", text="second", round_number=2))
    recent = board.recent()
    assert [message.text for message in recent] == ["first", "second"]
    assert recent[1].actor_name == "Mira"
    assert recent[1].round_number == 2


def test_recent_bounds_the_read() -> None:
    board = PartyMessageBoard()
    for index in range(10):
        board.post(_message(text=f"msg-{index}"))
    recent = board.recent(limit=8)
    assert [message.text for message in recent] == [f"msg-{index}" for index in range(2, 10)]


def test_non_positive_limit_returns_no_messages() -> None:
    board = PartyMessageBoard()
    board.post(_message())
    assert board.recent(limit=0) == ()
    assert board.recent(limit=-3) == ()


def test_returned_tuple_is_independent_of_later_posts() -> None:
    board = PartyMessageBoard()
    board.post(_message(text="first"))
    recent = board.recent()
    board.post(_message(text="second"))
    assert len(recent) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/agents/test_party_board.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.agents.party_board'`

- [ ] **Step 3: Implement**

Create `src/application/agents/party_board.py`:

```python
"""Party message board (§32 first slice): broadcast chatter, agent-layer only (§10)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PartyMessage:
    """One broadcast party-chat line; never game truth (spec §3.1)."""

    actor_name: str
    text: str
    round_number: int


class PartyMessageBoard:
    """In-memory broadcast board: unbounded appends, bounded reads (spec §3.1)."""

    def __init__(self) -> None:
        self._messages: list[PartyMessage] = []

    def post(self, message: PartyMessage) -> None:
        self._messages.append(message)

    def recent(self, limit: int = 8) -> tuple[PartyMessage, ...]:
        if limit <= 0:
            return ()
        return tuple(self._messages[-limit:])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/agents/test_party_board.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **285** offline tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/application/agents/party_board.py tests/application/agents/test_party_board.py
git commit -m "feat(application): add party message board for agent chatter

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: `AgentStats` in profiles + the three-agent config

**Files:**
- Modify: `src/application/agents/profiles.py` (full rewrite below)
- Modify: `config/agents.toml` (full rewrite below — 3 agents with `[stats]`)
- Modify: `tests/application/agents/test_agent_profiles.py` (full rewrite below — 13 tests)
- Modify: `tests/application/agents/test_character_agent.py` (`_PROFILE` gains `stats`)
- Modify: `tests/application/agents/test_agent_turn_service.py` (`_BRIX` gains `stats`)

**Interfaces:**
- Consumes: `WeaponSpec` from `application.commands` (fields: `weapon_id: str`, `name: str`, `damage_die_count: int`, `damage_die_size: int`, `ability: str = "strength"`).
- Produces: `AgentStats` frozen dataclass (nine int fields + `weapon: WeaponSpec`); `AgentProfile` gains required `stats: AgentStats` as its 7th field; loader requires an `[agents.<name>.stats]` table with all nine ints (≥ 1, non-bool) and a `stats.weapon` sub-table (`weapon_id`/`name` non-empty strings, die fields ints ≥ 1). Tasks 5–6 read `profile.stats`.

- [ ] **Step 1: Write the failing tests**

Full rewrite of `tests/application/agents/test_agent_profiles.py`:

```python
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
```

(13 tests. `_VALID[: _VALID.index(...)]` slices the string before the marker — the
marker line itself stays out.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/agents/test_agent_profiles.py -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'stats'` (or `AttributeError: stats`) on the shipped-config test.

- [ ] **Step 3: Implement**

Full rewrite of `src/application/agents/profiles.py`:

```python
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
```

Full rewrite of `config/agents.toml`:

```toml
[agent]
max_action_retries = 2

[agents.brix]
character_name = "Brix"
character_class = "fighter"
persona = "A cautious sellsword who prefers finishing fights quickly and safely."
objective = "Survive the skirmish and protect Arin; engage the nearest threat."
model_profile = "player"

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

[agents.mira]
character_name = "Mira"
character_class = "rogue"
persona = "An opportunistic skirmisher who finishes wounded foes and picks her shots."
objective = "Cull the weakest standing enemy each round."
model_profile = "player"

[agents.mira.stats]
strength = 10
dexterity = 16
constitution = 12
intelligence = 14
wisdom = 12
charisma = 10
armor_class = 15
speed_ft = 30
max_hp = 10

[agents.mira.stats.weapon]
weapon_id = "shortsword"
name = "Shortsword"
damage_die_count = 1
damage_die_size = 6

[agents.sera]
character_name = "Sera"
character_class = "cleric"
persona = "A protective cleric who watches the party's backs and calls out the biggest threat."
objective = "Keep allies standing; engage whatever presses the party hardest."
model_profile = "player"

[agents.sera.stats]
strength = 14
dexterity = 10
constitution = 14
intelligence = 9
wisdom = 16
charisma = 12
armor_class = 16
speed_ft = 30
max_hp = 11

[agents.sera.stats.weapon]
weapon_id = "mace"
name = "Mace"
damage_die_count = 1
damage_die_size = 6
```

Then update the two test files that construct `AgentProfile` (the field is now required).

In `tests/application/agents/test_character_agent.py` — replace the import line:

```python
from application.agents.profiles import AgentProfile
```

with:

```python
from application.agents.profiles import AgentProfile, AgentStats
from application.commands import WeaponSpec
```

and insert a `_STATS` constant directly above `_PROFILE = AgentProfile(` and pass it:

```python
_STATS = AgentStats(
    strength=16,
    dexterity=13,
    constitution=15,
    intelligence=10,
    wisdom=12,
    charisma=9,
    armor_class=16,
    speed_ft=30,
    max_hp=12,
    weapon=WeaponSpec(
        weapon_id="longsword",
        name="Longsword",
        damage_die_count=1,
        damage_die_size=8,
    ),
)

_PROFILE = AgentProfile(
    name="brix",
    character_name="Brix",
    character_class="fighter",
    persona="A cautious sellsword who prefers finishing fights quickly and safely.",
    objective="Survive the skirmish and protect Arin; engage the nearest threat.",
    model_profile="player",
    stats=_STATS,
)
```

In `tests/application/agents/test_agent_turn_service.py` — replace:

```python
from application.agents.profiles import AgentProfile, AgentProfileCatalog
```

with:

```python
from application.agents.profiles import AgentProfile, AgentProfileCatalog, AgentStats
```

and replace the `_BRIX = AgentProfile(` block with:

```python
_BRIX_STATS = AgentStats(
    strength=16,
    dexterity=13,
    constitution=15,
    intelligence=10,
    wisdom=12,
    charisma=9,
    armor_class=16,
    speed_ft=30,
    max_hp=12,
    weapon=WeaponSpec(
        weapon_id="longsword",
        name="Longsword",
        damage_die_count=1,
        damage_die_size=8,
    ),
)
_BRIX = AgentProfile(
    name="brix",
    character_name="Brix",
    character_class="fighter",
    persona="A cautious sellsword.",
    objective="Engage the nearest threat.",
    model_profile="player",
    stats=_BRIX_STATS,
)
```

(`WeaponSpec` is already imported in that test file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/agents/ -q`
Expected: PASS — all application/agents tests green (the 13 profile tests plus existing ones).

- [ ] **Step 5: Quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **290** offline tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/application/agents/profiles.py config/agents.toml tests/application/agents/
git commit -m "feat(application): add agent statlines and the three-agent config

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Encounter loader + `config/encounter.toml`

**Files:**
- Create: `src/application/encounter.py`
- Create: `config/encounter.toml`
- Test: `tests/application/test_encounter.py`

**Interfaces:**
- Consumes: `AddCharacterCommand`, `WeaponSpec` from `application.commands`.
- Produces: `EncounterError(ValueError)`; frozen `EnemySpec` (name, level, six ability ints, armor_class, speed_ft, max_hp, weapon: WeaponSpec); `load_encounter(path: str | Path) -> tuple[AddCharacterCommand, ...]` — each `[[enemies]]` entry becomes `AddCharacterCommand(character_type="enemy", ...)`. Task 6 imports `load_encounter`.

- [ ] **Step 1: Write the failing tests**

Create `tests/application/test_encounter.py`:

```python
"""Encounter configuration loading tests."""

from pathlib import Path

import pytest

from application.commands import AddCharacterCommand, WeaponSpec
from application.encounter import EncounterError, load_encounter

_SHIPPED = Path(__file__).resolve().parents[2] / "config" / "encounter.toml"

_VALID = """\
[[enemies]]
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
weapon = { weapon_id = "scimitar", name = "Scimitar", damage_die_count = 1, damage_die_size = 6 }
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "encounter.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_shipped_encounter_as_enemy_commands() -> None:
    commands = load_encounter(_SHIPPED)
    names = [command.name for command in commands]
    assert names == ["Goblin Scout", "Goblin Skulker", "Orc Brute"]
    assert all(command.character_type == "enemy" for command in commands)
    orc = commands[2]
    assert orc.strength == 16
    assert orc.armor_class == 15
    assert orc.max_hp == 15
    assert orc.weapon is not None
    assert orc.weapon.weapon_id == "greataxe"


def test_maps_stats_and_weapon(tmp_path: Path) -> None:
    (command,) = load_encounter(_write(tmp_path, _VALID))
    assert isinstance(command, AddCharacterCommand)
    assert command.character_type == "enemy"
    assert command.level == 1
    assert command.dexterity == 14
    assert command.max_hp == 7
    assert command.weapon == WeaponSpec(
        weapon_id="scimitar",
        name="Scimitar",
        damage_die_count=1,
        damage_die_size=6,
    )


def test_missing_name_raises(tmp_path: Path) -> None:
    with pytest.raises(EncounterError, match="name"):
        load_encounter(_write(tmp_path, _VALID.replace('name = "Goblin Scout"\n', "")))


def test_non_positive_stat_raises(tmp_path: Path) -> None:
    with pytest.raises(EncounterError, match="max_hp"):
        load_encounter(_write(tmp_path, _VALID.replace("max_hp = 7", "max_hp = 0")))


def test_duplicate_name_raises(tmp_path: Path) -> None:
    text = _VALID + _VALID.replace("Goblin Scout", "goblin scout")
    with pytest.raises(EncounterError, match="duplicate enemy name"):
        load_encounter(_write(tmp_path, text))


def test_empty_enemies_raises(tmp_path: Path) -> None:
    with pytest.raises(EncounterError, match="at least one enemy"):
        load_encounter(_write(tmp_path, ""))
```

(6 tests; the duplicate test is case-insensitive by construction.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/test_encounter.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.encounter'`

- [ ] **Step 3: Implement**

Create `src/application/encounter.py`:

```python
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
```

Create `config/encounter.toml`:

```toml
# The MVP-0 encounter (specs/2026-09-06-multi-agent-party-design.md §3.3).
# Loaded in every CLI mode — the fight is game content, not agent configuration.

[[enemies]]
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
weapon = { weapon_id = "scimitar", name = "Scimitar", damage_die_count = 1, damage_die_size = 6 }

[[enemies]]
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
weapon = { weapon_id = "scimitar", name = "Scimitar", damage_die_count = 1, damage_die_size = 6 }

[[enemies]]
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
weapon = { weapon_id = "greataxe", name = "Greataxe", damage_die_count = 1, damage_die_size = 12 }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/test_encounter.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **296** offline tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/application/encounter.py config/encounter.toml tests/application/test_encounter.py
git commit -m "feat(application): load the encounter from config/encounter.toml

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: The say field — schema, mapping, prompt chatter

**Files:**
- Modify: `src/application/agents/character_agent.py` (full rewrite below)
- Modify: `tests/application/agents/test_character_agent.py` (append 8 tests + 1 import line)

**Interfaces:**
- Consumes: `PartyMessage` from `application.agents.party_board` (Task 1); `AgentPerception`, `AgentProfile` unchanged.
- Produces: `ATTACK_DECISION_SCHEMA` gains optional `"party_message": {"type": "string"}` (NOT in required); `AgentDecision` gains `party_message: str | None = None`; `CharacterAgent.build_user_prompt(perception, *, rejection=None, party_messages: tuple[PartyMessage, ...] = ())` renders a "Party chatter:" section. Task 5 depends on all three.

- [ ] **Step 1: Write the failing tests**

In `tests/application/agents/test_character_agent.py`, first update the import block — replace:

```python
from application.agents.perception import AgentPerception, OpponentBrief
```

with:

```python
from application.agents.party_board import PartyMessage
from application.agents.perception import AgentPerception, OpponentBrief
```

Then append:

```python
def test_schema_allows_optional_party_message() -> None:
    validate_against_schema(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "x",
            "party_message": "Focus the orc.",
        },
        ATTACK_DECISION_SCHEMA,
    )  # does not raise


def test_schema_rejects_non_string_party_message() -> None:
    with pytest.raises(ModelInvalidResponseError):
        validate_against_schema(
            {
                "action_type": "attack",
                "target_id": "gob",
                "public_message": "x",
                "party_message": 3,
            },
            ATTACK_DECISION_SCHEMA,
        )


def test_map_decision_missing_or_blank_party_message_is_silence() -> None:
    agent = CharacterAgent(_PROFILE)
    silent = agent.map_decision(
        {"action_type": "attack", "target_id": "gob", "public_message": "hi"},
        _perception(),
    )
    blank = agent.map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "party_message": "  ",
        },
        _perception(),
    )
    assert silent.party_message is None
    assert blank.party_message is None


def test_map_decision_non_string_party_message_is_silence() -> None:
    decision = CharacterAgent(_PROFILE).map_decision(
        {"action_type": "attack", "target_id": "gob", "public_message": "hi", "party_message": 7},
        _perception(),
    )
    assert decision.party_message is None


def test_map_decision_collapses_newlines_and_strips() -> None:
    decision = CharacterAgent(_PROFILE).map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "party_message": "  Focus\nthe orc!\n",
        },
        _perception(),
    )
    assert decision.party_message == "Focus the orc!"


def test_map_decision_truncates_to_200_chars() -> None:
    decision = CharacterAgent(_PROFILE).map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "party_message": "x" * 500,
        },
        _perception(),
    )
    assert decision.party_message is not None
    assert len(decision.party_message) == 200


def test_user_prompt_renders_party_chatter() -> None:
    chatter = (
        PartyMessage(actor_name="Mira", text="The goblin bleeds — finish it.", round_number=1),
        PartyMessage(actor_name="Sera", text="Watch the orc.", round_number=1),
    )
    prompt = CharacterAgent(_PROFILE).build_user_prompt(_perception(), party_messages=chatter)
    assert "Party chatter:" in prompt
    assert "- Mira (round 1): The goblin bleeds — finish it." in prompt
    assert "- Sera (round 1): Watch the orc." in prompt
    assert prompt.count("HP") == 1  # chatter never leaks enemy stats


def test_user_prompt_omits_chatter_section_when_empty() -> None:
    prompt = CharacterAgent(_PROFILE).build_user_prompt(_perception(), party_messages=())
    assert "Party chatter:" not in prompt
```

(8 tests. The `count("HP") == 1` pin from Plan 4 still holds with chatter present.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/agents/test_character_agent.py -q`
Expected: FAIL — `ImportError: cannot import name 'PartyMessage'` … then, after that import exists only in Task 1 (it does), the failures become assertion/type errors: `AttributeError: 'AgentDecision' object has no attribute 'party_message'` and `TypeError: build_user_prompt() got an unexpected keyword argument 'party_messages'`.

- [ ] **Step 3: Implement**

Full rewrite of `src/application/agents/character_agent.py`:

```python
"""One character agent: identity, prompts, and structured-decision mapping."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from application.agents.party_board import PartyMessage
from application.agents.perception import AgentPerception
from application.agents.profiles import AgentProfile
from domain.common.ids import CharacterId
from domain.rules.actions import AttackProposal

ATTACK_DECISION_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "action_type": {"type": "string", "enum": ["attack"]},
        "target_id": {"type": "string"},
        "public_message": {"type": "string"},
        "party_message": {"type": "string"},
    },
    "required": ["action_type", "target_id", "public_message"],
    "additionalProperties": False,
}

_PARTY_MESSAGE_MAX_CHARS = 200


class InvalidAgentDecisionError(ValueError):
    """The model's decision failed agent-level mapping (unknown/dead target, bad fields)."""


@dataclass(frozen=True)
class AgentDecision:
    proposal: AttackProposal
    public_message: str
    party_message: str | None = None


class CharacterAgent:
    """Prompt construction and decision mapping for one agent-controlled character."""

    def __init__(self, profile: AgentProfile) -> None:
        self._profile = profile

    def build_system_prompt(self) -> str:
        return (
            f"You are {self._profile.character_name}, a {self._profile.character_class} "
            "in a tabletop role-playing combat.\n"
            f"Personality: {self._profile.persona}\n"
            f"Objective: {self._profile.objective}\n"
            "\n"
            "Rules:\n"
            "- You may only take the attack action.\n"
            "- Choose exactly one target_id from the opponents listed in the user message.\n"
            "- You may include party_message: one short sentence coordinating with your "
            "allies. Omit it to stay silent.\n"
            '- Reply ONLY with a JSON object: action_type ("attack"), target_id (string), '
            "public_message (a short first-person battle cry or rationale; never hidden "
            "reasoning), and optionally party_message (one short sentence for your allies).\n"
            "- No other keys, no prose outside the JSON."
        )

    def build_user_prompt(
        self,
        perception: AgentPerception,
        *,
        rejection: str | None = None,
        party_messages: tuple[PartyMessage, ...] = (),
    ) -> str:
        me = perception.self_view
        conditions = ", ".join(me.conditions) if me.conditions else "none"
        lines = [
            f"Round {perception.round_number}. It is your turn.",
            f"You: {me.name} (level {me.level}, {me.character_class}), "
            f"HP {me.hp_current}/{me.hp_max}, AC {me.armor_class}, "
            f"conditions: {conditions}.",
            "Opponents:",
        ]
        lines.extend(
            f"- {opponent.id}: {opponent.name} "
            f"({'defeated' if opponent.is_defeated else 'standing'})"
            for opponent in perception.opponents
        )
        if party_messages:
            lines.append("Party chatter:")
            lines.extend(
                f"- {message.actor_name} (round {message.round_number}): {message.text}"
                for message in party_messages
            )
        lines.append(f"Turn order: {', '.join(perception.initiative_order)}")
        if rejection is not None:
            lines.append(f"Your previous action was rejected: {rejection}. Choose again.")
        return "\n".join(lines)

    def map_decision(
        self, data: Mapping[str, Any], perception: AgentPerception
    ) -> AgentDecision:
        if data.get("action_type") != "attack":
            raise InvalidAgentDecisionError(
                f"unsupported action_type: {data.get('action_type')!r}"
            )

        target_id = data.get("target_id")
        if not isinstance(target_id, str) or not target_id:
            raise InvalidAgentDecisionError("target_id must be a non-empty string")

        living = {
            opponent.id: opponent
            for opponent in perception.opponents
            if not opponent.is_defeated
        }
        if target_id not in living:
            raise InvalidAgentDecisionError(
                f"target '{target_id}' is not a living opponent (living: {sorted(living)})"
            )

        public_message = data.get("public_message")
        if not isinstance(public_message, str) or not public_message.strip():
            raise InvalidAgentDecisionError("public_message must be a non-empty string")

        return AgentDecision(
            proposal=AttackProposal(
                actor_id=CharacterId(perception.active_actor_id),
                target_id=CharacterId(target_id),
            ),
            public_message=public_message.strip(),
            party_message=self._map_party_message(data.get("party_message")),
        )

    @staticmethod
    def _map_party_message(raw: object) -> str | None:
        """Chatter is cosmetic: never a rejection — silence, collapse, truncate (spec §3.4)."""
        if not isinstance(raw, str):
            return None
        collapsed = " ".join(raw.split())
        if not collapsed:
            return None
        return collapsed[:_PARTY_MESSAGE_MAX_CHARS]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/agents/test_character_agent.py -q`
Expected: PASS (18 passed)

- [ ] **Step 5: Quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **304** offline tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/application/agents/character_agent.py tests/application/agents/test_character_agent.py
git commit -m "feat(application): add optional party_message to the agent decision

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: Board in the turn loop — service wiring + multi-agent tests

**Files:**
- Modify: `src/application/agents/agent_turn_service.py` (full rewrite below)
- Modify: `tests/application/agents/test_agent_turn_service.py` (several edits, exact code below)

**Interfaces:**
- Consumes: `PartyMessage`/`PartyMessageBoard` (Task 1); `AgentDecision.party_message`, `build_user_prompt(party_messages=...)` (Task 4); `AgentProfile.stats` (Task 2); existing `AgentRuntime`, `GameService`, `TurnReport`, `SubmitActionCommand`.
- Produces: `AgentTurnService(..., *, max_action_retries=None, board: PartyMessageBoard | None = None)`; `AgentTurnReport` gains `actor_name: str` (2nd field) and `party_message: str | None = None` (last field); accepted model turns with chatter post to the board; Task 6 reads `report.actor_name`/`report.party_message`.

- [ ] **Step 1: Write the failing tests**

Edits to `tests/application/agents/test_agent_turn_service.py`:

1a. Update the import block — replace:

```python
"""AgentTurnService decision-loop tests (scripted fake gateway, no real LLM)."""

import pytest

from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.models.errors import ModelTimeoutError
from ai.models.fake import FakeModelGateway
from ai.models.profiles import ModelProfile, ModelProfileCatalog
from application.agents.agent_turn_service import AgentNotRegisteredError, AgentTurnService
from application.agents.fake_script import ScriptedAgentGateway
from application.agents.profiles import AgentProfile, AgentProfileCatalog, AgentStats
```

with:

```python
"""AgentTurnService decision-loop tests (scripted fake gateway, no real LLM)."""

from collections.abc import Mapping
from typing import Any

import pytest

from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.models.errors import ModelTimeoutError
from ai.models.fake import FakeModelGateway
from ai.models.profiles import ModelProfile, ModelProfileCatalog
from ai.models.types import ModelRequest, StructuredModelResponse
from application.agents.agent_turn_service import AgentNotRegisteredError, AgentTurnService
from application.agents.fake_script import ScriptedAgentGateway
from application.agents.party_board import PartyMessageBoard
from application.agents.profiles import AgentProfile, AgentProfileCatalog, AgentStats
```

1b. Directly below the `_BRIX = AgentProfile(...)` block, add the capturing gateway:

```python
class _CapturingFake(FakeModelGateway):
    """Records structured-call requests so tests can assert on prompts."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[ModelRequest] = []

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse:
        self.requests.append(request)
        return await super().generate_structured(request, schema)
```

1c. Replace `def _goblin() -> AddCharacterCommand:` with `def _goblin(name: str = "Goblin") -> AddCharacterCommand:` and inside it replace `name="Goblin",` with `name=name,`.

1d. Below `_goblin`, add the new builders:

```python
def _rogue(name: str) -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="player",
        character_class="rogue",
        level=1,
        strength=10,
        dexterity=16,
        constitution=12,
        intelligence=14,
        wisdom=12,
        charisma=10,
        armor_class=15,
        speed_ft=30,
        max_hp=10,
        weapon=WeaponSpec(
            weapon_id="shortsword",
            name="Shortsword",
            damage_die_count=1,
            damage_die_size=6,
        ),
    )


def _cleric(name: str) -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="player",
        character_class="cleric",
        level=1,
        strength=14,
        dexterity=10,
        constitution=14,
        intelligence=9,
        wisdom=16,
        charisma=12,
        armor_class=16,
        speed_ft=30,
        max_hp=11,
        weapon=WeaponSpec(
            weapon_id="mace",
            name="Mace",
            damage_die_count=1,
            damage_die_size=6,
        ),
    )


def _orc() -> AddCharacterCommand:
    return AddCharacterCommand(
        name="Orc Brute",
        character_type="enemy",
        level=1,
        strength=16,
        dexterity=12,
        constitution=14,
        intelligence=7,
        wisdom=10,
        charisma=8,
        armor_class=15,
        speed_ft=30,
        max_hp=15,
        weapon=WeaponSpec(
            weapon_id="greataxe",
            name="Greataxe",
            damage_die_count=1,
            damage_die_size=12,
        ),
    )
```

1e. Replace `_party_with_brix_first` with a version accepting extra party members:

```python
def _party_with_brix_first(
    game_service: GameService,
    *extra_party: AddCharacterCommand,
) -> tuple[GameId, CharacterId, CharacterId]:
    """Create Arin + Brix (+ extras) + Goblin, start combat; find a seed where Brix acts first."""
    for seed in range(1, 500):
        game_id = game_service.create_game(CreateGameCommand(seed=seed))
        game_service.add_character(game_id, _fighter("Arin"))
        brix_id = game_service.add_character(game_id, _fighter("Brix"))
        for command in extra_party:
            game_service.add_character(game_id, command)
        goblin_id = game_service.add_character(game_id, _goblin())
        game_service.start_combat(game_id)
        view = game_service.get_view(game_id)
        if view.combat is not None and view.combat.active_actor_id == brix_id.value:
            return game_id, brix_id, goblin_id
    raise AssertionError("no seed in 1..499 lets Brix act first")
```

1f. Replace `_agent_service` with a version accepting a board:

```python
def _agent_service(
    game_service: GameService,
    gateway: FakeModelGateway,
    *,
    max_action_retries: int = 2,
    board: PartyMessageBoard | None = None,
) -> AgentTurnService:
    runtime = AgentRuntime(gateway, RetryPolicy(max_attempts=3))
    agent_profiles = AgentProfileCatalog(
        max_action_retries=max_action_retries,
        agents={"brix": _BRIX},
    )
    return AgentTurnService(
        game_service, runtime, _MODEL_CATALOG, agent_profiles, board=board
    )
```

1g. **Delete** the existing `test_full_fight_completes_with_the_agent_in_the_party` test and append these four tests:

```python
def test_accepted_model_turn_posts_the_party_message() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    fake.enqueue_structured(
        {
            "action_type": "attack",
            "target_id": goblin_id.value,
            "public_message": "I strike.",
            "party_message": "The goblin bleeds — finish it.",
        }
    )
    board = PartyMessageBoard()
    service = _agent_service(game_service, fake, board=board)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.party_message == "The goblin bleeds — finish it."
    assert report.actor_name == "Brix"
    recent = board.recent()
    assert len(recent) == 1
    assert recent[0].actor_name == "Brix"
    assert recent[0].text == "The goblin bleeds — finish it."
    assert recent[0].round_number >= 1


def test_rejected_and_fallback_turns_post_nothing() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    for _ in range(2):  # max_action_retries=1 -> 2 invalid decision attempts, both chatter
        fake.enqueue_structured(
            {
                "action_type": "attack",
                "target_id": "nobody",
                "public_message": "Who?",
                "party_message": "should never be posted",
            }
        )
    board = PartyMessageBoard()
    service = _agent_service(game_service, fake, max_action_retries=1, board=board)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.proposal_source == "fallback"
    assert board.recent() == ()


def _drive_to_actor(
    game_service: GameService,
    service: AgentTurnService,
    game_id: GameId,
    agent_ids: set[str],
    stop_actor_id: str,
    *,
    max_steps: int = 60,
) -> None:
    """Advance enemy/other-agent turns until stop_actor_id is the active actor."""
    for _ in range(max_steps):
        view = game_service.get_view(game_id)
        if view.status == "ended":
            raise AssertionError("combat ended before the target actor's turn")
        active = view.combat.active_actor_id if view.combat else None
        assert active is not None
        if active == stop_actor_id:
            return
        if active in agent_ids:
            service.take_turn(game_id, CharacterId(active))
        else:
            game_service.run_active_enemy_turns(game_id)
    raise AssertionError(f"{stop_actor_id} never became the active actor")


def test_agent_chatter_reaches_the_next_agent_prompt() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service, _rogue("Mira"))
    view = game_service.get_view(game_id)
    assert view.combat is not None
    mira_id = next(member.id for member in view.party if member.name == "Mira")
    mira_profile = AgentProfile(
        name="mira",
        character_name="Mira",
        character_class="rogue",
        persona="Opportunistic.",
        objective="Finish wounded foes.",
        model_profile="player",
        stats=_BRIX_STATS,  # stats are irrelevant to prompts; reuse to keep the test short
    )
    fake = _CapturingFake()

    def _decision() -> dict[str, str]:
        game_view = game_service.get_view(game_id)
        target = next(enemy for enemy in game_view.enemies if not enemy.is_defeated)
        return {
            "action_type": "attack",
            "target_id": target.id,
            "public_message": "I attack.",
            "party_message": "The goblin bleeds — finish it.",
        }

    service = _agent_service(
        game_service, ScriptedAgentGateway(fake, _decision), board=PartyMessageBoard()
    )
    service.register(brix_id, _BRIX)
    service.register(CharacterId(mira_id), mira_profile)

    # Brix acts first by helper contract; her message must reach Mira's prompt.
    _drive_to_actor(game_service, service, game_id, {brix_id.value, mira_id}, mira_id)
    report = service.take_turn(game_id, CharacterId(mira_id))
    assert report.accepted is True

    user_content = fake.requests[-1].messages[-1].content
    assert "Party chatter:" in user_content
    assert "Brix (round" in user_content
    assert "The goblin bleeds — finish it." in user_content


def test_full_four_agent_fight_completes() -> None:
    game_service = _game_service()
    game_id = game_service.create_game(CreateGameCommand(seed=7))
    agent_ids = {
        game_service.add_character(game_id, _fighter("Brix")).value,
        game_service.add_character(game_id, _rogue("Mira")).value,
        game_service.add_character(game_id, _cleric("Sera")).value,
    }
    game_service.add_character(game_id, _fighter("Arin"))
    game_service.add_character(game_id, _goblin("Goblin Scout"))
    game_service.add_character(game_id, _goblin("Goblin Skulker"))
    game_service.add_character(game_id, _orc())
    game_service.start_combat(game_id)

    def _decision() -> dict[str, str]:
        view = game_service.get_view(game_id)
        target = next(enemy for enemy in view.enemies if not enemy.is_defeated)
        return {
            "action_type": "attack",
            "target_id": target.id,
            "public_message": "I attack.",
            "party_message": "Focus the nearest foe.",
        }

    service = _agent_service(
        game_service, ScriptedAgentGateway(FakeModelGateway(), _decision)
    )
    for actor_id in agent_ids:
        service.register(CharacterId(actor_id), _BRIX)

    for _ in range(300):
        view = game_service.get_view(game_id)
        if view.status == "ended":
            break
        active = view.combat.active_actor_id if view.combat else None
        if active is None:
            break
        if active in agent_ids:
            service.take_turn(game_id, CharacterId(active))
        elif any(member.id == active for member in view.enemies):
            game_service.run_active_enemy_turns(game_id)
        else:
            target = next(enemy for enemy in view.enemies if not enemy.is_defeated)
            game_service.submit_action(
                SubmitActionCommand(
                    game_id=game_id,
                    actor_id=CharacterId(active),
                    action_type="attack",
                    target_id=CharacterId(target.id),
                )
            )

    assert game_service.get_view(game_id).status == "ended"
```

(Net +3 tests: 9 total in the file. The chatter pin is the multi-agent behavior
guarantee: one agent's accepted broadcast appears in another agent's next prompt.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/agents/test_agent_turn_service.py -q`
Expected: FAIL — `TypeError: AgentTurnService.__init__() got an unexpected keyword argument 'board'` (and missing `actor_name`/`party_message` attributes on the report).

- [ ] **Step 3: Implement**

Full rewrite of `src/application/agents/agent_turn_service.py`:

```python
"""The agent turn use case: decision-attempt loop over the model, fallback, reporting."""

from __future__ import annotations

from dataclasses import dataclass

from ai.agents.errors import AgentRuntimeError, AgentRuntimeMisconfiguredError
from ai.agents.runtime import AgentRuntime
from ai.models.profiles import ModelProfileCatalog
from ai.models.types import LLMInvocation
from application.agents.character_agent import (
    ATTACK_DECISION_SCHEMA,
    AgentDecision,
    CharacterAgent,
    InvalidAgentDecisionError,
)
from application.agents.party_board import PartyMessage, PartyMessageBoard
from application.agents.perception import (
    AgentNotInCombatError,
    AgentPerception,
    build_perception,
    first_living_opponent,
)
from application.agents.profiles import AgentProfile, AgentProfileCatalog
from application.commands import SubmitActionCommand
from application.game_service import GameService
from application.views import TurnReport
from domain.common.ids import CharacterId, GameId

_PARTY_CHATTER_LIMIT = 8


@dataclass(frozen=True)
class AgentTurnReport:
    actor_id: str
    actor_name: str
    accepted: bool
    proposal_source: str  # "model" | "fallback"
    action_attempts: int
    rejection_reasons: tuple[str, ...]
    fallback_reason: str | None
    public_message: str | None
    invocations: tuple[LLMInvocation, ...]
    turn_report: TurnReport
    party_message: str | None = None


class AgentNotRegisteredError(KeyError):
    """Raised when take_turn is called for an actor with no registered agent profile."""


class AgentTurnService:
    """Runs one agent-controlled turn: bounded decisions, engine validation, fallback."""

    def __init__(
        self,
        game_service: GameService,
        runtime: AgentRuntime,
        catalog: ModelProfileCatalog,
        agent_profiles: AgentProfileCatalog,
        *,
        max_action_retries: int | None = None,
        board: PartyMessageBoard | None = None,
    ) -> None:
        self._game_service = game_service
        self._runtime = runtime
        self._catalog = catalog
        self._max_action_retries = (
            max_action_retries
            if max_action_retries is not None
            else agent_profiles.max_action_retries
        )
        self._board = board if board is not None else PartyMessageBoard()
        self._agents: dict[str, AgentProfile] = {}

    def register(self, actor_id: CharacterId, profile: AgentProfile) -> None:
        self._agents[actor_id.value] = profile

    def is_agent_controlled(self, actor_id: CharacterId) -> bool:
        return actor_id.value in self._agents

    def take_turn(self, game_id: GameId, actor_id: CharacterId) -> AgentTurnReport:
        profile = self._agents.get(actor_id.value)
        if profile is None:
            raise AgentNotRegisteredError(actor_id.value)

        agent = CharacterAgent(profile)
        model_profile = self._catalog.get(profile.model_profile)
        invocations: list[LLMInvocation] = []
        rejection_reasons: list[str] = []
        rejection: str | None = None
        perception: AgentPerception | None = None

        for attempt in range(1, self._max_action_retries + 2):
            view = self._game_service.get_view(game_id)
            perception = build_perception(view, actor_id.value)
            try:
                response = self._runtime.decide_structured(
                    profile=model_profile,
                    system=agent.build_system_prompt(),
                    user=agent.build_user_prompt(
                        perception,
                        rejection=rejection,
                        party_messages=self._board.recent(_PARTY_CHATTER_LIMIT),
                    ),
                    schema=ATTACK_DECISION_SCHEMA,
                )
                invocations.append(response.invocation)
                decision = agent.map_decision(response.data, perception)
            except AgentRuntimeMisconfiguredError:
                raise
            except AgentRuntimeError as error:
                if error.last_invocation is not None:
                    invocations.append(error.last_invocation)
                rejection = f"model failure: {error}"
                rejection_reasons.append(rejection)
                continue
            except InvalidAgentDecisionError as error:
                rejection = str(error)
                rejection_reasons.append(rejection)
                continue

            turn_report = self._submit(game_id, actor_id, decision)
            if turn_report.accepted:
                if decision.party_message is not None:
                    self._board.post(
                        PartyMessage(
                            actor_name=perception.self_view.name,
                            text=decision.party_message,
                            round_number=perception.round_number,
                        )
                    )
                return AgentTurnReport(
                    actor_id=actor_id.value,
                    actor_name=perception.self_view.name,
                    accepted=True,
                    proposal_source="model",
                    action_attempts=attempt,
                    rejection_reasons=tuple(rejection_reasons),
                    fallback_reason=None,
                    public_message=decision.public_message,
                    invocations=tuple(invocations),
                    turn_report=turn_report,
                    party_message=decision.party_message,
                )
            rejection = turn_report.reason or "action rejected by the rules engine"
            rejection_reasons.append(rejection)

        assert perception is not None  # the loop always runs at least one attempt
        return self._fallback(
            game_id,
            actor_id,
            perception.self_view.name,
            invocations,
            tuple(rejection_reasons),
        )

    def _submit(
        self, game_id: GameId, actor_id: CharacterId, decision: AgentDecision
    ) -> TurnReport:
        return self._game_service.submit_action(
            SubmitActionCommand(
                game_id=game_id,
                actor_id=actor_id,
                action_type="attack",
                target_id=decision.proposal.target_id,
            )
        )

    def _fallback(
        self,
        game_id: GameId,
        actor_id: CharacterId,
        actor_name: str,
        invocations: list[LLMInvocation],
        rejection_reasons: tuple[str, ...],
    ) -> AgentTurnReport:
        view = self._game_service.get_view(game_id)
        target_id = first_living_opponent(view, actor_id.value)
        if target_id is None:
            raise AgentNotInCombatError(
                f"character {actor_id.value} has no living opponent to attack"
            )
        detail = "; ".join(rejection_reasons) if rejection_reasons else "no model decision"
        turn_report = self._game_service.submit_action(
            SubmitActionCommand(
                game_id=game_id,
                actor_id=actor_id,
                action_type="attack",
                target_id=CharacterId(target_id),
            )
        )
        return AgentTurnReport(
            actor_id=actor_id.value,
            actor_name=actor_name,
            accepted=turn_report.accepted,
            proposal_source="fallback",
            action_attempts=self._max_action_retries + 1,
            rejection_reasons=rejection_reasons,
            fallback_reason=f"decision budget exhausted ({detail})",
            public_message=None,
            invocations=tuple(invocations),
            turn_report=turn_report,
            party_message=None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/agents/test_agent_turn_service.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **307** offline tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/application/agents/agent_turn_service.py tests/application/agents/test_agent_turn_service.py
git commit -m "feat(application): route party chatter through the agent turn loop

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: CLI — wire the party, load the encounter, render by name

**Files:**
- Modify: `src/interfaces/cli/app.py` (exact edits below)
- Modify: `tests/interfaces/test_cli.py` (3 test updates + 1 new test)

**Interfaces:**
- Consumes: everything from Tasks 1–5; `load_encounter` from `application.encounter` (Task 3); `profile.stats` (Task 2); `report.actor_name`/`report.party_message` (Task 5).
- Produces: `_wire_party(service, game_id, mode, console) -> AgentTurnService` (replaces `_wire_agent`); `_goblin()` deleted; encounter loaded in `main()` in all modes. This completes the feature.

- [ ] **Step 1: Write the failing tests**

Edits to `tests/interfaces/test_cli.py`:

1a. In `test_main_full_fight_reaches_a_winner`, replace:

```python
    code = main(console=console, input_fn=_scripted(*(["attack goblin"] * 60)))
```

with:

```python
    lines = (
        ["attack goblin scout"] * 30,
        ["attack goblin skulker"] * 30,
        ["attack orc brute"] * 60,
    )
    code = main(console=console, input_fn=_scripted(*lines))
```

1b. In `test_main_agent_fake_plays_a_full_fight`, replace:

```python
        input_fn=_scripted(*(["attack goblin"] * 60)),
```

with:

```python
        input_fn=_scripted(*(["attack orc brute"] * 60)),
```

and replace:

```python
    assert "AI-controlled" in output
    assert "wins the combat" in output
```

with:

```python
    assert "Brix, Mira, Sera join the party" in output
    assert "AI-controlled" in output
    assert "wins the combat" in output
```

1c. In `test_main_agent_fake_agent_takes_a_turn`, replace:

```python
            input_fn=_scripted(*(["attack goblin"] * 60)),
```

with:

```python
            input_fn=_scripted(*(["attack orc brute"] * 60)),
```

and replace:

```python
        if "Agent:" in output:
            assert "wins the combat" in output
            assert "AI-controlled" in output
            return
```

with:

```python
        if "says:" in output:
            assert "Brix, Mira, Sera join the party" in output
            assert "wins the combat" in output
            assert "AI-controlled" in output
            return
```

1d. Append the new test:

```python
def test_main_all_enemy_names_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(
        console=console,
        input_fn=_scripted(
            "attack goblin scout", "attack goblin skulker", "attack orc brute", "/quit"
        ),
    )
    assert code == 0
    assert "No such character" not in buffer.getvalue()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/interfaces/test_cli.py -q`
Expected: FAIL — with the current single-goblin main, "attack goblin scout" prints "No such character: goblin scout", so `test_main_full_fight_reaches_a_winner` and `test_main_all_enemy_names_resolve` fail; the fake-mode tests fail on the missing announcement/chatter lines.

- [ ] **Step 3: Implement**

Edits to `src/interfaces/cli/app.py`:

3a. Add the encounter import — replace:

```python
from application.game_service import GameService
```

with (ruff isort order: `application.commands` < `application.encounter` < `application.game_service`):

```python
from application.encounter import load_encounter
from application.game_service import GameService
```

3b. **Delete** the entire `_goblin()` builder (from `def _goblin() -> AddCharacterCommand:` through its final `)` before `def _wire_agent(`).

3c. Replace `_wire_agent` with `_wire_party`:

```python
def _wire_party(
    service: GameService,
    game_id: GameId,
    mode: str,
    console: Console,
) -> AgentTurnService:
    """Wire the agent stack and add the AI party members before combat starts."""
    agent_profiles = load_agent_profiles(_CONFIG_DIR / "agents.toml")
    model_catalog = load_model_profiles(_CONFIG_DIR / "llm.toml")
    if mode == "llm":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set; export it to run with --agent llm")
        gateway = create_gateway(model_catalog.default_provider, api_key=api_key)
    else:
        fake = FakeModelGateway()

        def _decision() -> dict[str, str]:
            view = service.get_view(game_id)
            living = [enemy for enemy in view.enemies if not enemy.is_defeated]
            target = living[0] if living else view.enemies[0]
            return {
                "action_type": "attack",
                "target_id": target.id,
                "public_message": "I attack the nearest standing foe.",
                "party_message": "Focus the nearest standing foe.",
            }

        gateway = ScriptedAgentGateway(fake, _decision)
    runtime = AgentRuntime(gateway, RetryPolicy())
    agent_service = AgentTurnService(service, runtime, model_catalog, agent_profiles)
    names: list[str] = []
    for profile in agent_profiles.agents.values():
        stats = profile.stats
        character_id = service.add_character(
            game_id,
            AddCharacterCommand(
                name=profile.character_name,
                character_type="player",
                character_class=profile.character_class,
                strength=stats.strength,
                dexterity=stats.dexterity,
                constitution=stats.constitution,
                intelligence=stats.intelligence,
                wisdom=stats.wisdom,
                charisma=stats.charisma,
                armor_class=stats.armor_class,
                speed_ft=stats.speed_ft,
                max_hp=stats.max_hp,
                weapon=stats.weapon,
            ),
        )
        agent_service.register(character_id, profile)
        names.append(profile.character_name)
    console.print(
        f"[cyan]{', '.join(names)} join the party (AI-controlled, mode: {mode})[/cyan]"
    )
    return agent_service
```

3d. Replace `_render_agent_turn` with:

```python
def _render_agent_turn(console: Console, report: AgentTurnReport, view: GameView) -> None:
    if report.public_message:
        console.print(f"[cyan]{report.actor_name}:[/cyan] {report.public_message}")
    if report.party_message:
        console.print(f"[cyan]{report.actor_name} says:[/cyan] {report.party_message}")
    if report.proposal_source == "fallback" and report.fallback_reason:
        console.print(
            f"[yellow]Fell back to a deterministic attack: {report.fallback_reason}[/yellow]"
        )
    console.print(
        f"[dim]agent {report.actor_id} — source: {report.proposal_source}, "
        f"attempts: {report.action_attempts}, llm calls: {len(report.invocations)}[/dim]"
    )
    render_report(console, report.turn_report, view)
```

3e. In `main()`, replace the setup block:

```python
    game_id = service.create_game(CreateGameCommand(seed=args.seed))
    service.add_character(game_id, _fighter("Arin"))
    agent_service: AgentTurnService | None = None
    if args.agent != "off":
        try:
            agent_service = _wire_agent(service, game_id, args.agent, console)
        except (ValueError, ModelError) as error:
            console.print(f"[red]{error}[/red]")
            return 2
    service.add_character(game_id, _goblin())
    service.start_combat(game_id)
```

with:

```python
    game_id = service.create_game(CreateGameCommand(seed=args.seed))
    service.add_character(game_id, _fighter("Arin"))
    agent_service: AgentTurnService | None = None
    if args.agent != "off":
        try:
            agent_service = _wire_party(service, game_id, args.agent, console)
        except (ValueError, ModelError) as error:
            console.print(f"[red]{error}[/red]")
            return 2
    for enemy_command in load_encounter(_CONFIG_DIR / "encounter.toml"):
        service.add_character(game_id, enemy_command)
    service.start_combat(game_id)
```

(The main loop's agent branch needs no change — it already dispatches any registered actor.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/interfaces/test_cli.py -q`
Expected: PASS (11 passed)

- [ ] **Step 5: Quality gates + offline demo**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **308** offline tests pass. Manual check (no network):
`.venv/bin/python -m interfaces.cli.app --agent fake --seed 42 < /dev/null` prints
`Brix, Mira, Sera join the party`, shows the three-enemy encounter, and exits cleanly
on EOF (exit code 0).

- [ ] **Step 6: Commit**

```bash
git add src/interfaces/cli/app.py tests/interfaces/test_cli.py
git commit -m "feat(interfaces): wire the three-agent party and configured encounter

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: README + final verification

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: documentation matching shipped behavior.

- [ ] **Step 1: Update README.md**

Replace the section titled `## AI character agent (offline by default)` in its entirety with:

```markdown
## AI party (offline by default)

`--agent llm` adds three AI-controlled party members (Brix, Mira, Sera) who
decide their own attacks through the model gateway and coordinate through
party chatter; the human keeps commanding Arin:

```bash
export OPENROUTER_API_KEY=sk-or-...
.venv/bin/python -m interfaces.cli.app --agent llm --seed 42
```

An offline demo that never touches the network:

```bash
.venv/bin/python -m interfaces.cli.app --agent fake --seed 42
```

Agent identity, persona, objective, and statlines live in `config/agents.toml`;
the encounter lives in `config/encounter.toml` and is loaded in every mode;
retry budgets sit under `[agent]`. Agents may broadcast one short
`party_message` per accepted turn; the last 8 messages join every agent's
prompt. The agent proposes, the rules engine decides — invalid proposals are
retried with the rejection reason, then a deterministic fallback attack.
```

- [ ] **Step 2: Verify spec completion checklist items**

Run: `git log master..HEAD --oneline -- src/domain`
Expected: empty output (domain untouched).

Run: `git diff master --stat -- pyproject.toml uv.lock`
Expected: empty output (no dependency changes).

- [ ] **Step 3: Final quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **308** offline tests pass (**309** with `OPENROUTER_API_KEY` set).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document the AI party and configured encounter

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Final verification (after Task 7)

- [ ] Full suite green offline: `.venv/bin/python -m pytest -q` → 308 offline (+1 live when `OPENROUTER_API_KEY` is set).
- [ ] `git log master..HEAD --oneline -- src/domain` → empty; purity test (`tests/ai/agents/test_purity.py`) green.
- [ ] `--agent off`: zero agent output and zero agent turns; the encounter comes from `config/encounter.toml` in all modes.
- [ ] Party size and encounter size are configuration only — no agent or enemy statline in CLI code.
- [ ] Chatter posts only after accepted model turns; rejected/fallback turns post nothing (pinned).
- [ ] One agent's message appears in another agent's prompt (pinned); enemy HP/AC never in any prompt (pinned).
- [ ] Every agent independently bounded: transport retries, decision attempts, deterministic fallback.
- [ ] No provider SDK outside `src/infrastructure/llm/`; no new dependencies.
- [ ] Offline demo: `.venv/bin/python -m interfaces.cli.app --agent fake --seed 42` plays the 4-party × 3-enemy fight to completion.
