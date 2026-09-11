# Evaluation Framework (Phase 18) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scripted scenarios drive real game sessions through the application layer and report a core metric set — legal-action rate, rejections, retries, latency, tokens/game, cost/game — plus scenario checks for instruction fidelity, cross-run consistency, and cooperation, as JSON files and a `conclave-eval` console table.

**Architecture:** A new top-level `src/session/` composition package (extracted from the CLI: `factory.py` wires everything, `play.py` drives turns and input) is shared by the CLI and the new `src/evaluation/` package. The runner opens fresh sessions per run, drives scenario steps through `advance`/`apply_input`, snapshots domain events + enriched invocations + party traffic, computes metrics, evaluates checks, and writes JSON reports. Evaluation contains no game rules and mutates state only through application services (§71: LLMs propose, the domain decides).

**Tech Stack:** Python 3.12 stdlib only for evaluation (dataclasses, json, collections, math, datetime, pathlib); Rich (already a dependency) for the two CLIs; pgserver fixtures (already present) for the postgres-mode test. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-10-evaluation-design.md` — the plan argues from the spec; executors read both. The spec was amended during planning (session package placement, scenario ground truth, the sanctioned initiative-determinism fix); this plan implements the amended text.

**Roadmap:** `docs/superpowers/plans/README.md` row #9 (Phase 18).

## Global Constraints

These apply to every task; each task's requirements implicitly include them.

- **Core invariant** (§65/§66/§71): evaluation measures behavior and never relaxes rules. It mutates game state only through application services; `src/evaluation/` contains zero rules logic; domain events are read as data.
- **Domain diff — exactly one sanctioned commit**: `git log master..HEAD -- src/domain` must show exactly one commit, Task 1's `roll_initiative` determinism fix (random-uuid tiebreak violated §47 reproducibility; the fix is a stable sort on `(-total, -dexterity_modifier)`). No other domain changes. Verify in Task 8.
- **Secrets and privacy** (§34, §48, §50): API keys come from env vars only (`OPENROUTER_API_KEY`, `DATABASE_URL`); never commit them. Reports, event summaries, and invocation summaries never contain prompts, payloads, API keys, or chain-of-thought.
- **Evaluation never gates the game** (same spirit as telemetry): a failed check is recorded `passed=false`; an exception inside a run marks that `ScenarioResult` `"error"` and the loop continues; only harness misuse raises `EvaluationError`.
- **Offline-first** (§46): the full suite passes with `OPENROUTER_API_KEY` empty. Live evaluation is a manual, env-gated `--provider openrouter` invocation; no new `live`-marked tests.
- **Rich only where rendering happens**: `src/evaluation/cli.py` and `src/interfaces/cli/` — never in the runner, metrics, model, or report modules.
- **Type/lint gates**: `ruff check .` clean (line-length 100, select E/F/I/UP/B), `mypy` strict clean on `src` (tests are not type-checked). One alphabetical import block per file — stdlib, then `ai` < `application` < `domain` < `evaluation` < `infrastructure` < `interfaces` < `session`.
- **Baseline** (verified 2026-09-10 on master `b574176`): `OPENROUTER_API_KEY= .venv/bin/python -m pytest -q` → **425 passed, 2 deselected**. Each task gate below projects the exact total after that task: 426 → 440 → 443 → 455 → 460 → 463 → 467 → **470 passed, 2 deselected** (final).
- **Gate pattern** — always `set -o pipefail` first (a masked exit code once committed failing code):

```bash
set -o pipefail
V=$PWD/.venv/bin/python
$V -m pytest <test files> -q | tail -1
$V -m ruff check .
$V -m mypy | tail -1
OPENROUTER_API_KEY= $V -m pytest -q | tail -1
```

- **CLI behavior is byte-identical after Task 2**: `tests/interfaces/test_cli.py` is the contract and must not be modified by any task. Exact strings it asserts: `from interfaces.cli.app import main, parse_input` and `from interfaces.cli.app import build_service` must keep working; `build_service("postgres")` without `DATABASE_URL` raises `ValueError` matching `DATABASE_URL`; unknown backend raises `ValueError` matching `unknown database backend`; console output keeps `"Brix, Mira, Sera join the party (AI-controlled, mode: fake)"`, `"No such character: X"`, `"The GM is off — run with --gm fake or --gm llm to talk."`, `"Unknown input — try: attack <target>"` and every other existing assertion.
- **Worktree sandbox** (recorded in session memory): plain commands only — no `printf |` into python, no env-var prefix on `python -c`. Env-prefixed pytest (`OPENROUTER_API_KEY= pytest`) is accepted. `EnterWorktree` branches from `origin/master`; local `master` is ahead (the spec + plan commits). On first entry run `git merge master --ff-only` inside the worktree.
- **Commits**: conventional, scoped by layer; every message ends with `Co-Authored-By: Claude Code <noreply@anthropic.com>`.

## File Structure

| File | Responsibility |
|---|---|
| `src/domain/combat/state.py` | Task 1: `roll_initiative` stable tie-break (the only domain change) |
| `src/session/__init__.py` | Re-exports the composition root's public surface |
| `src/session/factory.py` | `SessionConfig`, `GameSession`, `build_service`, `build_session`, `open_session` — wiring only |
| `src/session/play.py` | `parse_input`, `advance`, `apply_input`, `PendingTurn`, `InputOutcome` — the session engine |
| `src/interfaces/cli/app.py` | Slimmed CLI: rendering, `/commands`, REPL; re-exports `parse_input`/`build_service` |
| `src/evaluation/__init__.py` | package docstring |
| `src/evaluation/errors.py` | `EvaluationError` |
| `src/evaluation/model.py` | `Scenario`, `ScenarioCheck`, `CheckResult`, `RunRecord`, `EventSummary`, `InvocationSummary`, `ScenarioResult` |
| `src/evaluation/scenarios/__init__.py` | `SCENARIOS` registry + `get_scenario` |
| `src/evaluation/scenarios/goblin_skirmish.py` | Task 3 scenario + its checks |
| `src/evaluation/scenarios/instruction_following.py` | Task 8 scenario + its checks |
| `src/evaluation/scenarios/cooperation_smoke.py` | Task 8 scenario + its checks |
| `src/evaluation/metrics.py` | `compute_metrics(result) -> Metrics` (§4.5, `None` when not computable) |
| `src/evaluation/runner.py` | `run_scenario(...)` — per-run fresh sessions, event/invocation summaries |
| `src/evaluation/report.py` | `write_report(result, out_dir) -> Path` |
| `src/evaluation/cli.py` | `conclave-eval` argparse + Rich table + exit codes |
| `src/infrastructure/telemetry/in_memory.py` | Task 3: public `invocations()` accessor |
| `pyproject.toml` | Task 7: `conclave-eval` script entry |
| `.gitignore` | Task 6: `eval-results/` |
| `tests/domain/test_combat.py` | Task 1 tests |
| `tests/session/test_factory.py`, `tests/session/test_play.py` | Task 2 tests |
| `tests/evaluation/test_scenarios.py`, `test_metrics.py`, `test_runner.py`, `test_report.py`, `test_cli.py`, `test_offline_scenarios.py` | Tasks 3–8 tests |
| `tests/infrastructure/telemetry/test_in_memory_sink.py` | Task 3 accessor test |
| `README.md`, `docs/superpowers/plans/README.md` | Task 8: evaluation docs, row #9 → Complete |

---

### Task 1: Deterministic initiative tie-break (the one sanctioned domain change)

**Files:**
- Modify: `src/domain/combat/state.py:50-56` (the `entries.sort(...)` call in `roll_initiative`)
- Test: `tests/domain/test_combat.py`

**Interfaces:**
- Consumes: `roll_initiative(dice, characters, participant_ids) -> list[InitiativeEntry]` (signature unchanged; `InitiativeEntry.tiebreaker` stays recorded-but-unused, exactly as today).
- Produces: initiative order deterministic per seed — ties on `(total, dexterity_modifier)` resolve by participant order (Python's stable sort) instead of the random `character_id.value` uuid. All later tasks rely on same-seed runs producing identical event sequences.

- [ ] **Step 1: Write the failing tie test**

Append to `tests/domain/test_combat.py` (the module already has `_fighter` and `_seed_with_rolls` helpers):

```python
def test_initiative_ties_preserve_participant_order() -> None:
    first = _fighter("First")
    second = _fighter("Second")
    characters = {first.id: first, second.id: second}
    order = [first.id, second.id]
    seed = _seed_with_rolls([7, 7])  # equal naturals, equal dex mods (+1 each)

    entries = roll_initiative(DiceRoller(seed=seed), characters, order)

    assert [entry.character_id for entry in entries] == order
    assert entries[0].total == entries[1].total == 8
```

- [ ] **Step 2: Run the test to verify it is flaky-failing**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/domain/test_combat.py::test_initiative_ties_preserve_participant_order -q`
Expected: FAIL (intermittently — the current sort tiebreaks on a random uuid4, so the assertion flips between runs). If it happens to pass, re-run until it fails; if it passes 5 times in a row, proceed anyway — the next step makes it deterministic by construction.

- [ ] **Step 3: Fix the sort**

In `src/domain/combat/state.py`, replace the sort inside `roll_initiative` (currently sorting on `(-total, -dexterity_modifier, character_id.value)`) with:

```python
    # Ties on (total, dexterity modifier) keep participant order: the sort is
    # stable, so no random id is needed as a tiebreak (§47 reproducibility).
    entries.sort(key=lambda entry: (-entry.total, -entry.dexterity_modifier))
```

- [ ] **Step 4: Update the existing test's mirror sort for fidelity**

In `tests/domain/test_combat.py`, `test_initiative_orders_by_total_then_dex_modifier` (~line 102) keeps passing, but its expected-order mirror still models the uuid tiebreak. Change its ranking key from:

```python
        key=lambda entry: (-(entry[1] + entry[2]), -entry[2], str(entry[0])),
```

to:

```python
        key=lambda entry: (-(entry[1] + entry[2]), -entry[2]),
```

(the two participants have distinct dex modifiers, so this test never reaches the tiebreak — only the mirror's fidelity changes).

- [ ] **Step 5: Run the domain tests**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/domain/test_combat.py -q`
Expected: PASS (all, including the updated mirror test and the new tie test).

- [ ] **Step 6: Run the full offline gate**

Run the Global-Constraints gate pattern with all tests. Expected: **426 passed, 2 deselected** (baseline + the new tie test; no other outcome changes — verified by probe before planning).

- [ ] **Step 7: Commit**

```bash
git add src/domain/combat/state.py tests/domain/test_combat.py
git commit -m "fix(domain): break initiative ties by participant order, not random ids

roll_initiative sorted (total, dexterity_modifier) ties by
character_id.value - a random uuid4 - so two same-seed sessions could
diverge in turn order, violating CLAUDE.md 47 (the engine is
deterministic even when the LLM is not). Python's stable sort keeps
participant order without any id tiebreak; the recorded tiebreaker
field is unchanged.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: The `src/session/` composition package (extracted from the CLI)

**Files:**
- Create: `src/session/__init__.py`, `src/session/factory.py`, `src/session/play.py`
- Modify: `src/interfaces/cli/app.py` (rewrite: rendering + REPL only)
- Test: `tests/session/test_factory.py`, `tests/session/test_play.py` (new); `tests/interfaces/test_cli.py` untouched (the contract)

**Interfaces:**
- Consumes (existing, unchanged): `GameService` (`create_game`, `add_character`, `start_combat`, `run_active_enemy_turns`, `submit_action`, `get_view`, `get_events`), `AgentTurnService` (`take_turn`, `is_agent_controlled`, `register`; accepts `board=`), `GmDirector` (`on_combat_open` → `GmResult`, `on_turn_report` → `GmResult | None`, `on_player_say` → `GmResult`), `load_encounter(path) -> tuple[AddCharacterCommand, ...]`, `AgentRuntime(gateway, RetryPolicy())`, `ModelGateway` protocol at `ai.models.gateway`, `ScriptedAgentGateway(inner, decision)` / `ScriptedGmGateway(inner, decision)`, `PartyMessageBoard` (`application.agents.party_board`), `CompositeTelemetrySink`, `InMemoryTelemetrySink`, `LoggingTelemetrySink`, `PostgresTelemetrySink`, `create_gateway`/`create_embedding_gateway`.
- Produces (consumed by Tasks 3, 5, 6 and the CLI):
  - `SessionConfig(seed: int = 42, db: str = "memory", agent_mode: str | None = None, gm_mode: str = "off", gateway: ModelGateway | None = None, provider: str | None = None)` — frozen dataclass; `agent_mode=None` is the CLI's `"off"`.
  - `GameSession(game_service, game_id: GameId, telemetry: InMemoryTelemetrySink, party_board: PartyMessageBoard, party_names: tuple[str, ...], turn_service: AgentTurnService | None, gm_director: GmDirector | None, opening: GmResult | None = None)` — frozen dataclass.
  - `build_service(db: str = "memory") -> GameService` — moved verbatim (same `DATABASE_URL` / unknown-backend errors).
  - `build_session(config) -> GameSession`; `open_session(config) -> GameSession` (adds the GM combat-open narration).
  - `parse_input(raw: str) -> tuple[str, str]` — moved verbatim.
  - `advance(session) -> PendingTurn | None` — `PendingTurn(kind: str  # "enemy" | "agent", turn_report: TurnReport, agent_report: AgentTurnReport | None = None, gm_result: GmResult | None = None)`.
  - `apply_input(session, raw: str) -> InputOutcome` — `InputOutcome(kind: str  # "empty"|"command"|"unknown"|"attack"|"say"|"no_target"|"error", argument: str = "", turn_report: TurnReport | None = None, gm_result: GmResult | None = None, error: str | None = None)`.
  - `CONFIG_DIR: Path` — the repo's `config/` directory (reused by Task 5's runner).
  - `main` loses its unused `service` parameter (no caller passed it — grep-verified); everything else about `main` is byte-identical.

- [ ] **Step 1: Write the factory tests**

Create `tests/session/test_factory.py`:

```python
# tests/session/test_factory.py
"""Session composition-root tests (spec §4.1): wiring, opening, postgres."""

import pytest

from session import SessionConfig, build_session, open_session


def test_build_session_memory_wires_the_full_fight() -> None:
    session = build_session(SessionConfig(seed=42, agent_mode="fake"))

    assert session.game_id is not None
    assert session.party_names == ("Brix", "Mira", "Sera")
    assert session.turn_service is not None
    assert session.party_board is not None
    view = session.game_service.get_view(session.game_id)
    assert len(view.party) == 4  # Arin + the three agents
    assert [enemy.name for enemy in view.enemies] == [
        "Goblin Scout",
        "Goblin Skulker",
        "Orc Brute",
    ]
    assert view.combat is not None and view.combat.status == "active"


def test_build_session_agent_off_has_an_empty_party() -> None:
    session = build_session(SessionConfig(seed=42))

    assert session.party_names == ()
    assert session.turn_service is None


def test_build_session_gm_off_has_no_director_or_opening() -> None:
    session = open_session(SessionConfig(seed=42, gm_mode="off"))

    assert session.gm_director is None
    assert session.opening is None


def test_open_session_stores_the_opening_narration() -> None:
    session = open_session(SessionConfig(seed=42, agent_mode="fake", gm_mode="fake"))

    assert session.opening is not None
    assert session.opening.narration == (
        "Two goblins and an orc brute block the pass. The fight begins."
    )


def test_build_session_postgres_requires_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="DATABASE_URL"):
        build_session(SessionConfig(db="postgres"))


def test_build_session_postgres_round_trip(postgres_url) -> None:
    session = build_session(SessionConfig(seed=42, db="postgres"))

    view = session.game_service.get_view(session.game_id)
    assert view.status == "running"
    assert view.combat is not None


def test_build_session_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="unknown database backend"):
        build_session(SessionConfig(db="oracle"))
```

- [ ] **Step 2: Run the factory tests to verify they fail**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/session/test_factory.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'session'`

- [ ] **Step 3: Write the play tests**

Create `tests/session/test_play.py`:

```python
# tests/session/test_play.py
"""advance/apply_input engine tests (spec §4.1): the CLI loop's semantics."""

from session import SessionConfig, advance, apply_input, open_session


def _drain(session) -> list:
    pendings = []
    while (pending := advance(session)) is not None:
        pendings.append(pending)
    return pendings


def test_advance_drains_until_a_human_turn() -> None:
    session = open_session(SessionConfig(seed=42))

    _drain(session)

    view = session.game_service.get_view(session.game_id)
    assert view.status == "running"
    assert view.combat is not None and view.combat.status == "active"
    actor = view.combat.active_actor_id
    assert actor is not None
    assert all(member.id != actor for member in view.enemies)


def test_advance_drives_agent_turns_and_party_chatter() -> None:
    session = open_session(SessionConfig(seed=42, agent_mode="fake", gm_mode="fake"))

    seen_agent = False
    while True:
        pending = advance(session)
        if pending is None or pending.kind == "agent":
            seen_agent = pending is not None
            break
    assert seen_agent
    assert session.party_board.recent(limit=8)


def test_apply_input_attack_resolves_target() -> None:
    session = open_session(SessionConfig(seed=42))
    _drain(session)

    outcome = apply_input(session, "attack goblin scout")

    assert outcome.kind == "attack"
    assert outcome.turn_report is not None
    assert outcome.turn_report.accepted is True
    assert outcome.gm_result is None  # GM off on this session


def test_apply_input_unknown_target_submits_nothing() -> None:
    session = open_session(SessionConfig(seed=42))
    _drain(session)
    before = len(session.game_service.get_events(session.game_id))

    outcome = apply_input(session, "attack balrog")

    assert outcome.kind == "no_target"
    assert outcome.turn_report is None
    after = len(session.game_service.get_events(session.game_id))
    assert before == after  # no state change


def test_apply_input_say_with_gm_off_records_no_result() -> None:
    session = open_session(SessionConfig(seed=42, gm_mode="off"))
    _drain(session)

    outcome = apply_input(session, "say hold the line")

    assert outcome.kind == "say"
    assert outcome.gm_result is None


def test_apply_input_say_with_gm_fake_returns_reaction() -> None:
    session = open_session(SessionConfig(seed=42, agent_mode="fake", gm_mode="fake"))
    _drain(session)

    outcome = apply_input(session, "say hold the line")

    assert outcome.kind == "say"
    assert outcome.gm_result is not None
    assert outcome.gm_result.npc_reply == "Talk is for the weak. Say your last words!"


def test_apply_input_passthrough_kinds() -> None:
    session = open_session(SessionConfig(seed=42))
    _drain(session)

    quit_outcome = apply_input(session, "/quit")
    assert quit_outcome.kind == "command"
    assert quit_outcome.argument == "/quit"
    unknown = apply_input(session, "dance")
    assert unknown.kind == "unknown"
    assert unknown.argument == "dance"
    assert apply_input(session, "   ").kind == "empty"
```

- [ ] **Step 3b: Run the play tests to verify they fail**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/session/test_play.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'session'` (same reason as Step 2)

- [ ] **Step 4: Create the session package**

Create `src/session/factory.py`:

```python
"""Session composition root: wiring only, no rules, no rendering (spec §4.1).

Extracted from interfaces/cli/app.py with contracts preserved. Lives in a
top-level package because a composition root must import infrastructure, and
the application layer stays infrastructure-free (CLAUDE.md §4).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.memory.fake import DeterministicEmbeddingGateway
from ai.memory.ports import EmbeddingGateway, MemoryRepository
from ai.models.fake import FakeModelGateway
from ai.models.gateway import ModelGateway
from ai.models.profiles import load_model_profiles
from application.agents.agent_turn_service import AgentTurnService
from application.agents.fake_script import ScriptedAgentGateway, ScriptedGmGateway
from application.agents.party_board import PartyMessageBoard
from application.agents.profiles import load_agent_profiles
from application.commands import AddCharacterCommand, CreateGameCommand, WeaponSpec
from application.encounter import load_encounter
from application.game_service import GameService
from application.gm.conversation import GmConversation
from application.gm.director import GmDirector, GmResult
from application.gm.profiles import load_gm_profile
from application.memory.memory_service import MemoryService
from application.telemetry import (
    CompositeTelemetrySink,
    TelemetrySink,
    new_correlation_id,
)
from domain.common.ids import GameId
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.llm import create_embedding_gateway, create_gateway
from infrastructure.memory.in_memory import InMemoryMemoryRepository
from infrastructure.memory.pgvector_repository import PgvectorMemoryRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository
from infrastructure.persistence.postgres.connection import connect
from infrastructure.persistence.postgres.migrate import run_migrations
from infrastructure.persistence.postgres.repository import (
    PostgresEventRepository,
    PostgresGameRepository,
)
from infrastructure.telemetry.in_memory import InMemoryTelemetrySink
from infrastructure.telemetry.logging_sink import LoggingTelemetrySink
from infrastructure.telemetry.postgres import PostgresTelemetrySink

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@dataclass(frozen=True)
class SessionConfig:
    """Everything a caller chooses about a session; wiring stays in the factory."""

    seed: int = 42
    db: str = "memory"  # "memory" | "postgres" (DATABASE_URL from the environment)
    agent_mode: str | None = None  # None ("off") | "fake" | "llm"
    gm_mode: str = "off"  # "off" | "fake" | "llm"
    gateway: ModelGateway | None = None  # overrides the built gateway in every mode
    provider: str | None = None  # provider override for llm modes


@dataclass(frozen=True)
class GameSession:
    """One wired, started game plus the handles a driver needs to run it."""

    game_service: GameService
    game_id: GameId
    telemetry: InMemoryTelemetrySink
    party_board: PartyMessageBoard
    party_names: tuple[str, ...]
    turn_service: AgentTurnService | None
    gm_director: GmDirector | None
    opening: GmResult | None = None


def build_service(db: str = "memory") -> GameService:
    """Wire the application layer onto a persistence backend (spec §8)."""
    if db == "memory":
        event_store = InMemoryEventRepository()
        return GameService(InMemoryGameRepository(event_store), event_store)
    if db == "postgres":
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise ValueError(
                "DATABASE_URL is not set; copy .env.example and configure it "
                "to run with --db postgres"
            )
        run_migrations(database_url)
        connection = connect(database_url)
        return GameService(
            PostgresGameRepository(connection),
            PostgresEventRepository(connection),
        )
    raise ValueError(f"unknown database backend: {db!r}")


def _memory_repository(db: str) -> MemoryRepository:
    """Choose the memory backend alongside the game persistence backend (spec §3.6)."""
    if db == "memory":
        return InMemoryMemoryRepository()
    if db == "postgres":
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise ValueError(
                "DATABASE_URL is not set; copy .env.example and configure it "
                "to run with --db postgres"
            )
        return PgvectorMemoryRepository(connect(database_url))
    raise ValueError(f"unknown database backend: {db!r}")


def _gm_decision(prompt: str) -> dict[str, str]:
    """Deterministic GM responses for fake mode, keyed off the task marker (§3.7)."""
    if "Task: respond_to_player" in prompt:
        return {
            "narration": "The orc shifts its grip on the greataxe and considers you.",
            "npc_reply": "Talk is for the weak. Say your last words!",
            "addressed_to": "Orc Brute",
        }
    if "Task: react_to_events" in prompt:
        return {"narration": "Steel rings through the ravine as another foe falls."}
    return {"narration": "Two goblins and an orc brute block the pass. The fight begins."}


def _fighter(name: str) -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="player",
        character_class="fighter",
        level=1,
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


def _wire_gm(
    service: GameService, config: SessionConfig, telemetry: TelemetrySink
) -> GmDirector:
    """Wire the GM director off the shipped gm.toml persona (spec D9)."""
    profile = load_gm_profile(CONFIG_DIR / "gm.toml")
    model_catalog = load_model_profiles(CONFIG_DIR / "llm.toml")
    gateway: ModelGateway
    if config.gm_mode == "llm":
        if config.gateway is not None:
            gateway = config.gateway
        else:
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY is not set; export it to run with --gm llm"
                )
            gateway = create_gateway(
                config.provider or model_catalog.default_provider, api_key=api_key
            )
    else:
        inner = config.gateway if config.gateway is not None else FakeModelGateway()
        gateway = ScriptedGmGateway(inner, _gm_decision)
    runtime = AgentRuntime(gateway, RetryPolicy())
    return GmDirector(
        service, runtime, model_catalog, profile, GmConversation(), telemetry=telemetry
    )


def _wire_party(
    service: GameService,
    game_id: GameId,
    config: SessionConfig,
    board: PartyMessageBoard,
    telemetry: TelemetrySink,
) -> tuple[AgentTurnService, tuple[str, ...]]:
    """Wire the agent stack and add the AI party members before combat starts."""
    agent_profiles = load_agent_profiles(CONFIG_DIR / "agents.toml")
    model_catalog = load_model_profiles(CONFIG_DIR / "llm.toml")
    api_key: str | None = None
    if config.agent_mode == "llm":
        if config.gateway is not None:
            gateway = config.gateway
        else:
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY is not set; export it to run with --agent llm"
                )
            gateway = create_gateway(
                config.provider or model_catalog.default_provider, api_key=api_key
            )
    else:
        inner = config.gateway if config.gateway is not None else FakeModelGateway()

        def _decision() -> dict[str, str]:
            view = service.get_view(game_id)
            living = [enemy for enemy in view.enemies if not enemy.is_defeated]
            target = living[0] if living else view.enemies[0]
            return {
                "action_type": "attack",
                "target_id": target.id,
                "public_message": "I attack the nearest standing foe.",
                "party_message": "Focus the nearest standing foe.",
                "memory_note": "The orc hits hard; stay at range.",
            }

        gateway = ScriptedAgentGateway(inner, _decision)
    embedding_profile = model_catalog.get("embedding")
    embedder: EmbeddingGateway
    if api_key is not None:
        embedder = create_embedding_gateway(embedding_profile.provider, api_key=api_key)
    else:
        embedder = DeterministicEmbeddingGateway()
    memory = MemoryService(
        embedder,
        _memory_repository(config.db),
        model=embedding_profile.model,
        telemetry=telemetry,
    )
    runtime = AgentRuntime(gateway, RetryPolicy())
    agent_service = AgentTurnService(
        service,
        runtime,
        model_catalog,
        agent_profiles,
        board=board,
        memory=memory,
        telemetry=telemetry,
    )
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
    # No join line here: rendering belongs to the caller, which reads party_names.
    return agent_service, tuple(names)


def build_session(config: SessionConfig) -> GameSession:
    """Wire a full combat-ready session (spec §4.1); rendering stays with callers."""
    in_memory = InMemoryTelemetrySink()
    sinks: list[TelemetrySink] = [LoggingTelemetrySink(), in_memory]
    if config.db == "postgres":
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            sinks.append(PostgresTelemetrySink(connect(database_url)))
    telemetry: TelemetrySink = CompositeTelemetrySink(sinks)

    service = build_service(config.db)
    game_id = service.create_game(CreateGameCommand(seed=config.seed))
    service.add_character(game_id, _fighter("Arin"))

    board = PartyMessageBoard()
    turn_service: AgentTurnService | None = None
    party_names: tuple[str, ...] = ()
    if config.agent_mode is not None:
        turn_service, party_names = _wire_party(service, game_id, config, board, telemetry)

    gm_director: GmDirector | None = None
    if config.gm_mode != "off":
        gm_director = _wire_gm(service, config, telemetry)

    for enemy_command in load_encounter(CONFIG_DIR / "encounter.toml"):
        service.add_character(game_id, enemy_command)
    service.start_combat(game_id)
    return GameSession(
        game_service=service,
        game_id=game_id,
        telemetry=in_memory,
        party_board=board,
        party_names=party_names,
        turn_service=turn_service,
        gm_director=gm_director,
    )


def open_session(config: SessionConfig) -> GameSession:
    """build_session plus the GM's combat-open narration; ready for input."""
    session = build_session(config)
    if session.gm_director is None:
        return session
    opening = session.gm_director.on_combat_open(
        session.game_id, correlation_id=new_correlation_id()
    )
    return replace(session, opening=opening)
```

Create `src/session/play.py`:

```python
"""Session play engine: drive non-player turns and apply human input (spec §4.1)."""

from __future__ import annotations

from dataclasses import dataclass

from application.agents.agent_turn_service import AgentTurnReport
from application.commands import SubmitActionCommand
from application.gm.director import GmResult
from application.telemetry import new_correlation_id
from application.views import GameView, TurnReport
from domain.common.errors import DomainError
from domain.common.ids import CharacterId
from session.factory import GameSession


@dataclass(frozen=True)
class PendingTurn:
    """One driven non-player turn, ready for the caller to render."""

    kind: str  # "enemy" | "agent"
    turn_report: TurnReport
    agent_report: AgentTurnReport | None = None
    gm_result: GmResult | None = None


@dataclass(frozen=True)
class InputOutcome:
    """The effect of one human input line, for the caller to render."""

    kind: str  # "empty"|"command"|"unknown"|"attack"|"say"|"no_target"|"error"
    argument: str = ""
    turn_report: TurnReport | None = None
    gm_result: GmResult | None = None
    error: str | None = None


def parse_input(raw: str) -> tuple[str, str]:
    """Classify one raw input line (moved verbatim from interfaces.cli.app)."""
    stripped = raw.strip()
    if not stripped:
        return ("empty", "")
    if stripped.startswith("/"):
        return ("command", stripped)
    parts = stripped.split(None, 1)
    if parts[0].lower() == "attack" and len(parts) == 2:
        return ("attack", parts[1].strip())
    if parts[0].lower() == "say" and len(parts) == 2:
        return ("say", parts[1].strip())
    return ("unknown", stripped)


def _resolve_target(view: GameView, token: str) -> str | None:
    for member in (*view.party, *view.enemies):
        if member.id == token or member.name.lower() == token.lower():
            return member.id
    return None


def _is_enemy(view: GameView, character_id: str) -> bool:
    return any(member.id == character_id for member in view.enemies)


def _gm_react(
    session: GameSession, report: TurnReport, *, correlation_id: str
) -> GmResult | None:
    """React to a finished turn; None when the GM is off or nothing is notable."""
    if session.gm_director is None:
        return None
    return session.gm_director.on_turn_report(
        session.game_id, report, correlation_id=correlation_id
    )


def advance(session: GameSession) -> PendingTurn | None:
    """Drive non-player turns until it is the human's turn or the fight is over.

    Exceptions propagate: the CLI catches DomainError on the agent path exactly
    as today, and the evaluation runner converts them to "error" status.
    """
    service = session.game_service
    view = service.get_view(session.game_id)
    if view.status == "ended":
        return None
    combat = view.combat
    if combat is None or combat.status != "active":
        return None
    actor = combat.active_actor_id
    if actor is None:
        return None
    if _is_enemy(view, actor):
        report = service.run_active_enemy_turns(session.game_id)
        gm_result = _gm_react(session, report, correlation_id=new_correlation_id())
        return PendingTurn(kind="enemy", turn_report=report, gm_result=gm_result)
    if session.turn_service is not None and session.turn_service.is_agent_controlled(
        CharacterId(actor)
    ):
        correlation_id = new_correlation_id()
        agent_report = session.turn_service.take_turn(
            session.game_id, CharacterId(actor), correlation_id=correlation_id
        )
        gm_result = _gm_react(
            session, agent_report.turn_report, correlation_id=correlation_id
        )
        return PendingTurn(
            kind="agent",
            turn_report=agent_report.turn_report,
            agent_report=agent_report,
            gm_result=gm_result,
        )
    return None


def apply_input(session: GameSession, raw: str) -> InputOutcome:
    """Translate one human input into engine work; the caller renders the outcome."""
    kind, argument = parse_input(raw)
    if kind in ("empty", "command", "unknown"):
        return InputOutcome(kind=kind, argument=argument)
    view = session.game_service.get_view(session.game_id)
    if kind == "say":
        if session.gm_director is None:
            return InputOutcome(kind="say", argument=argument)
        gm_result = session.gm_director.on_player_say(
            session.game_id, argument, correlation_id=new_correlation_id()
        )
        return InputOutcome(kind="say", argument=argument, gm_result=gm_result)
    target_id = _resolve_target(view, argument)
    if target_id is None:
        return InputOutcome(kind="no_target", argument=argument)
    actor_id = view.combat.active_actor_id if view.combat else None
    if actor_id is None:
        return InputOutcome(kind="attack", argument=argument)
    try:
        report = session.game_service.submit_action(
            SubmitActionCommand(
                game_id=session.game_id,
                actor_id=CharacterId(actor_id),
                action_type="attack",
                target_id=CharacterId(target_id),
            )
        )
    except DomainError as error:
        return InputOutcome(kind="error", argument=argument, error=str(error))
    gm_result = _gm_react(session, report, correlation_id=new_correlation_id())
    return InputOutcome(
        kind="attack", argument=argument, turn_report=report, gm_result=gm_result
    )
```

Create `src/session/__init__.py`:

```python
"""Session composition root shared by the CLI, evaluation, and future adapters (§63)."""

from session.factory import (
    CONFIG_DIR,
    GameSession,
    SessionConfig,
    build_service,
    build_session,
    open_session,
)
from session.play import (
    InputOutcome,
    PendingTurn,
    advance,
    apply_input,
    parse_input,
)

__all__ = [
    "CONFIG_DIR",
    "GameSession",
    "InputOutcome",
    "PendingTurn",
    "SessionConfig",
    "advance",
    "apply_input",
    "build_service",
    "build_session",
    "open_session",
    "parse_input",
]
```

- [ ] **Step 5: Run the session tests**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/session -q`
Expected: **14 passed** (7 factory + 7 play; the postgres round-trip test self-skips only if pgserver is unavailable, matching existing behavior — if it skips on your machine the total reports as 13 passed, 1 skipped).

- [ ] **Step 6: Rewrite the CLI onto the session package**

Replace `src/interfaces/cli/app.py` in full with:

```python
"""CLI adapter — renders sessions from the shared composition root (§42, §63)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from rich.console import Console
from rich.table import Table

from ai.models.errors import ModelError
from application.agents.agent_turn_service import AgentTurnReport
from application.views import GameView
from domain.common.errors import DomainError, PersistenceError
from infrastructure.telemetry.in_memory import InMemoryTelemetrySink
from infrastructure.telemetry.logging_sink import configure_telemetry_logging
from interfaces.cli.renderer import render_game_view, render_gm_result, render_report
from session import (
    SessionConfig,
    advance,
    apply_input,
    build_service,
    open_session,
    parse_input,
)

__all__ = ["build_service", "main", "parse_input"]


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
        f"attempts: {report.action_attempts}, llm calls: {len(report.invocations)}, "
        f"memories: {report.memory_retrieved}[/dim]"
    )
    render_report(console, report.turn_report, view)


def _render_telemetry(console: Console, sink: InMemoryTelemetrySink) -> None:
    """Per-agent/role session totals table (spec §3.6)."""
    totals = sink.snapshot()
    if not totals:
        console.print("[dim]No LLM calls recorded this session.[/dim]")
        return
    table = Table(title="LLM telemetry (this session)")
    for column in (
        "agent", "role", "calls", "retries", "tokens in", "tokens out", "est. cost"
    ):
        table.add_column(column)
    for total in totals:
        table.add_row(
            total.key,
            total.role,
            str(total.calls),
            str(total.retries),
            str(total.input_tokens),
            str(total.output_tokens),
            f"${total.estimated_cost_usd:.6f}",
        )
    console.print(table)


def main(
    argv: list[str] | None = None,
    console: Console | None = None,
    input_fn: Callable[[str], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="conclave")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--db", choices=("memory", "postgres"), default="memory")
    parser.add_argument(
        "--agent",
        choices=("off", "llm", "fake"),
        default="off",
        help="add an AI-controlled party member (off | llm | fake)",
    )
    parser.add_argument(
        "--gm",
        choices=("off", "llm", "fake"),
        default="fake",
        help="enable the AI Game Master narrator (off | llm | fake)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="emit per-call LLM telemetry lines (JSON) to stderr or $CONCLAVE_TELEMETRY_LOG",
    )
    # argv=None means "no CLI arguments" so library/test callers are isolated
    # from the host process's sys.argv; the __main__ block passes it explicitly.
    args = parser.parse_args(argv if argv is not None else [])

    console = console or Console()
    configure_telemetry_logging(debug=args.debug)
    try:
        session = open_session(
            SessionConfig(
                seed=args.seed,
                db=args.db,
                agent_mode=None if args.agent == "off" else args.agent,
                gm_mode=args.gm,
            )
        )
    except (ValueError, PersistenceError, ModelError) as error:
        console.print(f"[red]{error}[/red]")
        return 2
    if session.party_names:
        console.print(
            f"[cyan]{', '.join(session.party_names)} join the party "
            f"(AI-controlled, mode: {args.agent})[/cyan]"
        )
    if session.opening is not None:
        render_gm_result(
            console,
            session.opening,
            session.game_service.get_view(session.game_id),
        )

    while True:
        view = session.game_service.get_view(session.game_id)
        render_game_view(console, view)
        if view.status == "ended":
            _render_telemetry(console, session.telemetry)
            console.print("The adventure has ended. Thanks for playing!")
            return 0
        try:
            pending = advance(session)
        except DomainError as error:
            console.print(f"[red]{error}[/red]")
            continue
        if pending is not None:
            if pending.kind == "agent":
                assert pending.agent_report is not None  # kind "agent" always carries it
                _render_agent_turn(console, pending.agent_report, view)
            else:
                render_report(console, pending.turn_report, view)
            if pending.gm_result is not None:
                render_gm_result(console, pending.gm_result, view)
            continue

        try:
            raw = (input_fn or input)("conclave> ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return 0

        outcome = apply_input(session, raw)
        if outcome.kind == "empty":
            continue
        if outcome.kind == "command":
            if outcome.argument == "/quit":
                _render_telemetry(console, session.telemetry)
                return 0
            if outcome.argument == "/status":
                continue
            if outcome.argument == "/telemetry":
                _render_telemetry(console, session.telemetry)
                continue
            if outcome.argument == "/help":
                console.print(
                    "Commands: attack <target>, say <text>, /status, /telemetry, /help, /quit"
                )
            else:
                console.print(f"Unknown command: {outcome.argument}")
            continue
        if outcome.kind == "say":
            if outcome.gm_result is None:
                console.print("The GM is off — run with --gm fake or --gm llm to talk.")
            else:
                render_gm_result(console, outcome.gm_result, view)
            continue
        if outcome.kind == "no_target":
            console.print(f"No such character: {outcome.argument}")
            continue
        if outcome.kind == "attack":
            if outcome.error is not None:
                console.print(f"[red]{outcome.error}[/red]")
                continue
            if outcome.turn_report is not None:
                render_report(console, outcome.turn_report, view)
            if outcome.gm_result is not None:
                render_gm_result(console, outcome.gm_result, view)
            continue
        console.print("Unknown input — try: attack <target>")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

`build_service` is imported from `session` (it lives in `session.factory`) so `tests/interfaces/test_cli.py`'s `from interfaces.cli.app import build_service` keeps working; `__all__` marks the re-exports as intentional (ruff F401).

- [ ] **Step 7: Run the full offline gate — the CLI contract is the gate**

Run the Global-Constraints gate pattern with `tests/interfaces/test_cli.py tests/session` first, then the full suite.
Expected: **440 passed, 2 deselected** (426 + 14 new session tests), `ruff` clean, `mypy` clean, and `tests/interfaces/test_cli.py` passing **unmodified** (byte-identical CLI behavior).

- [ ] **Step 8: Commit**

```bash
git add src/session src/interfaces/cli/app.py tests/session
git commit -m "feat(session): extract the session composition root from the CLI

build_service, the party/GM wiring, and the CLI loop's engine move to a
new top-level src/session package (factory.py + play.py): the composition
root must import infrastructure, so it cannot live in the
infrastructure-free application layer (CLAUDE.md 4). The CLI keeps
rendering, /commands, and the REPL; it re-exports parse_input and
build_service so the existing test contract is untouched. GameSession
exposes telemetry, the party board, party names, and the GM opening for
programmatic drivers - the evaluation harness and the future API layer
share this path (63).

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Evaluation scaffolding — errors, model, scenario registry, sink accessor

**Files:**
- Create: `src/evaluation/__init__.py`, `src/evaluation/errors.py`, `src/evaluation/model.py`, `src/evaluation/scenarios/__init__.py`, `src/evaluation/scenarios/goblin_skirmish.py`
- Modify: `src/infrastructure/telemetry/in_memory.py` (add `invocations()`)
- Test: `tests/evaluation/test_scenarios.py` (new), `tests/infrastructure/telemetry/test_in_memory_sink.py` (append)

**Interfaces:**
- Consumes: `SessionConfig`/`open_session` from Task 2 (runner, Task 5); `InMemoryTelemetrySink._records` (same package).
- Produces (consumed by Tasks 4–8):
  - `EvaluationError(RuntimeError)` in `evaluation.errors`.
  - `EventSummary(sequence: int, event_type: str, actor: str | None = None, target: str | None = None, detail: str | None = None)` — frozen.
  - `InvocationSummary(agent_id: str | None, operation: str, status: str, attempt: int, latency_ms: int, input_tokens: int | None, output_tokens: int | None, estimated_cost_usd: float | None)` — frozen.
  - `RunRecord(run_index: int, seed: int, event_summaries: tuple[EventSummary, ...], invocation_summaries: tuple[InvocationSummary, ...], turn_reports: tuple[str, ...], party_messages: tuple[str, ...], duration_ms: int)` — frozen.
  - `ScenarioCheck(name: str, description: str, evaluate: Callable[[ScenarioResult], bool])`; `Scenario(name: str, description: str, seed: int, steps: tuple[str, ...], repeat_runs: int = 1, checks: tuple[ScenarioCheck, ...] = ())`; `CheckResult(name: str, description: str, passed: bool)`; `ScenarioResult(scenario, provider: str, model: str, runs: tuple[RunRecord, ...], checks: tuple[CheckResult, ...], metrics: Mapping[str, float | int | None] = {}, rejection_reasons: Mapping[str, int] = {}, status: str = "ok", error: str | None = None)` — all frozen.
  - `SCENARIOS: Mapping[str, Scenario]` and `get_scenario(name: str) -> Scenario` (raises `EvaluationError`).
  - `InMemoryTelemetrySink.invocations() -> tuple[LLMInvocation, ...]`.

- [ ] **Step 1: Write the registry tests**

Create `tests/evaluation/test_scenarios.py`:

```python
# tests/evaluation/test_scenarios.py
"""Scenario registry tests (spec §4.2)."""

import pytest

from evaluation.errors import EvaluationError
from evaluation.scenarios import get_scenario


def test_get_scenario_returns_goblin_skirmish() -> None:
    scenario = get_scenario("goblin-skirmish")

    assert scenario.seed == 42
    assert scenario.repeat_runs == 2
    assert scenario.steps == ("attack goblin scout", "attack goblin skulker")
    assert {check.name for check in scenario.checks} == {
        "no-rejections",
        "skirmish-enemies-defeated",
        "consistent-runs",
    }


def test_get_scenario_unknown_name_raises_evaluation_error() -> None:
    with pytest.raises(EvaluationError, match="unknown scenario"):
        get_scenario("dragon-hoard")
```

- [ ] **Step 2: Run to verify failure**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/evaluation/test_scenarios.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evaluation'`

- [ ] **Step 3: Write the errors and model modules**

Create `src/evaluation/__init__.py`:

```python
"""Evaluation scenarios and metrics over real sessions (spec §4, Phase 18)."""
```

Create `src/evaluation/errors.py`:

```python
"""Harness-level errors (spec §5): misuse of the evaluation harness itself."""

from __future__ import annotations


class EvaluationError(RuntimeError):
    """Unknown scenario, bad provider, bad repeat count, or unwritable output dir."""
```

Create `src/evaluation/model.py`:

```python
"""Evaluation data model (spec §4.2/§4.3): scenarios, run records, results."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScenarioCheck:
    """One deterministic predicate over a finished result (spec §4.2)."""

    name: str
    description: str
    evaluate: Callable[["ScenarioResult"], bool]


@dataclass(frozen=True)
class Scenario:
    """A scripted, repeatable measurement of real game sessions."""

    name: str
    description: str
    seed: int
    steps: tuple[str, ...]  # human inputs, same grammar the CLI accepts
    repeat_runs: int = 1  # >1 enables cross-run consistency
    checks: tuple[ScenarioCheck, ...] = ()


@dataclass(frozen=True)
class EventSummary:
    """One domain event reduced to comparable facts (spec §4.3)."""

    sequence: int
    event_type: str
    actor: str | None = None
    target: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class InvocationSummary:
    """One enriched LLM invocation's metrics (spec §34: never prompts or payloads)."""

    agent_id: str | None
    operation: str
    status: str
    attempt: int
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None


@dataclass(frozen=True)
class RunRecord:
    """What one seeded session actually did (spec §4.3)."""

    run_index: int
    seed: int
    event_summaries: tuple[EventSummary, ...]
    invocation_summaries: tuple[InvocationSummary, ...]
    turn_reports: tuple[str, ...]
    party_messages: tuple[str, ...]
    duration_ms: int


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one scenario check (spec §5: recorded, never raised)."""

    name: str
    description: str
    passed: bool


@dataclass(frozen=True)
class ScenarioResult:
    """Everything one scenario run produced, checks included."""

    scenario: Scenario
    provider: str
    model: str
    runs: tuple[RunRecord, ...]
    checks: tuple[CheckResult, ...]
    metrics: Mapping[str, float | int | None] = field(default_factory=dict)
    rejection_reasons: Mapping[str, int] = field(default_factory=dict)
    status: str = "ok"  # "ok" | "error"
    error: str | None = None
```

- [ ] **Step 4: Write the goblin-skirmish scenario module and registry**

Create `src/evaluation/scenarios/goblin_skirmish.py`:

```python
"""The goblin-skirmish scenario (spec §4.4.1): two strikes, two goblins down.

Ground truth at seed 42 (offline scripted gateways): both steps are accepted,
there are zero rejections, and both goblins are defeated. The original draft
repeated "attack goblin scout", which fails its own no-rejections check - the
scout dies during step 2's pre-drain because the AI party attacks it too.
"""

from __future__ import annotations

from evaluation.model import Scenario, ScenarioCheck, ScenarioResult

_ENEMY_NAMES = ("Goblin Scout", "Goblin Skulker")


def _no_rejections(result: ScenarioResult) -> bool:
    return result.metrics.get("rejection_count") == 0


def _skirmish_enemies_defeated(result: ScenarioResult) -> bool:
    for run in result.runs:
        defeated = {
            event.actor
            for event in run.event_summaries
            if event.event_type == "character_defeated"
        }
        if not set(_ENEMY_NAMES) <= defeated:
            return False
    return True


def _runs_are_consistent(result: ScenarioResult) -> bool:
    agreement = result.metrics.get("consistency_agreement")
    return agreement is None or agreement == 1.0


GOBLIN_SKIRMISH = Scenario(
    name="goblin-skirmish",
    description=(
        "Two human strikes at the goblin screen while the AI party fights on: "
        "every proposed action must pass rules validation and both goblins fall."
    ),
    seed=42,
    steps=("attack goblin scout", "attack goblin skulker"),
    repeat_runs=2,
    checks=(
        ScenarioCheck(
            name="no-rejections",
            description="no action is rejected by the rules engine",
            evaluate=_no_rejections,
        ),
        ScenarioCheck(
            name="skirmish-enemies-defeated",
            description="Goblin Scout and Goblin Skulker are defeated in every run",
            evaluate=_skirmish_enemies_defeated,
        ),
        ScenarioCheck(
            name="consistent-runs",
            description="same-seed repeated runs produce identical event sequences",
            evaluate=_runs_are_consistent,
        ),
    ),
)
```

Create `src/evaluation/scenarios/__init__.py`:

```python
"""Scenario registry (spec §4.2): SCENARIOS maps names to concrete scenarios."""

from collections.abc import Mapping

from evaluation.errors import EvaluationError
from evaluation.model import Scenario
from evaluation.scenarios.goblin_skirmish import GOBLIN_SKIRMISH

SCENARIOS: Mapping[str, Scenario] = {
    "goblin-skirmish": GOBLIN_SKIRMISH,
}


def get_scenario(name: str) -> Scenario:
    """Look up a scenario by name; unknown names are harness misuse (§5)."""
    try:
        return SCENARIOS[name]
    except KeyError:
        raise EvaluationError(f"unknown scenario: {name!r}") from None
```

- [ ] **Step 4: Add the sink accessor**

In `src/infrastructure/telemetry/in_memory.py`, add after `snapshot()`:

```python
    def invocations(self) -> tuple[LLMInvocation, ...]:
        """Every recorded invocation, in order (evaluation runner, spec §4.3)."""
        return tuple(self._records)
```

Append to `tests/infrastructure/telemetry/test_in_memory_sink.py`:

```python
def test_invocations_returns_records_in_order() -> None:
    sink = InMemoryTelemetrySink()
    first = _invocation(request_id="req-1")
    second = _invocation(request_id="req-2")

    sink.record(first)
    sink.record(second)

    assert sink.invocations() == (first, second)
```

- [ ] **Step 5: Run the task tests**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/evaluation tests/infrastructure/telemetry/test_in_memory_sink.py -q`
Expected: **3 new passed** (2 registry + 1 sink accessor), plus the pre-existing sink tests all green.

- [ ] **Step 6: Run the full offline gate**

Expected: **443 passed, 2 deselected** (440 + 3), `ruff` clean, `mypy` clean.

- [ ] **Step 7: Commit**

```bash
git add src/evaluation src/infrastructure/telemetry/in_memory.py tests/evaluation tests/infrastructure/telemetry/test_in_memory_sink.py
git commit -m "feat(evaluation): scaffold the scenario model, registry, and sink accessor

EvaluationError for harness misuse; the frozen data model (Scenario,
ScenarioCheck, EventSummary, InvocationSummary, RunRecord, CheckResult,
ScenarioResult); the scenario registry with goblin-skirmish and its three
checks; and a public InMemoryTelemetrySink.invocations() accessor so the
runner can read embedding invocations that reach only the sink.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: Metrics module

**Files:**
- Create: `src/evaluation/metrics.py`
- Test: `tests/evaluation/test_metrics.py` (new)

**Interfaces:**
- Consumes: `ScenarioResult`, `RunRecord`, `EventSummary`, `InvocationSummary` from Task 3.
- Produces: `compute_metrics(result: ScenarioResult) -> Metrics` where `Metrics = dict[str, float | int | None]`, with exactly these keys: `legal_action_rate`, `rejection_count`, `retry_count`, `latency_ms_p50`, `latency_ms_p95`, `tokens_per_game`, `cost_per_game_usd`, `turn_count`, `party_message_count`, `consistency_agreement` (consumed by Tasks 5–8). An empty run set (error path) yields `None` metrics, never a crash.

- [ ] **Step 1: Write the metric tests**

Create `tests/evaluation/test_metrics.py`:

```python
# tests/evaluation/test_metrics.py
"""Metric arithmetic on synthetic records (spec §4.5): None when not computable."""

from evaluation.metrics import compute_metrics
from evaluation.model import (
    EventSummary,
    InvocationSummary,
    RunRecord,
    Scenario,
    ScenarioResult,
)


def _invocation(**overrides: object) -> InvocationSummary:
    values: dict[str, object] = {
        "agent_id": "brix",
        "operation": "generate_structured",
        "status": "ok",
        "attempt": 1,
        "latency_ms": 10,
        "input_tokens": 10,
        "output_tokens": 5,
        "estimated_cost_usd": None,
    }
    values.update(overrides)
    return InvocationSummary(**values)  # type: ignore[arg-type]


def _event(event_type: str, sequence: int, *, actor: str | None = None) -> EventSummary:
    return EventSummary(sequence=sequence, event_type=event_type, actor=actor)


def _run(
    index: int,
    events: tuple[EventSummary, ...] = (),
    invocations: tuple[InvocationSummary, ...] = (),
    *,
    turn_reports: tuple[str, ...] = (),
    party_messages: tuple[str, ...] = (),
) -> RunRecord:
    return RunRecord(
        run_index=index,
        seed=42,
        event_summaries=events,
        invocation_summaries=invocations,
        turn_reports=turn_reports,
        party_messages=party_messages,
        duration_ms=100,
    )


def _result(
    runs: tuple[RunRecord, ...], rejection_reasons: dict[str, int] | None = None
) -> ScenarioResult:
    scenario = Scenario(
        name="synthetic", description="d", seed=42, steps=("attack goblin scout",)
    )
    return ScenarioResult(
        scenario=scenario,
        provider="fake",
        model="test-model",
        runs=runs,
        checks=(),
        metrics={},
        rejection_reasons=rejection_reasons or {},
    )


def test_legal_action_rate_averages_over_runs() -> None:
    accepted = (_event("attack_requested", 1), _event("attack_requested", 2))
    half = (_event("attack_requested", 1), _event("action_rejected", 2))
    result = _result((_run(0, accepted), _run(1, half)))

    metrics = compute_metrics(result)

    assert metrics["legal_action_rate"] == 0.75  # 2/2 and 1/2, averaged


def test_legal_action_rate_is_none_without_proposals() -> None:
    result = _result((_run(0),))

    assert compute_metrics(result)["legal_action_rate"] is None


def test_rejection_count_and_reason_breakdown() -> None:
    reasons = {"invalid target": 2, "not your turn": 1}
    result = _result((_run(0), _run(1)), rejection_reasons=reasons)

    metrics = compute_metrics(result)

    assert metrics["rejection_count"] == 3


def test_retry_count_counts_attempts_above_one() -> None:
    run = _run(0, invocations=(_invocation(attempt=1), _invocation(attempt=3)))

    assert compute_metrics(_result((run,)))["retry_count"] == 1


def test_latency_percentiles_use_ok_invocations() -> None:
    invocations = (
        _invocation(latency_ms=10),
        _invocation(latency_ms=20),
        _invocation(latency_ms=30),
        _invocation(latency_ms=40),
        _invocation(latency_ms=999, status="error"),
    )

    metrics = compute_metrics(_result((_run(0, invocations=invocations),)))

    assert metrics["latency_ms_p50"] == 20  # nearest-rank over ok calls
    assert metrics["latency_ms_p95"] == 40


def test_tokens_and_cost_per_game_average_over_runs() -> None:
    priced = _invocation(input_tokens=0, output_tokens=0, estimated_cost_usd=0.02)
    runs = (
        _run(0, invocations=(_invocation(input_tokens=10, output_tokens=5), priced)),
        _run(1, invocations=(_invocation(input_tokens=30, output_tokens=15),)),
    )

    metrics = compute_metrics(_result(runs))

    assert metrics["tokens_per_game"] == 30  # (15 + 45) / 2
    assert metrics["cost_per_game_usd"] == 0.01  # 0.02 / 2


def test_cost_per_game_is_none_without_priced_calls() -> None:
    runs = (_run(0, invocations=(_invocation(),)),)

    assert compute_metrics(_result(runs))["cost_per_game_usd"] is None


def test_turn_and_party_message_counts_sum_runs() -> None:
    runs = (
        _run(0, turn_reports=("accepted",), party_messages=("Brix: Focus.",)),
        _run(1, turn_reports=("accepted", "rejected: invalid target")),
    )

    metrics = compute_metrics(_result(runs))

    assert metrics["turn_count"] == 3
    assert metrics["party_message_count"] == 1


def test_consistency_agreement_identical_runs() -> None:
    first = _run(
        0,
        event_summaries=(_event("turn_started", 1), _event("turn_ended", 2)),
    )
    second = _run(
        1,
        event_summaries=(_event("turn_started", 1), _event("turn_ended", 2)),
    )
    result = _result((first, second))

    assert compute_metrics(result)["consistency_agreement"] == 1.0


def test_consistency_agreement_detects_divergence() -> None:
    same = (
        EventSummary(sequence=1, event_type="turn_started"),
        EventSummary(sequence=2, event_type="turn_ended"),
    )
    divergent = (EventSummary(sequence=1, event_type="turn_started"),)
    result = _result((_run(0, event_summaries=same), _run(1, event_summaries=divergent)))

    assert compute_metrics(result)["consistency_agreement"] == 0.5


def test_consistency_is_none_for_a_single_run() -> None:
    result = _result((_run(0),))

    assert compute_metrics(result)["consistency_agreement"] is None


def test_empty_result_yields_none_not_crashes() -> None:
    """The runner's error path can carry zero runs; metrics must not divide by zero."""
    metrics = compute_metrics(_result(()))

    assert metrics["tokens_per_game"] is None
    assert metrics["cost_per_game_usd"] is None
    assert metrics["latency_ms_p50"] is None
    assert metrics["latency_ms_p95"] is None
    assert metrics["consistency_agreement"] is None
    assert metrics["rejection_count"] == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/evaluation/test_metrics.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evaluation.metrics'`

- [ ] **Step 3: Write the implementation**

Create `src/evaluation/metrics.py`:

```python
"""Core metric arithmetic over ScenarioResults (spec §4.5).

None means "not computable" — never a fake 0 or 1.
"""

from __future__ import annotations

import math

from evaluation.model import InvocationSummary, RunRecord, ScenarioResult

Metrics = dict[str, float | int | None]


def compute_metrics(result: ScenarioResult) -> Metrics:
    runs = result.runs
    return {
        "legal_action_rate": _legal_action_rate(runs),
        "rejection_count": sum(result.rejection_reasons.values()),
        "retry_count": _retry_count(runs),
        "latency_ms_p50": _percentile(_ok_latencies(runs), 0.50),
        "latency_ms_p95": _percentile(_ok_latencies(runs), 0.95),
        "tokens_per_game": _tokens_per_game(runs),
        "cost_per_game_usd": _cost_per_game(runs),
        "turn_count": sum(len(run.turn_reports) for run in runs),
        "party_message_count": sum(len(run.party_messages) for run in runs),
        "consistency_agreement": _consistency(runs),
    }


def _legal_action_rate(runs: tuple[RunRecord, ...]) -> float | None:
    """AttackRequested / (AttackRequested + ActionRejected), averaged over runs.

    The current ruleset rejects only attack proposals, so every ActionRejected
    counts toward the denominator; when more action types exist, extend
    EventSummary with action_type and filter here.
    """
    rates: list[float] = []
    for run in runs:
        proposals = sum(
            1 for e in run.event_summaries if e.event_type == "attack_requested"
        )
        rejections = sum(
            1 for e in run.event_summaries if e.event_type == "action_rejected"
        )
        if proposals + rejections == 0:
            continue
        rates.append(proposals / (proposals + rejections))
    if not rates:
        return None
    return sum(rates) / len(rates)


def _retry_count(runs: tuple[RunRecord, ...]) -> int:
    return sum(
        1
        for run in runs
        for invocation in run.invocation_summaries
        if invocation.attempt > 1
    )


def _ok_latencies(runs: tuple[RunRecord, ...]) -> list[int]:
    return sorted(
        invocation.latency_ms
        for run in runs
        for invocation in run.invocation_summaries
        if invocation.status == "ok"
    )


def _percentile(sorted_values: list[int], fraction: float) -> int | None:
    """Nearest-rank percentile over pre-sorted values."""
    if not sorted_values:
        return None
    index = max(0, math.ceil(fraction * len(sorted_values)) - 1)
    return sorted_values[min(index, len(sorted_values) - 1)]


def _tokens_per_game(runs: tuple[RunRecord, ...]) -> int | None:
    if not runs:
        return None
    total = sum(
        (invocation.input_tokens or 0) + (invocation.output_tokens or 0)
        for run in runs
        for invocation in run.invocation_summaries
    )
    return total // len(runs)


def _cost_per_game(runs: tuple[RunRecord, ...]) -> float | None:
    costs = [
        invocation.estimated_cost_usd
        for run in runs
        for invocation in run.invocation_summaries
        if invocation.estimated_cost_usd is not None
    ]
    if not costs:
        return None
    return round(sum(costs) / len(runs), 6)


def _consistency(runs: tuple[RunRecord, ...]) -> float | None:
    """Fraction of runs whose event-type sequence equals run 0's."""
    if len(runs) < 2:
        return None
    first = tuple(event.event_type for event in runs[0].event_summaries)
    matches = sum(
        1
        for run in runs
        if tuple(event.event_type for event in run.event_summaries) == first
    )
    return matches / len(runs)
```

- [ ] **Step 3b: Run the metric tests**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/evaluation/test_metrics.py -q`
Expected: **12 passed**

- [ ] **Step 4: Run the full offline gate**

Expected: **455 passed, 2 deselected**, `ruff` clean, `mypy` clean.

- [ ] **Step 5: Commit**

```bash
git add src/evaluation/metrics.py tests/evaluation/test_metrics.py
git commit -m "feat(evaluation): compute the core metric set over run records

Legal-action rate averaged over runs, rejection totals, retry counts,
latency p50/p95 (nearest-rank, status-ok calls), tokens and cost per
game, turn and party-message counts, and cross-run consistency - all
None when not computable, never a fake 0 or 1; an empty run set (the
error path) yields None instead of dividing by zero (spec 4.5).

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: Runner + goblin-skirmish end-to-end

**Files:**
- Create: `src/evaluation/runner.py`
- Test: `tests/evaluation/test_runner.py` (new)

**Interfaces:**
- Consumes: `open_session`/`SessionConfig`/`CONFIG_DIR` (Task 2), `compute_metrics` (Task 4), `Scenario`/model types (Task 3), `load_model_profiles` (`ai.models.profiles`), `EventEnvelope` (`domain.events.collector`), `LLMInvocation` (`ai.models.types`), `EvaluationError`.
- Produces: `run_scenario(scenario: Scenario, *, seed: int, repeat: int, provider: str, db: str = "memory") -> ScenarioResult` — the only entry point Task 7's CLI uses. Unknown provider or `repeat < 1` raises `EvaluationError`; a failing run yields `status="error"` with `error` set, partial runs kept, `checks=()`.

- [ ] **Step 1: Write the runner tests**

Create `tests/evaluation/test_runner.py`:

```python
# tests/evaluation/test_runner.py
"""Runner end-to-end over offline scripted gateways (spec §4.3)."""

import pytest

from evaluation import runner as runner_module
from evaluation.errors import EvaluationError
from evaluation.runner import run_scenario
from evaluation.scenarios import get_scenario


def test_run_scenario_goblin_skirmish_offline() -> None:
    scenario = get_scenario("goblin-skirmish")

    result = run_scenario(scenario, seed=42, repeat=2, provider="fake")

    assert result.status == "ok"
    assert result.error is None
    assert len(result.runs) == 2
    assert result.runs[0].seed == 42
    assert result.runs[0].event_summaries  # a real fight happened
    assert result.runs[0].invocation_summaries  # gateway calls were recorded
    assert result.runs[0].party_messages  # scripted agents post chatter
    assert result.runs[0].turn_reports
    assert all(check.passed for check in result.checks)
    assert result.metrics["consistency_agreement"] == 1.0
    assert result.rejection_reasons == {}


def test_run_scenario_is_reproducible_across_calls() -> None:
    scenario = get_scenario("goblin-skirmish")

    first = run_scenario(scenario, seed=42, repeat=1, provider="fake")
    second = run_scenario(scenario, seed=42, repeat=1, provider="fake")

    assert [event.event_type for event in first.runs[0].event_summaries] == [
        event.event_type for event in second.runs[0].event_summaries
    ]


def test_failing_run_reports_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = get_scenario("goblin-skirmish")

    def _boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("gateway exploded")

    monkeypatch.setattr(runner_module, "_run_once", _boom)

    result = run_scenario(scenario, seed=42, repeat=2, provider="fake")

    assert result.status == "error"
    assert "gateway exploded" in str(result.error)
    assert result.checks == ()


def test_unknown_provider_raises_evaluation_error() -> None:
    scenario = get_scenario("goblin-skirmish")

    with pytest.raises(EvaluationError, match="unknown provider"):
        run_scenario(scenario, seed=42, repeat=1, provider="ollama")


def test_repeat_below_one_raises_evaluation_error() -> None:
    scenario = get_scenario("goblin-skirmish")

    with pytest.raises(EvaluationError, match="repeat"):
        run_scenario(scenario, seed=42, repeat=0, provider="fake")
```

- [ ] **Step 2: Run to verify failure**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/evaluation/test_runner.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evaluation.runner'`

- [ ] **Step 3: Write the runner**

Create `src/evaluation/runner.py`:

```python
"""Scenario runner: fresh seeded sessions through the application layer (spec §4.3).

Evaluation contains no game rules and mutates game state only through
application services (§71). One correlation id per step (Plan 8).
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import replace

from ai.models.profiles import load_model_profiles
from ai.models.types import LLMInvocation
from application.views import TurnReport
from domain.events.collector import EventEnvelope
from evaluation.errors import EvaluationError
from evaluation.metrics import compute_metrics
from evaluation.model import (
    CheckResult,
    EventSummary,
    InvocationSummary,
    RunRecord,
    Scenario,
    ScenarioResult,
)
from session import (
    CONFIG_DIR,
    GameSession,
    SessionConfig,
    advance,
    apply_input,
    open_session,
)

_PROVIDER_MODES = {"fake": ("fake", "fake"), "openrouter": ("llm", "llm")}
_PARTY_SNAPSHOT_LIMIT = 128


def run_scenario(
    scenario: Scenario,
    *,
    seed: int,
    repeat: int,
    provider: str,
    db: str = "memory",
) -> ScenarioResult:
    """Run a scenario repeat times; isolate a failing run (spec §5)."""
    if provider not in _PROVIDER_MODES:
        raise EvaluationError(f"unknown provider: {provider!r}")
    if repeat < 1:
        raise EvaluationError(f"repeat must be >= 1, got {repeat}")
    agent_mode, gm_mode = _PROVIDER_MODES[provider]
    config = SessionConfig(
        db=db,
        agent_mode=agent_mode,
        gm_mode=gm_mode,
        provider=provider if provider == "openrouter" else None,
    )
    model = load_model_profiles(CONFIG_DIR / "llm.toml").get("player").model

    runs: list[RunRecord] = []
    for run_index in range(repeat):
        try:
            runs.append(_run_once(scenario, config, run_index, seed))
        except Exception as error:  # scenario isolation, spec §5
            partial = ScenarioResult(
                scenario=scenario,
                provider=provider,
                model=model,
                runs=tuple(runs),
                checks=(),
                metrics={},
                rejection_reasons=_rejection_reasons(tuple(runs)),
                status="error",
                error=str(error),
            )
            return replace(partial, metrics=compute_metrics(partial))

    base = ScenarioResult(
        scenario=scenario,
        provider=provider,
        model=model,
        runs=tuple(runs),
        checks=(),
        metrics={},
        rejection_reasons=_rejection_reasons(tuple(runs)),
    )
    result = replace(base, metrics=compute_metrics(base))
    checks = tuple(
        CheckResult(
            name=check.name,
            description=check.description,
            passed=check.evaluate(result),
        )
        for check in scenario.checks
    )
    return replace(result, checks=checks)


def _run_once(
    scenario: Scenario, config: SessionConfig, run_index: int, seed: int
) -> RunRecord:
    """One fresh session, driven step by step, then reduced to a RunRecord."""
    started = time.perf_counter()
    session = open_session(replace(config, seed=seed))
    turn_reports: list[TurnReport] = []

    for step in scenario.steps:
        _drain(session, turn_reports)
        view = session.game_service.get_view(session.game_id)
        if view.status == "ended":
            continue  # later steps are skipped once the fight is decided
        outcome = apply_input(session, step)
        if outcome.turn_report is not None:
            turn_reports.append(outcome.turn_report)
    _drain(session, turn_reports)
    duration_ms = int((time.perf_counter() - started) * 1000)

    events = session.game_service.get_events(session.game_id)
    view = session.game_service.get_view(session.game_id)
    name_by_id = {member.id: member.name for member in (*view.party, *view.enemies)}
    return RunRecord(
        run_index=run_index,
        seed=seed,
        event_summaries=tuple(
            _summarize_event(envelope, name_by_id) for envelope in events
        ),
        invocation_summaries=tuple(
            _summarize_invocation(invocation)
            for invocation in session.telemetry.invocations()
        ),
        turn_reports=tuple(
            f"{'accepted' if report.accepted else 'rejected'}"
            + (f": {report.reason}" if report.reason else "")
            for report in turn_reports
        ),
        party_messages=tuple(
            f"{message.actor_name}: {message.text}"
            for message in session.party_board.recent(limit=_PARTY_SNAPSHOT_LIMIT)
        ),
        duration_ms=duration_ms,
    )


def _drain(session: GameSession, turn_reports: list[TurnReport]) -> None:
    """Drive non-player turns until it is the human's turn or the fight is over."""
    while (pending := advance(session)) is not None:
        turn_reports.append(pending.turn_report)


def _rejection_reasons(runs: tuple[RunRecord, ...]) -> dict[str, int]:
    reasons: dict[str, int] = {}
    for run in runs:
        for event in run.event_summaries:
            if event.event_type == "action_rejected" and event.detail:
                reasons[event.detail] = reasons.get(event.detail, 0) + 1
    return reasons


def _summarize_invocation(invocation: LLMInvocation) -> InvocationSummary:
    """Metrics only — never prompts, payloads, or reasoning (§34/§50)."""
    return InvocationSummary(
        agent_id=invocation.agent_id,
        operation=invocation.operation,
        status=invocation.status,
        attempt=invocation.attempt,
        latency_ms=invocation.latency_ms,
        input_tokens=invocation.input_tokens,
        output_tokens=invocation.output_tokens,
        estimated_cost_usd=invocation.estimated_cost_usd,
    )


def _summarize_event(
    envelope: EventEnvelope, name_by_id: Mapping[str, str]
) -> EventSummary:
    """Reduce one envelope to comparable facts, ids resolved to names."""
    payload = envelope.payload
    event_type = envelope.event_type

    def _name(field: str) -> str:
        value = str(payload[field])
        return name_by_id.get(value, value)

    actor = target = detail = None
    if event_type == "attack_requested":
        actor, target = _name("attacker_id"), _name("target_id")
    elif event_type == "attack_resolved":
        actor, target = _name("attacker_id"), _name("target_id")
        detail = (
            f"roll {payload['roll']}+{payload['attack_bonus']}={payload['total']} "
            f"vs AC {payload['target_ac']} hit={payload['hit']} crit={payload['critical']}"
        )
    elif event_type == "action_rejected":
        actor = _name("actor_id")
        detail = str(payload["reason"])
    elif event_type == "damage_applied":
        actor = _name("character_id")
        detail = f"-{payload['amount']} ({payload['hp_after']} hp)"
    elif event_type == "character_defeated":
        actor = _name("character_id")
    elif event_type == "initiative_rolled":
        actor = _name("character_id")
        detail = f"total {payload['total']}"
    elif event_type == "combat_started":
        detail = (
            f"round {payload['round_number']}: "
            f"{len(payload['participant_ids'])} participants"
        )
    elif event_type == "combat_ended":
        detail = f"round {payload['round_number']}: {payload['winner_side']} wins"
    elif event_type in ("turn_started", "turn_ended"):
        actor = _name("actor_id")
    return EventSummary(
        sequence=envelope.sequence,
        event_type=event_type,
        actor=actor,
        target=target,
        detail=detail,
    )
```

- [ ] **Step 3b: Run the runner tests**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/evaluation/test_runner.py -q`
Expected: **5 passed**

- [ ] **Step 4: Run the full offline gate**

Expected: **460 passed, 2 deselected**, `ruff` clean, `mypy` clean.

- [ ] **Step 5: Commit**

```bash
git add src/evaluation/runner.py tests/evaluation/test_runner.py
git commit -m "feat(evaluation): run scenarios through real sessions and record what happened

Each run opens a fresh seeded session via open_session, drains
non-player turns, applies the scenario's steps through apply_input, and
reduces the run to event summaries, invocation summaries, turn report
summaries, and the party-traffic snapshot. A failing run marks the
scenario result error with partial runs kept; checks evaluate over the
computed metrics and are recorded, never raised (spec 4.3, 5).

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: Report writer + eval-results gitignore

**Files:**
- Create: `src/evaluation/report.py`
- Modify: `.gitignore` (append `eval-results/`)
- Test: `tests/evaluation/test_report.py` (new)

**Interfaces:**
- Consumes: `ScenarioResult` and friends (Task 3).
- Produces: `write_report(result: ScenarioResult, out_dir: Path) -> Path` — creates `out_dir` on demand, writes `<scenario>-<provider>-<model-with-/-replaced>-<seed>-<UTC timestamp>.json`, returns the path. `EvaluationError` when the directory cannot be created. No secrets, prompts, payloads, or reasoning anywhere in the JSON (§34/§50).

- [ ] **Step 1: Write the report tests**

Create `tests/evaluation/test_report.py`:

```python
# tests/evaluation/test_report.py
"""Report writer tests (spec §4.6): naming, shape, and hygiene."""

import json

from evaluation.model import (
    EventSummary,
    RunRecord,
    Scenario,
    ScenarioResult,
)
from evaluation.report import write_report


def _result() -> ScenarioResult:
    scenario = Scenario(
        name="goblin-skirmish", description="d", seed=42, steps=("attack goblin scout",)
    )
    run = RunRecord(
        run_index=0,
        seed=42,
        event_summaries=(
            EventSummary(sequence=1, event_type="combat_started"),
            EventSummary(sequence=2, event_type="turn_started", actor="Arin"),
        ),
        invocation_summaries=(),
        turn_reports=("accepted",),
        party_messages=("Brix: Focus the nearest standing foe.",),
        duration_ms=120,
    )
    return ScenarioResult(
        scenario=scenario,
        provider="fake",
        model="z-ai/glm-5.3-flash",
        runs=(run,),
        checks=(),
        metrics={"legal_action_rate": 1.0, "rejection_count": 0},
        rejection_reasons={},
    )


def test_write_report_writes_parseable_json_with_the_contract_name(tmp_path) -> None:
    path = write_report(_result(), tmp_path)

    assert path.parent == tmp_path
    assert path.name.startswith("goblin-skirmish-fake-z-ai-glm-5.3-flash-42-")
    assert path.name.endswith(".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["scenario"]["name"] == "goblin-skirmish"
    assert payload["provider"] == "fake"
    assert payload["metrics"]["legal_action_rate"] == 1.0
    assert payload["runs"][0]["event_types"] == ["combat_started", "turn_started"]
    assert payload["runs"][0]["party_messages"] == ["Brix: Focus the nearest standing foe."]


def test_write_report_creates_a_missing_out_dir(tmp_path) -> None:
    out_dir = tmp_path / "nested" / "eval-results"

    path = write_report(_result(), out_dir)

    assert out_dir.is_dir()
    assert path.exists()


def test_report_never_contains_secrets_or_prompts(tmp_path) -> None:
    path = write_report(_result(), tmp_path)

    text = path.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY" not in text
    assert "api_key" not in text.lower()
    assert "prompt" not in text.lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/evaluation/test_report.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evaluation.report'`

- [ ] **Step 3: Write the report writer**

Create `src/evaluation/report.py`:

```python
"""JSON report writer (spec §4.6): no secrets, no prompts, no payloads (§34/§50)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from evaluation.errors import EvaluationError
from evaluation.model import ScenarioResult


def write_report(result: ScenarioResult, out_dir: Path) -> Path:
    """Write one scenario's JSON report and return its path."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise EvaluationError(
            f"cannot write report directory {out_dir}: {error}"
        ) from error
    seed = result.runs[0].seed if result.runs else result.scenario.seed
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    model = result.model.replace("/", "-")
    path = out_dir / f"{result.scenario.name}-{result.provider}-{model}-{seed}-{stamp}.json"
    path.write_text(json.dumps(_payload(result), indent=2) + "\n", encoding="utf-8")
    return path


def _payload(result: ScenarioResult) -> dict[str, object]:
    return {
        "scenario": {
            "name": result.scenario.name,
            "description": result.scenario.description,
            "seed": result.scenario.seed,
            "steps": list(result.scenario.steps),
        },
        "provider": result.provider,
        "model": result.model,
        "status": result.status,
        "error": result.error,
        "checks": [
            {"name": check.name, "description": check.description, "passed": check.passed}
            for check in result.checks
        ],
        "metrics": dict(result.metrics),
        "rejection_reasons": dict(result.rejection_reasons),
        "runs": [
            {
                "run_index": run.run_index,
                "seed": run.seed,
                "duration_ms": run.duration_ms,
                "event_types": [event.event_type for event in run.event_summaries],
                "events": [
                    {
                        "sequence": event.sequence,
                        "event_type": event.event_type,
                        "actor": event.actor,
                        "target": event.target,
                        "detail": event.detail,
                    }
                    for event in run.event_summaries
                ],
                "invocations": [
                    {
                        "agent_id": invocation.agent_id,
                        "operation": invocation.operation,
                        "status": invocation.status,
                        "attempt": invocation.attempt,
                        "latency_ms": invocation.latency_ms,
                        "input_tokens": invocation.input_tokens,
                        "output_tokens": invocation.output_tokens,
                        "estimated_cost_usd": invocation.estimated_cost_usd,
                    }
                    for invocation in run.invocation_summaries
                ],
                "turn_reports": list(run.turn_reports),
                "party_messages": list(run.party_messages),
            }
            for run in result.runs
        ],
    }
```

Append to `.gitignore`:

```text
eval-results/
```

- [ ] **Step 3b: Run the report tests**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/evaluation/test_report.py -q`
Expected: **3 passed**

- [ ] **Step 4: Run the full offline gate**

Expected: **463 passed, 2 deselected**, `ruff` clean, `mypy` clean.

- [ ] **Step 5: Commit**

```bash
git add src/evaluation/report.py .gitignore tests/evaluation/test_report.py
git commit -m "feat(evaluation): write JSON reports under git-ignored eval-results/

One file per scenario run: scenario config (no secrets), check results,
metrics plus rejection reasons, and per-run event/invocation/turn/party
summaries. Never prompts, payloads, API keys, or reasoning (34/50).

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: The `conclave-eval` CLI

**Files:**
- Create: `src/evaluation/cli.py`
- Modify: `pyproject.toml` (`[project.scripts]` — add the script entry)
- Test: `tests/evaluation/test_cli.py` (new)

**Interfaces:**
- Consumes: `run_scenario` (Task 5), `write_report` (Task 6), `SCENARIOS`/`get_scenario` (Task 3), `EvaluationError`.
- Produces: `main(argv: list[str] | None = None, console: Console | None = None) -> int` — `--scenario all|<name>` (default all), `--provider fake|openrouter` (default fake), `--seed` (default 42), `--repeat N` (overrides `repeat_runs` when given), `--db memory|postgres`, `--out-dir` (default `eval-results/`). Exit 0 all scenarios pass; 1 any check failure or `"error"` status; 2 usage error (unknown scenario, missing `OPENROUTER_API_KEY` — before any run).

- [ ] **Step 1: Write the CLI tests**

Create `tests/evaluation/test_cli.py`:

```python
# tests/evaluation/test_cli.py
"""conclave-eval CLI tests: exit codes, artifacts, fast-fail (spec §4.6)."""

import json
from io import StringIO

from rich.console import Console

from evaluation.cli import main


def _console() -> tuple:
    buffer = StringIO()
    return Console(file=buffer, width=120, force_terminal=False), buffer


def test_eval_cli_runs_goblin_skirmish_offline(tmp_path) -> None:
    console, buffer = _console()
    out_dir = tmp_path / "results"

    code = main(
        ["--scenario", "goblin-skirmish", "--out-dir", str(out_dir)], console=console
    )

    assert code == 0
    reports = list(out_dir.glob("goblin-skirmish-*.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert all(check["passed"] for check in payload["checks"])
    assert "goblin-skirmish" in buffer.getvalue()


def test_eval_cli_repeat_overrides_scenario_runs(tmp_path) -> None:
    console, _ = _console()
    out_dir = tmp_path / "results"

    code = main(
        ["--scenario", "goblin-skirmish", "--repeat", "1", "--out-dir", str(out_dir)],
        console=console,
    )

    assert code == 0
    report = next(out_dir.glob("goblin-skirmish-*.json"))
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert len(payload["runs"]) == 1


def test_eval_cli_unknown_scenario_exits_2(tmp_path) -> None:
    console, buffer = _console()

    code = main(
        ["--scenario", "dragon-hoard", "--out-dir", str(tmp_path)], console=console
    )

    assert code == 2
    assert "unknown scenario" in buffer.getvalue()


def test_eval_cli_openrouter_without_api_key_exits_2(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    console, buffer = _console()

    code = main(["--provider", "openrouter", "--out-dir", str(tmp_path)], console=console)

    assert code == 2
    assert "OPENROUTER_API_KEY" in buffer.getvalue()
```

- [ ] **Step 2: Run to verify failure**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/evaluation/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evaluation.cli'`

- [ ] **Step 3: Write the CLI and the script entry**

Create `src/evaluation/cli.py`:

```python
"""conclave-eval — run scenarios, print a Rich summary (spec §4.6).

Rich lives only here (spec §6); the runner and metrics stay presentation-free.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from rich.console import Console
from rich.table import Table

from evaluation.errors import EvaluationError
from evaluation.model import ScenarioResult
from evaluation.report import write_report
from evaluation.runner import run_scenario
from evaluation.scenarios import SCENARIOS, get_scenario


def _table(results: list[ScenarioResult]) -> Table:
    table = Table(title="Evaluation results")
    for column in (
        "scenario",
        "model",
        "runs",
        "checks",
        "legal %",
        "rejections",
        "retries",
        "tokens/game",
        "cost/game",
        "p50 ms",
        "p95 ms",
        "status",
    ):
        table.add_column(column)
    for result in results:
        metrics = result.metrics
        legal = metrics.get("legal_action_rate")
        cost = metrics.get("cost_per_game_usd")
        table.add_row(
            result.scenario.name,
            result.model,
            str(len(result.runs)),
            f"{sum(1 for check in result.checks if check.passed)}/{len(result.checks)}",
            "—" if legal is None else f"{legal:.0%}",
            str(metrics.get("rejection_count")),
            str(metrics.get("retry_count")),
            str(metrics.get("tokens_per_game")),
            "—" if cost is None else f"${cost:.6f}",
            str(metrics.get("latency_ms_p50")),
            str(metrics.get("latency_ms_p95")),
            result.status,
        )
    return table


def main(argv: list[str] | None = None, console: Console | None = None) -> int:
    parser = argparse.ArgumentParser(prog="conclave-eval")
    parser.add_argument("--scenario", default="all", help="all | <scenario name>")
    parser.add_argument("--provider", choices=("fake", "openrouter"), default="fake")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--repeat", type=int, default=None, help="override the scenario's repeat_runs"
    )
    parser.add_argument("--db", choices=("memory", "postgres"), default="memory")
    parser.add_argument("--out-dir", type=Path, default=Path("eval-results"))
    args = parser.parse_args(argv if argv is not None else [])

    console = console or Console()
    if args.provider == "openrouter" and not os.environ.get("OPENROUTER_API_KEY"):
        console.print(
            "[red]OPENROUTER_API_KEY is not set; export it to run live evaluation[/red]"
        )
        return 2
    try:
        scenarios = (
            [get_scenario(name) for name in sorted(SCENARIOS)]
            if args.scenario == "all"
            else [get_scenario(args.scenario)]
        )
    except EvaluationError as error:
        console.print(f"[red]{error}[/red]")
        return 2

    exit_code = 0
    results: list[ScenarioResult] = []
    for scenario in scenarios:
        result = run_scenario(
            scenario,
            seed=args.seed,
            repeat=args.repeat if args.repeat is not None else scenario.repeat_runs,
            provider=args.provider,
            db=args.db,
        )
        path = write_report(result, args.out_dir)
        console.print(f"[dim]wrote {path}[/dim]")
        results.append(result)
        if result.status != "ok" or not all(check.passed for check in result.checks):
            exit_code = 1
    console.print(_table(results))
    return exit_code
```

Modify `pyproject.toml` — the `[project.scripts]` block currently reads:

```toml
[project.scripts]
conclave = "interfaces.cli.app:main"
```

Change it to:

```toml
[project.scripts]
conclave = "interfaces.cli.app:main"
conclave-eval = "evaluation.cli:main"
```

- [ ] **Step 3b: Run the CLI tests**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/evaluation/test_cli.py -q`
Expected: **4 passed**

- [ ] **Step 4: Run the full offline gate**

Expected: **467 passed, 2 deselected**, `ruff` clean, `mypy` clean.

- [ ] **Step 5: Smoke the installed script**

```bash
.venv/bin/pip install -e . -q
.venv/bin/conclave-eval --scenario goblin-skirmish --out-dir /tmp/eval-smoke
ls /tmp/eval-smoke
git status --porcelain  # eval-results/ absent (only /tmp used); tree stays clean
```

Expected: exit 0, one report file listed, `git status --porcelain` empty.

- [ ] **Step 6: Commit**

```bash
git add src/evaluation/cli.py pyproject.toml tests/evaluation/test_cli.py
git commit -m "feat(evaluation): add the conclave-eval CLI with Rich summary and exit codes

--scenario all|<name>, --provider fake|openrouter (fast-fails without
OPENROUTER_API_KEY before any run), --seed, --repeat override, --db,
--out-dir defaulting to git-ignored eval-results/. Exit 0 all checks
pass, 1 any failure or error, 2 usage error (spec 4.6).

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: Remaining scenarios, docs, and the final gate

**Files:**
- Create: `src/evaluation/scenarios/instruction_following.py`, `src/evaluation/scenarios/cooperation_smoke.py`, `tests/evaluation/test_offline_scenarios.py`
- Modify: `src/evaluation/scenarios/__init__.py`, `tests/evaluation/test_scenarios.py` (append), `README.md` (Evaluation section), `docs/superpowers/plans/README.md` (row #9)

**Interfaces:**
- Consumes: `Scenario`/`ScenarioCheck` (Task 3), `run_scenario` (Task 5).
- Produces: `SCENARIOS` with exactly three entries — `goblin-skirmish`, `instruction-following`, `cooperation-smoke`. `instruction-following` checks: `player-attack-fidelity`, `agents-attack-enemies`, `no-rejections`. `cooperation-smoke` checks: `party-messages-exchanged`, `no-rejections`.

- [ ] **Step 1: Write the new-scenario tests**

Append to `tests/evaluation/test_scenarios.py`:

```python
def test_registry_holds_the_three_scenarios() -> None:
    from evaluation.scenarios import SCENARIOS

    assert set(SCENARIOS) == {
        "goblin-skirmish",
        "instruction-following",
        "cooperation-smoke",
    }
```

Create `tests/evaluation/test_offline_scenarios.py`:

```python
# tests/evaluation/test_offline_scenarios.py
"""Offline end-to-end checks for the two later scenarios (spec §4.4)."""

from evaluation.runner import run_scenario
from evaluation.scenarios import get_scenario


def test_instruction_following_passes_offline() -> None:
    scenario = get_scenario("instruction-following")

    result = run_scenario(scenario, seed=42, repeat=1, provider="fake")

    assert result.status == "ok"
    assert all(check.passed for check in result.checks)
    fidelity = [
        event
        for event in result.runs[0].event_summaries
        if event.event_type == "attack_requested"
        and event.actor == "Arin"
        and event.target == "Orc Brute"
    ]
    assert fidelity  # the human instruction, executed by the rules engine


def test_cooperation_smoke_passes_offline() -> None:
    scenario = get_scenario("cooperation-smoke")

    result = run_scenario(scenario, seed=42, repeat=1, provider="fake")

    assert result.status == "ok"
    assert all(check.passed for check in result.checks)
    assert result.metrics["party_message_count"] >= 1
```

- [ ] **Step 2: Run to verify failure**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/evaluation/test_scenarios.py tests/evaluation/test_offline_scenarios.py -q`
Expected: FAIL — `unknown scenario: 'instruction-following'` (registry lacks the new names)

- [ ] **Step 3: Write the scenario modules and update the registry**

Create `src/evaluation/scenarios/instruction_following.py`:

```python
"""The instruction-following scenario (spec §4.4.2).

Agents have no instruction channel: the human instruction is executed
deterministically by the player character. (a) player-attack-fidelity
verifies the instruction reaches the engine as an attack from Arin on
Orc Brute; (b) agents-attack-enemies verifies the AI party produces
legal attack proposals against the enemy roster. Offline (scripted
decisions) both hold and validate harness plumbing; live, (a) stays a
harness check and (b) measures whether the model proposes legal attacks.
Ground truth at seed 42: Arin's attack is accepted (a miss), zero
rejections.
"""

from __future__ import annotations

from evaluation.model import Scenario, ScenarioCheck, ScenarioResult

_PARTY_NAMES = ("Brix", "Mira", "Sera")
_ENEMY_NAMES = ("Goblin Scout", "Goblin Skulker", "Orc Brute")


def _player_attack_fidelity(result: ScenarioResult) -> bool:
    for run in result.runs:
        if not any(
            event.event_type == "attack_requested"
            and event.actor == "Arin"
            and event.target == "Orc Brute"
            for event in run.event_summaries
        ):
            return False
    return True


def _agents_attack_enemies(result: ScenarioResult) -> bool:
    for run in result.runs:
        agent_attacks = [
            event
            for event in run.event_summaries
            if event.event_type == "attack_requested" and event.actor in _PARTY_NAMES
        ]
        if not agent_attacks:
            return False
        if any(event.target not in _ENEMY_NAMES for event in agent_attacks):
            return False
    return True


def _no_rejections(result: ScenarioResult) -> bool:
    return result.metrics.get("rejection_count") == 0


INSTRUCTION_FOLLOWING = Scenario(
    name="instruction-following",
    description=(
        "One human instruction ('attack orc brute'): the instruction executes "
        "deterministically through the rules engine, and the AI party keeps "
        "proposing legal attacks against the enemy roster."
    ),
    seed=42,
    steps=("attack orc brute",),
    checks=(
        ScenarioCheck(
            name="player-attack-fidelity",
            description="Arin's attack lands on Orc Brute in every run",
            evaluate=_player_attack_fidelity,
        ),
        ScenarioCheck(
            name="agents-attack-enemies",
            description="every party-agent attack targets an enemy-roster name",
            evaluate=_agents_attack_enemies,
        ),
        ScenarioCheck(
            name="no-rejections",
            description="no action is rejected by the rules engine",
            evaluate=_no_rejections,
        ),
    ),
)
```

Create `src/evaluation/scenarios/cooperation_smoke.py`:

```python
"""The cooperation-smoke scenario (spec §4.4.3): one say, party traffic.

Ground truth at seed 42 (offline): the say triggers a GM reaction with no
state change, the drain-driven fight produces party traffic (the scripted
agents always post one), and nothing is rejected.
"""

from __future__ import annotations

from evaluation.model import Scenario, ScenarioCheck, ScenarioResult


def _party_messages_exchanged(result: ScenarioResult) -> bool:
    count = result.metrics.get("party_message_count")
    return isinstance(count, int) and count >= 1


def _no_rejections(result: ScenarioResult) -> bool:
    return result.metrics.get("rejection_count") == 0


COOPERATION_SMOKE = Scenario(
    name="cooperation-smoke",
    description=(
        "The party holds the line: one human 'say' reaches the GM while the "
        "AI party fights, proving party traffic flows and no action is rejected."
    ),
    seed=42,
    steps=("say hold the line",),
    checks=(
        ScenarioCheck(
            name="party-messages-exchanged",
            description="at least one party message is posted during the run",
            evaluate=_party_messages_exchanged,
        ),
        ScenarioCheck(
            name="no-rejections",
            description="no action is rejected by the rules engine",
            evaluate=_no_rejections,
        ),
    ),
)
```

Replace `src/evaluation/scenarios/__init__.py` in full:

```python
"""Scenario registry (spec §4.2): SCENARIOS maps names to concrete scenarios."""

from collections.abc import Mapping

from evaluation.errors import EvaluationError
from evaluation.model import Scenario
from evaluation.scenarios.cooperation_smoke import COOPERATION_SMOKE
from evaluation.scenarios.goblin_skirmish import GOBLIN_SKIRMISH
from evaluation.scenarios.instruction_following import INSTRUCTION_FOLLOWING

SCENARIOS: Mapping[str, Scenario] = {
    "goblin-skirmish": GOBLIN_SKIRMISH,
    "instruction-following": INSTRUCTION_FOLLOWING,
    "cooperation-smoke": COOPERATION_SMOKE,
}


def get_scenario(name: str) -> Scenario:
    """Look up a scenario by name; unknown names are harness misuse (§5)."""
    try:
        return SCENARIOS[name]
    except KeyError:
        raise EvaluationError(f"unknown scenario: {name!r}") from None
```

- [ ] **Step 3b: Run the offline scenario tests**

Run: `OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/evaluation -q`
Expected: all green — the two new scenarios pass their offline checks (ground truth verified during planning: instruction-following — Arin→Orc Brute accepted, 0 rejections; cooperation-smoke — ≥1 party message, 0 rejections).

- [ ] **Step 4: Docs — README and roadmap**

In `README.md`, add an **Evaluation** section after the existing CLI/observability docs (match the README's current heading style):

````markdown
## Evaluation

Run repeatable, seeded scenarios against real sessions:

```bash
.venv/bin/conclave-eval                              # all scenarios, offline (fake gateways)
.venv/bin/conclave-eval --scenario goblin-skirmish   # one scenario
.venv/bin/conclave-eval --repeat 5 --seed 7          # more runs for consistency stats
OPENROUTER_API_KEY=... .venv/bin/conclave-eval --provider openrouter   # live comparison
```

Reports land in `eval-results/` (git-ignored): one JSON per scenario with checks,
metrics (legal-action rate, rejections, retries, latency p50/p95, tokens/game,
cost/game), per-run event sequences, and invocation summaries — never prompts,
payloads, or keys. Offline runs are fully deterministic (same seed ⇒ same events).
````

In `docs/superpowers/plans/README.md`, change row #9 from:

```markdown
| 9 | `2026-09-10-evaluation-design.md` | Phase 18 — repeatable evaluation scenarios and metrics | Not started |
```

to:

```markdown
| 9 | `2026-09-10-evaluation-design.md` | Phase 18 — repeatable evaluation scenarios and metrics | Complete |
```

- [ ] **Step 5: Full offline gate**

```bash
set -o pipefail
V=$PWD/.venv/bin/python
OPENROUTER_API_KEY= $V -m pytest -q | tail -1
$V -m ruff check .
$V -m mypy | tail -1
```

Expected: **470 passed, 2 deselected**, ruff clean, mypy clean.

- [ ] **Step 6: Domain-diff check**

```bash
git log --oneline master..HEAD -- src/domain
```

Expected: exactly one commit — Task 1's `fix(domain): break initiative ties by participant order, not random ids`.

- [ ] **Step 7: Commit the scenarios and docs**

```bash
git add src/evaluation/scenarios tests/evaluation docs/superpowers/plans/README.md README.md
git commit -m "feat(evaluation): add instruction-following and cooperation-smoke scenarios

instruction-following measures player-attack fidelity (the human
instruction executed through the engine) plus agent-proposal
well-formedness against the enemy roster; cooperation-smoke asserts
party traffic on one say. Registry holds all three; README and roadmap
row 9 updated.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 8: Optional live smoke (manual, never CI)**

Only with a real key exported by the user:

```bash
OPENROUTER_API_KEY=<key> .venv/bin/conclave-eval --scenario goblin-skirmish --provider openrouter
```

Expected: one report in `eval-results/`, status ok or a clean per-scenario error (models are not deterministic; the consistency check may fail live — that is a reported result, not a harness bug). Never commit the key; never add a `live` test for this.

- [ ] **Step 9: Final review checklist (from the spec §10)**

- [ ] Scenario results reproduce offline (same seed ⇒ same event sequence) — Task 5's reproducibility test proves it.
- [ ] Every numeric metric traces to events or enriched invocations — Task 4's unit tests prove it.
- [ ] No prompts, payloads, API keys, or reasoning in any report artifact — Task 6's hygiene test proves it.
- [ ] Evaluation drives only application services; zero rules logic in `src/evaluation/` — review confirms.
- [ ] Domain diff is exactly Task 1's determinism fix; CLI behavior unchanged; full offline suite green — Steps 5–6 prove it.
- [ ] Live mode works with `OPENROUTER_API_KEY` and never runs in CI — Step 8 is manual and unmarked.