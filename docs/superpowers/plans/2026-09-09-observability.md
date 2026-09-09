# Observability (Phase 17) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every LLM call becomes observable — a structured JSON log line, an in-session totals table, and (with `--db postgres`) a persistent Postgres row — always as bookkeeping, never as a gate on the game.

**Architecture:** One enriched frozen `LLMInvocation` record, one application-defined `TelemetrySink` Protocol, three infrastructure sinks (logging, in-RAM, Postgres). The application layer enriches gateway-built records with `dataclasses.replace` (turn context: `game_id`, `agent_id`, per-turn `correlation_id`, `timestamp`, transport `attempt`, `retrieval_count`) and hands them to a composite sink. The CLI composes sinks and surfaces totals.

**Tech Stack:** Python 3.12 stdlib only for the port and sinks (`dataclasses`, `logging`, `json`, `uuid`); psycopg 3 (already a dependency) for the Postgres sink; Rich (already a dependency) for the CLI table. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-09-observability-design.md` — the plan argues from the spec; executors read both.

**Roadmap:** `docs/superpowers/plans/README.md` row #8 (Phase 17).

## Global Constraints

These apply to every task; each task's requirements implicitly include them.

- **Telemetry never gates the game** (spec §4): sink `record()` failures are swallowed inside each sink; the composite drops a sink that raised and reports it once; a Postgres failure degrades to logging-only. Fake-mode determinism is untouched; the offline suite passes without `OPENROUTER_API_KEY`.
- **Domain layer untouched**: `git log master..HEAD -- src/domain` stays empty. Verify in the final task.
- **No secrets, no prompts in telemetry** (§34, §50): `LLMInvocation` never carries prompts, payloads, reasoning, or credentials. Keys come from env vars only (`OPENROUTER_API_KEY`, `DATABASE_URL`); never commit them.
- **Layer boundaries** (spec §5): port in `src/application/telemetry/`, sinks in `src/infrastructure/telemetry/`, enrichment in the three application services, presentation in `src/interfaces/cli/`. Provider names only under `src/infrastructure/`.
- **TEXT id columns (spec deviation, decided)**: spec §3.4 sketches UUID id columns, but a `UUID PRIMARY KEY` cannot be NULL and cannot hold fake-gateway ids (`uuid4().hex` is hex-without-dashes, scripted ids are `req-0001`). Migration 003 uses TEXT ids and stores every id verbatim — simpler than NULL-coercion and it preserves fake-mode determinism. The spec file is amended by this plan's first commit.
- **Type/lint gates**: `ruff check .` clean (line-length 100, select E/F/I/UP/B), `mypy` strict clean on `src` (tests are not type-checked). No first-party isort section: one alphabetical import block per file — stdlib, then `ai` < `application` < `domain` < `infrastructure` < `interfaces`.
- **Baseline** (verified 2026-09-09 on master `ce90830`): `OPENROUTER_API_KEY= .venv/bin/python -m pytest -q` → **396 passed, 2 skipped**. Every task gate below projects exact totals from this baseline.
- **Gate pattern** — always `set -o pipefail` first (a masked exit code once committed failing code):

```bash
set -o pipefail
V=$PWD/.venv/bin/python
$V -m pytest <test files> -q | tail -1
$V -m ruff check .
$V -m mypy | tail -1
OPENROUTER_API_KEY= $V -m pytest -q | tail -1
```

- **Worktree sandbox** (recorded in session memory): plain commands only — no `printf |` into python, no env-var prefix on `python -c`. Write scripted CLI input to a file, then run `.venv/bin/python -c "import sys; sys.path.insert(0, 'src'); from interfaces.cli.app import main; sys.exit(main(sys.argv[1:]))" --agent fake < /tmp/input.txt > /tmp/out.txt`. Env-prefixed pytest (`OPENROUTER_API_KEY= pytest`) is accepted.
- **Worktree base**: `EnterWorktree` branches from `origin/master`; local `master` is ahead (the spec and plan commits). On first entry run `git merge master --ff-only` inside the worktree.
- **Commits**: conventional, scoped by layer; every message ends with `Co-Authored-By: Claude Code <noreply@anthropic.com>`.

## File Structure

| File | Responsibility |
|---|---|
| `src/ai/models/types.py` | Enriched frozen `LLMInvocation` (7 new defaulted fields) |
| `src/application/telemetry/__init__.py` | `TelemetrySink` Protocol, `CompositeTelemetrySink`, `stamp_invocation`, `new_correlation_id`, `TELEMETRY_LOGGER` |
| `src/infrastructure/telemetry/__init__.py` | package docstring |
| `src/infrastructure/telemetry/in_memory.py` | `InMemoryTelemetrySink` + `TelemetryTotals` |
| `src/infrastructure/telemetry/logging_sink.py` | `LoggingTelemetrySink` + `configure_telemetry_logging` |
| `src/infrastructure/telemetry/postgres.py` | `PostgresTelemetrySink` |
| `src/infrastructure/persistence/postgres/migrations/003_llm_invocations.sql` | table + indexes |
| `src/ai/agents/runtime.py` | stamps transport `attempt` on invocations |
| `src/application/agents/agent_turn_service.py` | enrich + record turn invocations |
| `src/application/gm/director.py` | enrich + record GM invocations |
| `src/application/memory/memory_service.py` | enrich + record embed invocations |
| `src/interfaces/cli/app.py` | `--debug`, `/telemetry`, session summary, sink composition |
| `src/ai/models/profiles.py` | explicit `default_provider` (carry-forward) |
| `pyproject.toml` | `live` marker + `addopts = ["-m", "not live"]` |
| `tests/ai/models/test_types.py`, `tests/ai/agents/test_runtime.py`, `tests/ai/models/test_profiles.py` | AI-layer tests |
| `tests/application/telemetry/test_telemetry_port.py` | port + composite tests |
| `tests/infrastructure/telemetry/test_in_memory_sink.py` | RAM sink tests |
| `tests/infrastructure/telemetry/test_logging_sink.py` | logging sink tests |
| `tests/infrastructure/test_postgres_telemetry.py` | Postgres sink tests |
| `tests/application/agents/test_agent_turn_service.py`, `tests/application/gm/test_gm_director.py`, `tests/application/memory/test_memory_service.py` | enrichment tests |
| `tests/interfaces/test_cli.py` | CLI surfacing tests |
| `tests/integration/test_openrouter_live.py` | `live` marker |
| `README.md` | observability + live-test docs |

---

### Task 1: Enriched `LLMInvocation`

**Files:**
- Modify: `src/ai/models/types.py:34-47` (the `LLMInvocation` dataclass)
- Test: `tests/ai/models/test_types.py`

**Interfaces:**
- Consumes: existing 10-field `LLMInvocation` (all construction sites keep working — new fields have defaults).
- Produces: `LLMInvocation` with `timestamp: str | None = None`, `game_id: str | None = None`, `agent_id: str | None = None`, `correlation_id: str | None = None`, `attempt: int = 1`, `retrieval_count: int = 0`, `tools_called: int = 0` (in that order, after `request_id`). Tasks 2–6 consume these names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ai/models/test_types.py`:

```python
def test_llm_invocation_telemetry_fields_have_defaults() -> None:
    invocation = _invocation()

    assert invocation.timestamp is None
    assert invocation.game_id is None
    assert invocation.agent_id is None
    assert invocation.correlation_id is None
    assert invocation.attempt == 1
    assert invocation.retrieval_count == 0
    assert invocation.tools_called == 0


def test_llm_invocation_is_enrichable_with_replace() -> None:
    original = _invocation()

    enriched = replace(
        original,
        timestamp="2026-09-09T12:00:00+00:00",
        game_id="game-1",
        agent_id="brix",
        correlation_id="corr-1",
        attempt=2,
        retrieval_count=3,
    )

    assert enriched.game_id == "game-1"
    assert enriched.agent_id == "brix"
    assert enriched.correlation_id == "corr-1"
    assert enriched.attempt == 2
    assert enriched.retrieval_count == 3
    assert enriched.provider == "fake"  # transport facts survive enrichment
    # the original frozen record is untouched
    assert original.game_id is None
    assert original.attempt == 1
```

Also extend the stdlib import block at the top of the file — change:

```python
from dataclasses import FrozenInstanceError
```

to:

```python
from dataclasses import FrozenInstanceError, replace
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/ai/models/test_types.py -q | tail -1`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'timestamp'`-style errors (the new fields do not exist yet) — 2 failures.

- [ ] **Step 3: Implement the enriched record**

In `src/ai/models/types.py`, replace the `LLMInvocation` dataclass with:

```python
@dataclass(frozen=True)
class LLMInvocation:
    """Per-call telemetry metadata (CLAUDE.md §34). Never prompts, payloads, or reasoning."""

    provider: str
    model: str
    operation: str
    status: str
    error_kind: str | None
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    request_id: str
    # Turn-context enrichment (Phase 17, spec §3.1): stamped by the application
    # layer; every field defaults so gateway construction sites stay unchanged.
    timestamp: str | None = None
    game_id: str | None = None
    agent_id: str | None = None
    correlation_id: str | None = None
    attempt: int = 1
    retrieval_count: int = 0
    tools_called: int = 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/ai/models/test_types.py -q | tail -1`
Expected: all pass.

- [ ] **Step 5: Run the gate**

```bash
set -o pipefail
V=$PWD/.venv/bin/python
$V -m ruff check . && $V -m mypy | tail -1 && OPENROUTER_API_KEY= $V -m pytest -q | tail -1
```

Expected: ruff clean, mypy clean, **398 passed, 2 skipped**.

- [ ] **Step 6: Commit**

```bash
git add src/ai/models/types.py tests/ai/models/test_types.py
git commit -m "feat(ai): enrich LLMInvocation with turn-context telemetry fields

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: `TelemetrySink` port, composite, and in-RAM sink

**Files:**
- Create: `src/application/telemetry/__init__.py`
- Create: `src/infrastructure/telemetry/__init__.py`
- Create: `src/infrastructure/telemetry/in_memory.py`
- Create: `tests/application/telemetry/test_telemetry_port.py`
- Create: `tests/infrastructure/telemetry/test_in_memory_sink.py`

**Interfaces:**
- Consumes: enriched `LLMInvocation` (Task 1).
- Produces (used by Tasks 3–6):
  - `application.telemetry.TELEMETRY_LOGGER = "conclave.telemetry"`
  - `class TelemetrySink(Protocol): def record(self, invocation: LLMInvocation) -> None: ...`
  - `new_correlation_id() -> str`
  - `stamp_invocation(invocation: LLMInvocation, *, game_id: str | None, agent_id: str | None, correlation_id: str | None) -> LLMInvocation` (stamps `timestamp` too)
  - `class CompositeTelemetrySink: __init__(self, sinks: Sequence[TelemetrySink]) -> None; record(self, invocation: LLMInvocation) -> None` (drops a sink that raised, reports once)
  - `infrastructure.telemetry.in_memory.InMemoryTelemetrySink` (same `record`) + `.snapshot() -> tuple[TelemetryTotals, ...]`, `TelemetryTotals(key, role, calls, retries, input_tokens, output_tokens, estimated_cost_usd)` frozen dataclass with `.total_tokens` property.

- [ ] **Step 1: Write the failing port tests**

Create `tests/application/telemetry/test_telemetry_port.py`:

```python
# tests/application/telemetry/test_telemetry_port.py
"""TelemetrySink port and composite tests (Phase 17, spec §3.3, §4)."""

import logging
from datetime import datetime

from ai.models.types import LLMInvocation
from application.telemetry import (
    CompositeTelemetrySink,
    TelemetrySink,
    stamp_invocation,
)


def _invocation(**overrides: object) -> LLMInvocation:
    values: dict[str, object] = {
        "provider": "fake",
        "model": "test-model",
        "operation": "generate_structured",
        "status": "ok",
        "error_kind": None,
        "latency_ms": 5,
        "input_tokens": 10,
        "output_tokens": 5,
        "estimated_cost_usd": None,
        "request_id": "req-1",
    }
    values.update(overrides)
    return LLMInvocation(**values)  # type: ignore[arg-type]


class _RecordingSink:
    """Sink double: records invocations, or explodes on demand."""

    def __init__(self, *, name: str, explode: bool = False) -> None:
        self.name = name
        self.explode = explode
        self.records: list[LLMInvocation] = []

    def record(self, invocation: LLMInvocation) -> None:
        if self.explode:
            raise RuntimeError(f"boom from {self.name}")
        self.records.append(invocation)


def test_composite_calls_sinks_in_order() -> None:
    first = _RecordingSink(name="a")
    second = _RecordingSink(name="b")
    sink: TelemetrySink = CompositeTelemetrySink([first, second])
    invocation = _invocation()

    sink.record(invocation)

    assert first.records == [invocation]
    assert second.records == [invocation]


def test_composite_drops_a_broken_sink_after_one_report(caplog) -> None:
    broken = _RecordingSink(name="broken", explode=True)
    healthy = _RecordingSink(name="healthy")
    sink = CompositeTelemetrySink([broken, healthy])
    invocation = _invocation()

    sink.record(invocation)
    sink.record(invocation)  # the dropped sink is never called again

    assert broken.records == []
    assert healthy.records == [invocation, invocation]
    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "boom from broken" in warnings[0].getMessage()


def test_composite_survives_when_every_sink_is_dropped() -> None:
    broken = _RecordingSink(name="broken", explode=True)
    sink: TelemetrySink = CompositeTelemetrySink([broken])

    sink.record(_invocation())  # the only sink gets dropped
    sink.record(_invocation())  # the composite must not raise

    assert True  # reaching here is the assertion


def test_stamp_invocation_enriches_without_mutating() -> None:
    original = _invocation()

    stamped = stamp_invocation(
        original, game_id="game-1", agent_id="brix", correlation_id="corr-1"
    )

    assert stamped.game_id == "game-1"
    assert stamped.agent_id == "brix"
    assert stamped.correlation_id == "corr-1"
    assert stamped.timestamp is not None
    datetime.fromisoformat(stamped.timestamp)  # UTC ISO-8601, parseable
    assert original.game_id is None and original.timestamp is None
```

- [ ] **Step 2: Run the port tests to verify they fail**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/application/telemetry/test_telemetry_port.py -q | tail -1`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.telemetry'`.

- [ ] **Step 3: Implement the port and composite**

Create `src/application/telemetry/__init__.py`:

```python
"""Telemetry port: sinks receive enriched LLMInvocation records (spec §3.3).

The application layer owns the port; infrastructure provides sinks. Recording
is bookkeeping, never a gate (CLAUDE.md §28, §66): the composite drops a sink
that raised, reports it once, and the game continues.
"""

import dataclasses
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from ai.models.types import LLMInvocation

TELEMETRY_LOGGER = "conclave.telemetry"


class TelemetrySink(Protocol):
    """One destination for enriched LLM telemetry records."""

    def record(self, invocation: LLMInvocation) -> None: ...


def new_correlation_id() -> str:
    """One fresh correlation id per turn, shared by every call servicing it (§3.2)."""
    return uuid.uuid4().hex


def stamp_invocation(
    invocation: LLMInvocation,
    *,
    game_id: str | None,
    agent_id: str | None,
    correlation_id: str | None,
) -> LLMInvocation:
    """Enrich a frozen record with turn context; total and side-effect-free."""
    return dataclasses.replace(
        invocation,
        timestamp=datetime.now(UTC).isoformat(),
        game_id=game_id,
        agent_id=agent_id,
        correlation_id=correlation_id,
    )


class CompositeTelemetrySink:
    """Calls sinks in order; drops and reports a sink that raised (spec §4)."""

    def __init__(self, sinks: Sequence[TelemetrySink]) -> None:
        self._sinks = list(sinks)

    def record(self, invocation: LLMInvocation) -> None:
        for sink in list(self._sinks):
            try:
                sink.record(invocation)
            except Exception as error:  # noqa: BLE001 - telemetry never gates the game
                self._sinks.remove(sink)
                logging.getLogger(TELEMETRY_LOGGER).warning(
                    "telemetry sink %s dropped after failure: %s",
                    type(sink).__name__,
                    error,
                )
```

- [ ] **Step 4: Run the port tests to verify they pass**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/application/telemetry/test_telemetry_port.py -q | tail -1`
Expected: 4 passed.

- [ ] **Step 5: Write the failing in-RAM sink tests**

Create `tests/infrastructure/telemetry/test_in_memory_sink.py`:

```python
# tests/infrastructure/telemetry/test_in_memory_sink.py
"""InMemoryTelemetrySink aggregate tests (Phase 17, spec §3.4)."""

import pytest

from ai.models.types import LLMInvocation
from infrastructure.telemetry.in_memory import InMemoryTelemetrySink


def _invocation(**overrides: object) -> LLMInvocation:
    values: dict[str, object] = {
        "provider": "fake",
        "model": "test-model",
        "operation": "generate_structured",
        "status": "ok",
        "error_kind": None,
        "latency_ms": 5,
        "input_tokens": 10,
        "output_tokens": 5,
        "estimated_cost_usd": None,
        "request_id": "req-1",
    }
    values.update(overrides)
    return LLMInvocation(**values)  # type: ignore[arg-type]


def test_snapshot_on_an_empty_session_is_empty() -> None:
    assert InMemoryTelemetrySink().snapshot() == ()


def test_snapshot_groups_by_agent_and_role() -> None:
    sink = InMemoryTelemetrySink()
    sink.record(_invocation(agent_id="gm"))
    sink.record(_invocation(agent_id="brix"))
    sink.record(_invocation(agent_id="brix", operation="embed"))
    sink.record(_invocation())  # unenriched: the key falls back to the role

    totals = sink.snapshot()

    assert [(total.key, total.role) for total in totals] == [
        ("brix", "embedding"),
        ("brix", "player-agent"),
        ("gm", "gm"),
        ("player-agent", "player-agent"),
    ]


def test_snapshot_counts_retries_tokens_and_cost() -> None:
    sink = InMemoryTelemetrySink()
    sink.record(_invocation())
    sink.record(
        _invocation(attempt=2, input_tokens=20, output_tokens=10, estimated_cost_usd=0.002)
    )
    sink.record(_invocation(input_tokens=None, output_tokens=None, estimated_cost_usd=None))

    totals = sink.snapshot()

    assert len(totals) == 1
    row = totals[0]
    assert row.calls == 3
    assert row.retries == 1
    assert row.input_tokens == 30
    assert row.output_tokens == 15
    assert row.total_tokens == 40
    assert row.estimated_cost_usd == pytest.approx(0.002)
```

- [ ] **Step 6: Run the in-RAM sink tests to verify they fail**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/infrastructure/telemetry/test_in_memory_sink.py -q | tail -1`
Expected: FAIL — `ModuleNotFoundError: No module named 'infrastructure.telemetry'`.

- [ ] **Step 7: Implement the in-RAM sink**

Create `src/infrastructure/telemetry/__init__.py`:

```python
"""Telemetry sinks: logging, in-RAM session totals, and Postgres persistence."""
```

Create `src/infrastructure/telemetry/in_memory.py`:

```python
"""Per-session RAM accumulator for LLM telemetry (Phase 17, spec §3.4)."""

from dataclasses import dataclass

from ai.models.types import LLMInvocation

_EMBED_OPERATION = "embed"


def _role_for(invocation: LLMInvocation) -> str:
    if invocation.agent_id == "gm":
        return "gm"
    if invocation.operation == _EMBED_OPERATION:
        return "embedding"
    return "player-agent"


@dataclass(frozen=True)
class TelemetryTotals:
    """Aggregates for one (agent, role) bucket of the session."""

    key: str
    role: str
    calls: int
    retries: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class InMemoryTelemetrySink:
    """Accumulates records in RAM; snapshot() returns per-(agent, role) totals."""

    def __init__(self) -> None:
        self._records: list[LLMInvocation] = []

    def record(self, invocation: LLMInvocation) -> None:
        self._records.append(invocation)

    def snapshot(self) -> tuple[TelemetryTotals, ...]:
        buckets: dict[tuple[str, str], list[LLMInvocation]] = {}
        for record in self._records:
            role = _role_for(record)
            key = record.agent_id if record.agent_id else role
            buckets.setdefault((key, role), []).append(record)
        return tuple(
            TelemetryTotals(
                key=key,
                role=role,
                calls=len(records),
                retries=sum(1 for record in records if record.attempt > 1),
                input_tokens=sum(record.input_tokens or 0 for record in records),
                output_tokens=sum(record.output_tokens or 0 for record in records),
                estimated_cost_usd=sum(
                    record.estimated_cost_usd or 0.0 for record in records
                ),
            )
            for (key, role), records in sorted(buckets.items())
        )
```

- [ ] **Step 8: Run the in-RAM sink tests to verify they pass**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/infrastructure/telemetry/test_in_memory_sink.py -q | tail -1`
Expected: 3 passed.

- [ ] **Step 9: Run the gate**

```bash
set -o pipefail
V=$PWD/.venv/bin/python
$V -m ruff check . && $V -m mypy | tail -1 && OPENROUTER_API_KEY= $V -m pytest -q | tail -1
```

Expected: ruff clean, mypy clean, **405 passed, 2 skipped**.

- [ ] **Step 10: Commit**

```bash
git add src/application/telemetry tests/application/telemetry
git commit -m "feat(application): add the TelemetrySink port and composite sink

Co-Authored-By: Claude Code <noreply@anthropic.com>"
git add src/infrastructure/telemetry tests/infrastructure/telemetry
git commit -m "feat(infrastructure): add the in-RAM telemetry sink

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Logging telemetry sink

**Files:**
- Create: `src/infrastructure/telemetry/logging_sink.py`
- Create: `tests/infrastructure/telemetry/test_logging_sink.py`

**Interfaces:**
- Consumes: `LLMInvocation` (Task 1), `TELEMETRY_LOGGER` (Task 2).
- Produces (used by Task 6):
  - `configure_telemetry_logging(*, debug: bool = False) -> None` — attaches the handler (FileHandler when `CONCLAVE_TELEMETRY_LOG` holds a path, else stderr), sets level DEBUG when `debug` else WARNING.
  - `class LoggingTelemetrySink: __init__(self, logger: logging.Logger | None = None) -> None; record(self, invocation: LLMInvocation) -> None` — one JSON line per record at DEBUG.

- [ ] **Step 1: Write the failing tests**

Create `tests/infrastructure/telemetry/test_logging_sink.py`:

```python
# tests/infrastructure/telemetry/test_logging_sink.py
"""LoggingTelemetrySink tests: JSON shape, level gating, never-gates policy."""

import json
import logging

from ai.models.types import LLMInvocation
from infrastructure.telemetry.logging_sink import (
    LoggingTelemetrySink,
    configure_telemetry_logging,
)


def _invocation(**overrides: object) -> LLMInvocation:
    values: dict[str, object] = {
        "provider": "fake",
        "model": "test-model",
        "operation": "generate_structured",
        "status": "ok",
        "error_kind": None,
        "latency_ms": 5,
        "input_tokens": 10,
        "output_tokens": 5,
        "estimated_cost_usd": 0.001,
        "request_id": "req-1",
        "timestamp": "2026-09-09T12:00:00+00:00",
        "game_id": "game-1",
        "agent_id": "brix",
        "correlation_id": "corr-1",
        "attempt": 2,
        "retrieval_count": 3,
        "tools_called": 0,
    }
    values.update(overrides)
    return LLMInvocation(**values)  # type: ignore[arg-type]


_EXPECTED_KEYS = {
    "ts",
    "event",
    "game_id",
    "agent_id",
    "correlation_id",
    "request_id",
    "provider",
    "model",
    "operation",
    "status",
    "error_kind",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost_usd",
    "attempt",
    "retrieval_count",
    "tools_called",
}


def test_record_writes_one_json_line_per_invocation(tmp_path, monkeypatch) -> None:
    log_file = tmp_path / "telemetry.jsonl"
    monkeypatch.setenv("CONCLAVE_TELEMETRY_LOG", str(log_file))
    configure_telemetry_logging(debug=True)

    LoggingTelemetrySink().record(_invocation())
    for handler in logging.getLogger("conclave.telemetry").handlers:
        handler.flush()

    payload = json.loads(log_file.read_text(encoding="utf-8"))
    assert set(payload) == _EXPECTED_KEYS
    assert payload["event"] == "llm_invocation"
    assert payload["provider"] == "fake"
    assert payload["model"] == "test-model"
    assert payload["operation"] == "generate_structured"
    assert payload["status"] == "ok"
    assert payload["request_id"] == "req-1"
    assert payload["game_id"] == "game-1"
    assert payload["agent_id"] == "brix"
    assert payload["correlation_id"] == "corr-1"
    assert payload["ts"] == "2026-09-09T12:00:00+00:00"
    assert payload["latency_ms"] == 5
    assert payload["input_tokens"] == 10
    assert payload["output_tokens"] == 5
    assert payload["total_tokens"] == 15
    assert payload["estimated_cost_usd"] == 0.001
    assert payload["attempt"] == 2
    assert payload["retrieval_count"] == 3
    assert payload["tools_called"] == 0


def test_telemetry_is_silent_by_default_and_debug_enables_it(
    tmp_path, monkeypatch
) -> None:
    log_file = tmp_path / "telemetry.jsonl"
    monkeypatch.setenv("CONCLAVE_TELEMETRY_LOG", str(log_file))
    sink = LoggingTelemetrySink()

    configure_telemetry_logging(debug=False)
    sink.record(_invocation())
    for handler in logging.getLogger("conclave.telemetry").handlers:
        handler.flush()
    assert log_file.read_text(encoding="utf-8") == ""

    configure_telemetry_logging(debug=True)
    sink.record(_invocation())
    for handler in logging.getLogger("conclave.telemetry").handlers:
        handler.flush()
    assert len(log_file.read_text(encoding="utf-8").splitlines()) == 1


def test_record_failures_are_swallowed() -> None:
    class _BoomLogger:
        def debug(self, *args: object) -> None:
            raise RuntimeError("disk full")

    LoggingTelemetrySink(logger=_BoomLogger()).record(_invocation())  # must not raise
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/infrastructure/telemetry/test_logging_sink.py -q | tail -1`
Expected: FAIL — `ImportError: cannot import name 'LoggingTelemetrySink'`.

- [ ] **Step 3: Implement the sink**

Create `src/infrastructure/telemetry/logging_sink.py`:

```python
"""Stdlib-logging telemetry sink: one JSON line per invocation (spec §3.4).

The telemetry logger is silent by default (WARNING); `--debug` moves it to
DEBUG so per-call lines reach stderr or the CONCLAVE_TELEMETRY_LOG file.
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime

from ai.models.types import LLMInvocation
from application.telemetry import TELEMETRY_LOGGER


def configure_telemetry_logging(*, debug: bool = False) -> None:
    """(Re)attach the telemetry handler; WARNING unless --debug (spec §3.6)."""
    logger = logging.getLogger(TELEMETRY_LOGGER)
    path = os.environ.get("CONCLAVE_TELEMETRY_LOG")
    if path:
        handler: logging.Handler = logging.FileHandler(path)
    else:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    for old in logger.handlers:
        old.close()
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG if debug else logging.WARNING)


class LoggingTelemetrySink:
    """Emits one JSON object per invocation at DEBUG on the telemetry logger."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger if logger is not None else logging.getLogger(TELEMETRY_LOGGER)

    def record(self, invocation: LLMInvocation) -> None:
        try:
            self._logger.debug(json.dumps(_payload(invocation), sort_keys=True))
        except Exception:  # noqa: BLE001 - telemetry never gates the game (spec §4)
            pass


def _payload(invocation: LLMInvocation) -> dict[str, object]:
    input_tokens = invocation.input_tokens
    output_tokens = invocation.output_tokens
    total = (
        input_tokens + output_tokens
        if input_tokens is not None and output_tokens is not None
        else None
    )
    return {
        "ts": invocation.timestamp or datetime.now(UTC).isoformat(),
        "event": "llm_invocation",
        "game_id": invocation.game_id,
        "agent_id": invocation.agent_id,
        "correlation_id": invocation.correlation_id,
        "request_id": invocation.request_id,
        "provider": invocation.provider,
        "model": invocation.model,
        "operation": invocation.operation,
        "status": invocation.status,
        "error_kind": invocation.error_kind,
        "latency_ms": invocation.latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
        "estimated_cost_usd": invocation.estimated_cost_usd,
        "attempt": invocation.attempt,
        "retrieval_count": invocation.retrieval_count,
        "tools_called": invocation.tools_called,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/infrastructure/telemetry/test_logging_sink.py -q | tail -1`
Expected: 3 passed.

- [ ] **Step 5: Run the gate**

```bash
set -o pipefail
V=$PWD/.venv/bin/python
$V -m ruff check . && $V -m mypy | tail -1 && OPENROUTER_API_KEY= $V -m pytest -q | tail -1
```

Expected: ruff clean, mypy clean, **408 passed, 2 skipped**.

- [ ] **Step 6: Commit**

```bash
git add src/infrastructure/telemetry/logging_sink.py tests/infrastructure/telemetry/test_logging_sink.py
git commit -m "feat(infrastructure): add the JSON logging telemetry sink

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: Postgres telemetry sink + migration 003

**Files:**
- Create: `src/infrastructure/persistence/postgres/migrations/003_llm_invocations.sql`
- Create: `src/infrastructure/telemetry/postgres.py`
- Modify: `tests/infrastructure/test_postgres_migrations.py:21,29,44` (regression: migration 003 changes the applied set)
- Create: `tests/infrastructure/test_postgres_telemetry.py`

**Interfaces:**
- Consumes: `LLMInvocation` (Task 1), `TelemetrySink` (Task 2), `connect()` from `infrastructure.persistence.postgres.connection`, the pgserver `postgres_url` session fixture from `tests/conftest.py`.
- Produces (used by Task 6): `class PostgresTelemetrySink: __init__(self, connection: psycopg.Connection[dict[str, Any]]) -> None; record(self, invocation: LLMInvocation) -> None` — one plain-SQL INSERT per record; failures log at most one WARNING and never raise.

**Known regression (must be fixed in this task):** `tests/infrastructure/test_postgres_migrations.py` asserts `applied == [1, 2]` twice; migration 003 breaks both assertions. Update both to `[1, 2, 3]` and add `llm_invocations` to the expected-tables subset.

- [ ] **Step 1: Write the failing migration + sink tests**

Create `tests/infrastructure/test_postgres_telemetry.py`:

```python
# tests/infrastructure/test_postgres_telemetry.py
"""PostgresTelemetrySink round-trip and never-gates tests (Phase 17, spec §3.4)."""

import logging
from datetime import UTC, datetime

import pytest

from ai.models.types import LLMInvocation
from infrastructure.persistence.postgres.connection import connect
from infrastructure.telemetry.postgres import PostgresTelemetrySink


def test_sink_round_trips_an_enriched_invocation(postgres_url: str) -> None:
    connection = connect(postgres_url)
    sink = PostgresTelemetrySink(connection)

    sink.record(
        LLMInvocation(
            provider="openrouter",
            model="z-ai/glm-5.3-flash",
            operation="generate_structured",
            status="ok",
            error_kind=None,
            latency_ms=120,
            input_tokens=100,
            output_tokens=40,
            estimated_cost_usd=0.000123,
            request_id="11111111-1111-1111-1111-111111111111",
            timestamp="2026-09-09T12:00:00+00:00",
            game_id="00000000-0000-0000-0000-000000000001",
            agent_id="brix",
            correlation_id="corr-1",
            attempt=2,
            retrieval_count=3,
            tools_called=0,
        )
    )

    row = connection.execute(
        "SELECT * FROM llm_invocations WHERE request_id = %s",
        ("11111111-1111-1111-1111-111111111111",),
    ).fetchone()
    assert row is not None
    assert row["provider"] == "openrouter"
    assert row["model"] == "z-ai/glm-5.3-flash"
    assert row["operation"] == "generate_structured"
    assert row["status"] == "ok"
    assert row["error_kind"] is None
    assert row["latency_ms"] == 120
    assert row["input_tokens"] == 100
    assert row["output_tokens"] == 40
    assert float(row["estimated_cost_usd"]) == pytest.approx(0.000123)
    assert row["attempt"] == 2
    assert row["retrieval_count"] == 3
    assert row["tools_called"] == 0
    assert row["game_id"] == "00000000-0000-0000-0000-000000000001"
    assert row["agent_id"] == "brix"
    assert row["correlation_id"] == "corr-1"
    assert row["timestamp"] == datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    connection.close()


def test_non_uuid_ids_are_stored_as_text(postgres_url: str) -> None:
    """Fake-gateway ids (req-0001) and character keys (brix) persist verbatim."""
    connection = connect(postgres_url)
    sink = PostgresTelemetrySink(connection)

    sink.record(
        LLMInvocation(
            provider="deterministic",
            model="test-model",
            operation="embed",
            status="ok",
            error_kind=None,
            latency_ms=0,
            input_tokens=6,
            output_tokens=0,
            estimated_cost_usd=None,
            request_id="req-0001",
            game_id="game-1",
            agent_id="brix",
        )
    )

    row = connection.execute(
        "SELECT * FROM llm_invocations WHERE request_id = %s", ("req-0001",)
    ).fetchone()
    assert row is not None
    assert row["request_id"] == "req-0001"
    assert row["game_id"] == "game-1"
    assert row["agent_id"] == "brix"
    assert row["correlation_id"] is None
    assert row["attempt"] == 1  # column defaults applied
    assert row["retrieval_count"] == 0
    assert row["tools_called"] == 0
    assert row["timestamp"] is not None  # NOT NULL DEFAULT now() filled it
    connection.close()


def test_a_failed_insert_never_raises_and_warns_once(
    postgres_url: str, caplog
) -> None:
    """A duplicate request_id violates the PRIMARY KEY; the sink swallows it."""
    connection = connect(postgres_url)
    sink = PostgresTelemetrySink(connection)
    invocation = LLMInvocation(
        provider="fake",
        model="test-model",
        operation="generate_structured",
        status="ok",
        error_kind=None,
        latency_ms=1,
        input_tokens=1,
        output_tokens=1,
        estimated_cost_usd=None,
        request_id="dup-1",
    )

    sink.record(invocation)
    sink.record(invocation)  # PRIMARY KEY violation → swallowed, no raise

    row = connection.execute(
        "SELECT count(*) AS n FROM llm_invocations WHERE request_id = %s", ("dup-1",)
    ).fetchone()
    assert row is not None and row["n"] == 1
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    connection.close()
```

Also update `tests/infrastructure/test_postgres_migrations.py`:

- line 21: `assert {"games", "game_events", "schema_migrations"} <= tables` → `assert {"games", "game_events", "schema_migrations", "llm_invocations"} <= tables`
- line 29: `assert applied == [1, 2]` → `assert applied == [1, 2, 3]`
- line 44: `assert applied == [1, 2]` → `assert applied == [1, 2, 3]`

- [ ] **Step 2: Run the tests to verify they fail**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/infrastructure/test_postgres_telemetry.py tests/infrastructure/test_postgres_migrations.py -q | tail -1`
Expected: FAIL — 3 failures in the telemetry file (`no such table: llm_invocations`), plus the two migrations tests failing their updated `[1, 2, 3]` assertions.

- [ ] **Step 3: Write migration 003 and the sink**

Create `src/infrastructure/persistence/postgres/migrations/003_llm_invocations.sql`:

```sql
-- 003_llm_invocations.sql — per-call LLM telemetry (Phase 17, spec §3.4).
-- Id columns are TEXT, not UUID: fake gateways use ids like uuid4().hex and
-- scripted ids like req-0001, which a UUID PRIMARY KEY can neither be NULL
-- for nor hold. Telemetry must never fail the game (spec §4).
CREATE TABLE llm_invocations (
    request_id         TEXT PRIMARY KEY,
    game_id            TEXT,
    agent_id           TEXT,
    correlation_id     TEXT,
    provider           TEXT NOT NULL,
    model              TEXT NOT NULL,
    operation          TEXT NOT NULL,
    status             TEXT NOT NULL,
    error_kind         TEXT,
    latency_ms         INTEGER,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    estimated_cost_usd NUMERIC(12, 6),
    attempt            INTEGER NOT NULL DEFAULT 1,
    retrieval_count    INTEGER NOT NULL DEFAULT 0,
    tools_called       INTEGER NOT NULL DEFAULT 0,
    timestamp          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX llm_invocations_game_idx ON llm_invocations (game_id);
CREATE INDEX llm_invocations_correlation_idx ON llm_invocations (correlation_id);
```

Create `src/infrastructure/telemetry/postgres.py`:

```python
"""PostgreSQL telemetry sink: one row per LLM invocation (Phase 17, spec §3.4)."""

import logging
from datetime import UTC, datetime
from typing import Any

import psycopg

from ai.models.types import LLMInvocation
from application.telemetry import TELEMETRY_LOGGER
from domain.common.errors import PersistenceError

_INSERT_INVOCATION = """
INSERT INTO llm_invocations (
    request_id, game_id, agent_id, correlation_id,
    provider, model, operation, status, error_kind,
    latency_ms, input_tokens, output_tokens, estimated_cost_usd,
    attempt, retrieval_count, tools_called, timestamp
) VALUES (
    %(request_id)s, %(game_id)s, %(agent_id)s, %(correlation_id)s,
    %(provider)s, %(model)s, %(operation)s, %(status)s, %(error_kind)s,
    %(latency_ms)s, %(input_tokens)s, %(output_tokens)s, %(estimated_cost_usd)s,
    %(attempt)s, %(retrieval_count)s, %(tools_called)s, %(timestamp)s::timestamptz
)
"""


def _row(invocation: LLMInvocation) -> dict[str, Any]:
    return {
        "request_id": invocation.request_id,
        "game_id": invocation.game_id,
        "agent_id": invocation.agent_id,
        "correlation_id": invocation.correlation_id,
        "provider": invocation.provider,
        "model": invocation.model,
        "operation": invocation.operation,
        "status": invocation.status,
        "error_kind": invocation.error_kind,
        "latency_ms": invocation.latency_ms,
        "input_tokens": invocation.input_tokens,
        "output_tokens": invocation.output_tokens,
        "estimated_cost_usd": invocation.estimated_cost_usd,
        "attempt": invocation.attempt,
        "retrieval_count": invocation.retrieval_count,
        "tools_called": invocation.tools_called,
        "timestamp": invocation.timestamp or datetime.now(UTC).isoformat(),
    }


class PostgresTelemetrySink:
    """Plain-SQL INSERT per record; failures degrade to one WARNING (spec §4)."""

    def __init__(self, connection: psycopg.Connection[dict[str, Any]]) -> None:
        self._connection = connection
        self._warned = False

    def record(self, invocation: LLMInvocation) -> None:
        try:
            self._connection.execute(_INSERT_INVOCATION, _row(invocation))
        except (psycopg.Error, PersistenceError):
            if not self._warned:
                self._warned = True
                logging.getLogger(TELEMETRY_LOGGER).warning(
                    "Postgres telemetry unavailable; degrading to logging-only"
                )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/infrastructure/test_postgres_telemetry.py tests/infrastructure/test_postgres_migrations.py -q | tail -1`
Expected: all pass (5 in the two files, provided pgserver is installed; they skip cleanly otherwise).

- [ ] **Step 5: Run the gate**

```bash
set -o pipefail
V=$PWD/.venv/bin/python
$V -m ruff check . && $V -m mypy | tail -1 && OPENROUTER_API_KEY= $V -m pytest -q | tail -1
```

Expected: ruff clean, mypy clean, **411 passed, 2 skipped**.

- [ ] **Step 6: Commit**

```bash
git add src/infrastructure/persistence/postgres/migrations/003_llm_invocations.sql src/infrastructure/telemetry/postgres.py tests/infrastructure/test_postgres_telemetry.py tests/infrastructure/test_postgres_migrations.py
git commit -m "feat(infrastructure): persist LLM telemetry to Postgres (migration 003)

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: Enrichment wiring (runtime attempt + three services)

**Files:**
- Modify: `src/ai/agents/runtime.py` (stamp transport attempt)
- Modify: `src/application/agents/agent_turn_service.py`
- Modify: `src/application/gm/director.py`
- Modify: `src/application/memory/memory_service.py`
- Test: `tests/ai/agents/test_runtime.py`, `tests/application/agents/test_agent_turn_service.py`, `tests/application/memory/test_memory_service.py`, `tests/application/gm/test_gm_director.py`

**Interfaces:**
- Consumes: `TelemetrySink`, `stamp_invocation`, `new_correlation_id` (Task 2); enriched `LLMInvocation` (Task 1).
- Produces (used by Task 6):
  - `AgentTurnService(..., telemetry: TelemetrySink | None = None)`; `take_turn(game_id, actor_id, *, correlation_id: str | None = None) -> AgentTurnReport` — report invocations carry `game_id`/`agent_id`/`correlation_id`/`timestamp`; the sink receives them.
  - `GmDirector(..., telemetry: TelemetrySink | None = None)`; hooks gain `*, correlation_id: str | None = None`; GM invocations are stamped `agent_id="gm"`.
  - `MemoryService(..., telemetry: TelemetrySink | None = None)`; `retrieve(game_id, perception, *, correlation_id: str | None = None)`; `record_turn(..., *, note=None, correlation_id: str | None = None)`; embed invocations stamped `agent_id` = owning character, `retrieval_count` = memories returned (0 on record).
  - `AgentRuntime.decide_structured` stamps `attempt=n` (transport attempt) on returned and last-failed invocations when n > 1.

**Ruling on `attempt` (spec §3.1 defines `attempt > 1` = retry but §3.5 names no stamping site):** the runtime owns transport retries, so it stamps `attempt`; decision-level retries produce new runtime calls whose invocations start at `attempt=1` (the per-turn CLI display already covers decision attempts).

- [ ] **Step 1: Write the failing runtime attempt tests**

Append to `tests/ai/agents/test_runtime.py`:

```python
def test_retry_success_stamps_the_attempt_on_the_invocation() -> None:
    fake = FakeModelGateway()
    fake.enqueue_error(ModelTimeoutError("boom"))
    fake.enqueue_structured(dict(_DECISION))
    sleeps: list[float] = []
    runtime = AgentRuntime(fake, _policy(sleeps))

    response = runtime.decide_structured(
        profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA
    )

    assert response.invocation.attempt == 2
    assert fake.invocations[0].attempt == 1  # the failed first attempt keeps 1


def test_exhausted_budget_stamps_the_last_attempt() -> None:
    fake = FakeModelGateway()
    fake.enqueue_error(ModelTimeoutError("boom"))
    fake.enqueue_error(ModelTimeoutError("boom"))
    sleeps: list[float] = []
    runtime = AgentRuntime(fake, _policy(sleeps, max_attempts=2))

    with pytest.raises(AgentRuntimeError) as excinfo:
        runtime.decide_structured(profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA)

    assert excinfo.value.last_invocation is not None
    assert excinfo.value.last_invocation.attempt == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/ai/agents/test_runtime.py -q | tail -1`
Expected: FAIL — `assert 1 == 2` on the attempt fields (2 failures).

- [ ] **Step 3: Stamp the attempt in the runtime**

In `src/ai/agents/runtime.py`, add `import dataclasses` to the stdlib import block (after `import asyncio`), and add this module-level helper below the imports:

```python
def _with_attempt(
    invocation: LLMInvocation | None, attempt: int
) -> LLMInvocation | None:
    """Stamp the transport retry number on the record (attempt > 1 = retry)."""
    if invocation is None or attempt == 1:
        return invocation
    return dataclasses.replace(invocation, attempt=attempt)
```

Rewrite the `decide_structured` loop body so both the success and the failure paths carry the stamped invocation:

```python
        last_error: ModelError | None = None
        last_invocation: LLMInvocation | None = None
        for attempt in range(1, self._retry_policy.max_attempts + 1):
            try:
                response = asyncio.run(self._gateway.generate_structured(request, schema))
            except ModelError as error:
                last_error = error
                last_invocation = _with_attempt(error.invocation, attempt)
                if not is_retryable(error):
                    raise AgentRuntimeMisconfiguredError(
                        f"non-retryable model failure after {attempt} attempt(s): {error}",
                        attempts=attempt,
                        last_invocation=last_invocation,
                    ) from error
                if attempt < self._retry_policy.max_attempts:
                    self._retry_policy.sleep(self._retry_policy.backoff_seconds)
            else:
                if attempt > 1:
                    response = dataclasses.replace(
                        response,
                        invocation=dataclasses.replace(response.invocation, attempt=attempt),
                    )
                return response
        raise AgentRuntimeError(
            f"model decision failed after {self._retry_policy.max_attempts} "
            f"attempt(s): {last_error}",
            attempts=self._retry_policy.max_attempts,
            last_invocation=last_invocation,
        )
```

(The `return` moves into an `else:` clause so the final `raise` stays reachable for mypy.)

- [ ] **Step 4: Run the runtime tests to verify they pass**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/ai/agents/test_runtime.py -q | tail -1`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/ai/agents/runtime.py tests/ai/agents/test_runtime.py
git commit -m "feat(ai): stamp the transport attempt number on runtime invocations

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 6: Write the failing enrichment tests**

**6a.** In `tests/application/agents/test_agent_turn_service.py`:

- Extend the `ai.models.types` import (line 17) to include `LLMInvocation`:
  `from ai.models.types import LLMInvocation, ModelRequest, StructuredModelResponse`
- Add `from application.telemetry import TelemetrySink` to the `application.*` import block (after `application.agents.profiles`).
- Give `_agent_service` a `telemetry` parameter and pass it through:

```python
def _agent_service(
    game_service: GameService,
    gateway: FakeModelGateway,
    *,
    max_action_retries: int = 2,
    board: PartyMessageBoard | None = None,
    memory: MemoryService | None = None,
    telemetry: TelemetrySink | None = None,
) -> AgentTurnService:
    runtime = AgentRuntime(gateway, RetryPolicy(max_attempts=3))
    agent_profiles = AgentProfileCatalog(
        max_action_retries=max_action_retries,
        agents={"brix": _BRIX},
    )
    return AgentTurnService(
        game_service,
        runtime,
        _MODEL_CATALOG,
        agent_profiles,
        board=board,
        memory=memory,
        telemetry=telemetry,
    )
```

- Add a sink double near the top (after `_CapturingFake`):

```python
class _RecordingTelemetrySink:
    """Telemetry double that keeps every enriched record for assertions."""

    def __init__(self) -> None:
        self.records: list[LLMInvocation] = []

    def record(self, invocation: LLMInvocation) -> None:
        self.records.append(invocation)
```

- Append the three new tests:

```python
def test_turn_invocations_carry_the_enrichment_stamp() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    fake.enqueue_structured(
        {"action_type": "attack", "target_id": goblin_id.value, "public_message": "I strike."}
    )
    service = _agent_service(game_service, fake)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert len(report.invocations) == 1
    invocation = report.invocations[0]
    assert invocation.game_id == str(game_id)
    assert invocation.agent_id == brix_id.value
    assert invocation.correlation_id is not None
    assert invocation.timestamp is not None
    datetime.fromisoformat(invocation.timestamp)
    assert invocation.attempt == 1


def test_transport_retry_invocations_carry_attempt_numbers() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    for _ in range(6):  # 2 decision attempts x 3 transport attempts
        fake.enqueue_error(ModelTimeoutError("boom"))
    service = _agent_service(game_service, fake, max_action_retries=1)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.proposal_source == "fallback"
    assert len(report.invocations) == 2
    assert all(invocation.attempt == 3 for invocation in report.invocations)


def test_one_correlation_id_spans_the_decision_and_memory_calls() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    fake.enqueue_structured(
        {"action_type": "attack", "target_id": goblin_id.value, "public_message": "I strike."}
    )
    telemetry = _RecordingTelemetrySink()
    memory, _repo = _memory_service(telemetry=telemetry)
    service = _agent_service(game_service, fake, memory=memory, telemetry=telemetry)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id, correlation_id="corr-42")

    embeds = [record for record in telemetry.records if record.operation == "embed"]
    decisions = [
        record for record in telemetry.records if record.operation == "generate_structured"
    ]
    assert len(decisions) == 1
    assert len(embeds) == 2  # retrieval embed + episodic/semantic record embed
    assert all(record.correlation_id == "corr-42" for record in telemetry.records)
    assert all(record.agent_id == brix_id.value for record in embeds)
    assert all(record.game_id == str(game_id) for record in telemetry.records)
```

- Extend the stdlib import block at the top with `from datetime import datetime` (place it after `import asyncio`), and give `_memory_service` a telemetry parameter:

```python
def _memory_service(
    gateway: EmbeddingGateway | None = None,
    telemetry: TelemetrySink | None = None,
) -> tuple[MemoryService, InMemoryMemoryRepository]:
    repo = InMemoryMemoryRepository()
    embedder = gateway if gateway is not None else DeterministicEmbeddingGateway()
    return (
        MemoryService(embedder, repo, model="test-model", telemetry=telemetry),
        repo,
    )
```

**6b.** Append to `tests/application/memory/test_memory_service.py`:

First add `from ai.models.types import LLMInvocation` to the file's import block (after the `ai.memory.types` import). Then append:

```python
class _RecordingTelemetrySink:
    """Telemetry double that keeps every enriched record for assertions."""

    def __init__(self) -> None:
        self.records: list[LLMInvocation] = []

    def record(self, invocation: LLMInvocation) -> None:
        self.records.append(invocation)


def test_retrieve_stamps_the_embed_invocation_with_the_retrieval_count() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(
        _seed_record(
            "game-1", "brix", "The Goblin hits hard — stay at range.", MemoryKind.SEMANTIC, 1
        )
    )
    telemetry = _RecordingTelemetrySink()
    service = MemoryService(
        DeterministicEmbeddingGateway(), repo, model="test-model", telemetry=telemetry
    )

    memories = service.retrieve("game-1", _perception(), correlation_id="corr-9")

    assert len(memories) == 1
    assert len(telemetry.records) == 1
    invocation = telemetry.records[0]
    assert invocation.operation == "embed"
    assert invocation.agent_id == "brix"
    assert invocation.game_id == "game-1"
    assert invocation.correlation_id == "corr-9"
    assert invocation.retrieval_count == 1
    assert invocation.timestamp is not None


def test_record_turn_stamps_its_embed_invocation() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _brix_first(game_service)
    telemetry = _RecordingTelemetrySink()
    service = MemoryService(
        DeterministicEmbeddingGateway(),
        InMemoryMemoryRepository(),
        model="test-model",
        telemetry=telemetry,
    )
    perception = build_perception(game_service.get_view(game_id), brix_id.value)
    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=goblin_id,
        )
    )

    service.record_turn(
        str(game_id),
        perception,
        turn_report,
        note="Watch the Goblin.",
        correlation_id="corr-10",
    )

    assert len(telemetry.records) == 1
    invocation = telemetry.records[0]
    assert invocation.operation == "embed"
    assert invocation.agent_id == brix_id.value
    assert invocation.game_id == str(game_id)
    assert invocation.correlation_id == "corr-10"
    assert invocation.retrieval_count == 0
    assert invocation.timestamp is not None
```

**6c.** In `tests/application/gm/test_gm_director.py`, extend the `ai.models.types` import to `from ai.models.types import LLMInvocation, ModelRequest, StructuredModelResponse`, add `from application.telemetry import TelemetrySink` to the `application.*` import block (after `application.gm.profiles`), and append:

```python
class _RecordingTelemetrySink:
    def __init__(self) -> None:
        self.records: list[LLMInvocation] = []

    def record(self, invocation: LLMInvocation) -> None:
        self.records.append(invocation)
```

Give `_director` a telemetry parameter and pass it through:

```python
def _director(
    game_service: GameService,
    fake: FakeModelGateway,
    telemetry: TelemetrySink | None = None,
) -> tuple[GmDirector, GmConversation]:
    conversation = GmConversation()
    runtime = AgentRuntime(fake, RetryPolicy(max_attempts=3))
    director = GmDirector(
        game_service, runtime, _MODEL_CATALOG, _PROFILE, conversation, telemetry=telemetry
    )
    return director, conversation
```

Append the two GM tests:

```python
def test_gm_invocations_are_stamped_with_the_gm_agent_id() -> None:
    service, game_id = _scene()
    fake = _CapturingFake()
    fake.enqueue_structured({"narration": "Two foes block the pass."})
    telemetry = _RecordingTelemetrySink()
    director, _conversation = _director(service, fake, telemetry)

    result = director.on_combat_open(game_id, correlation_id="corr-7")

    assert result.narration is not None
    assert len(telemetry.records) == 1
    invocation = telemetry.records[0]
    assert invocation.agent_id == "gm"
    assert invocation.game_id == str(game_id)
    assert invocation.correlation_id == "corr-7"
    assert invocation.timestamp is not None
    assert result.invocations[0].agent_id == "gm"


def test_failed_gm_calls_are_stamped_too() -> None:
    service, game_id = _scene()
    fake = FakeModelGateway()
    fake.enqueue_error(ModelRequestError("gateway down"))
    telemetry = _RecordingTelemetrySink()
    director, _conversation = _director(service, fake, telemetry)

    result = director.on_combat_open(game_id)

    assert result.narration is None
    assert len(telemetry.records) == 1
    assert telemetry.records[0].agent_id == "gm"
    assert telemetry.records[0].status == "error"
    assert result.invocations[0].agent_id == "gm"
```

(`ModelRequestError` is already imported in that test file.)

- [ ] **Step 7: Run the enrichment tests to verify they fail**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/application/agents/test_agent_turn_service.py tests/application/memory/test_memory_service.py tests/application/gm/test_gm_director.py -q | tail -1`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'telemetry'` on the service constructors (7 new failures; the runtime attempt tests from Steps 1–4 already pass).

- [ ] **Step 8: Wire enrichment into the three services**

**8a. `src/application/agents/agent_turn_service.py`:**

- Add to the import block: `from application.telemetry import TelemetrySink, new_correlation_id, stamp_invocation` (after `application.memory.memory_service`).
- Constructor: add `telemetry: TelemetrySink | None = None` after `memory: MemoryService | None = None`, and `self._telemetry = telemetry` at the end of the body.
- Replace the `take_turn` signature and its opening lines:

```python
    def take_turn(
        self,
        game_id: GameId,
        actor_id: CharacterId,
        *,
        correlation_id: str | None = None,
    ) -> AgentTurnReport:
        profile = self._agents.get(actor_id.value)
        if profile is None:
            raise AgentNotRegisteredError(actor_id.value)
        correlation_id = correlation_id or new_correlation_id()
```

- Change the memory call sites inside `take_turn`:

```python
        memories = self._retrieve_memories(game_id, perception, invocations, correlation_id)
```

and in the accepted branch:

```python
                self._record_memories(
                    game_id, perception, turn_report, decision.memory_note, invocations,
                    correlation_id,
                )
```

- The accepted-path return becomes:

```python
                return AgentTurnReport(
                    actor_id=actor_id.value,
                    actor_name=perception.self_view.name,
                    accepted=True,
                    proposal_source="model",
                    action_attempts=attempt,
                    rejection_reasons=tuple(rejection_reasons),
                    fallback_reason=None,
                    public_message=decision.public_message,
                    invocations=self._flush(game_id, actor_id.value, correlation_id, invocations),
                    turn_report=turn_report,
                    party_message=decision.party_message,
                    memory_retrieved=len(memories),
                )
```

- The final fallback call becomes:

```python
        return self._fallback(
            game_id,
            actor_id,
            perception,
            memories,
            invocations,
            tuple(rejection_reasons),
            correlation_id,
        )
```

- `_fallback` gains `correlation_id: str` as its last parameter; its return statement uses `invocations=self._flush(game_id, actor_id.value, correlation_id, invocations)`; and its internal `self._record_memories(game_id, perception, turn_report, None, invocations)` call gains `correlation_id`.
- `_retrieve_memories` and `_record_memories` gain the parameter and pass it into MemoryService:

```python
    def _retrieve_memories(
        self,
        game_id: GameId,
        perception: AgentPerception,
        invocations: list[LLMInvocation],
        correlation_id: str,
    ) -> tuple[MemoryRecord, ...]:
        """Memory never gates a turn (spec §2.8): failures degrade to no memories."""
        if self._memory is None:
            return ()
        try:
            return self._memory.retrieve(
                str(game_id), perception, correlation_id=correlation_id
            )
        except ModelError as error:
            if error.invocation is not None:
                invocations.append(error.invocation)
            return ()
        except PersistenceError:
            return ()

    def _record_memories(
        self,
        game_id: GameId,
        perception: AgentPerception,
        turn_report: TurnReport,
        note: str | None,
        invocations: list[LLMInvocation],
        correlation_id: str,
    ) -> None:
        """Recording never revisits an accepted action (spec §2.8): failures drop the write."""
        if self._memory is None:
            return
        try:
            self._memory.record_turn(
                str(game_id), perception, turn_report, note=note, correlation_id=correlation_id
            )
        except ModelError as error:
            if error.invocation is not None:
                invocations.append(error.invocation)
        except PersistenceError:
            return
```

- Add the flush helper at the end of the class:

```python
    def _flush(
        self,
        game_id: GameId,
        agent_id: str,
        correlation_id: str,
        invocations: list[LLMInvocation],
    ) -> tuple[LLMInvocation, ...]:
        """Stamp every invocation with the turn context and hand it to the sink."""
        enriched = tuple(
            stamp_invocation(
                invocation,
                game_id=str(game_id),
                agent_id=agent_id,
                correlation_id=correlation_id,
            )
            for invocation in invocations
        )
        if self._telemetry is not None:
            for invocation in enriched:
                self._telemetry.record(invocation)
        return enriched
```

**8b. `src/application/memory/memory_service.py`:**

- Add imports: `import dataclasses` (stdlib block), `from ai.models.types import LLMInvocation`, `from application.telemetry import TelemetrySink, stamp_invocation` (new `application` import block after `application.agents.perception`).
- Constructor gains `telemetry: TelemetrySink | None = None` (keyword, last) and `self._telemetry = telemetry`.
- `retrieve` gains `*, correlation_id: str | None = None` and flushes after the search:

```python
    def retrieve(
        self,
        game_id: str,
        perception: AgentPerception,
        *,
        correlation_id: str | None = None,
    ) -> tuple[MemoryRecord, ...]:
        """Embed the situation line and return the agent's most relevant memories."""
        me = perception.self_view
        opponent_names = (
            ", ".join(opponent.name for opponent in perception.opponents) or "none"
        )
        query = (
            f"{me.name} the {me.character_class}; "
            f"round {perception.round_number}; opponents: {opponent_names}"
        )
        response = asyncio.run(
            self._gateway.embed(EmbeddingRequest(texts=(query,), model=self._model))
        )
        memories = self._repository.search(
            game_id, me.id, response.vectors[0], limit=self._retrieval_limit
        )
        self._flush(
            response.invocation,
            game_id=game_id,
            agent_id=me.id,
            correlation_id=correlation_id,
            retrieval_count=len(memories),
        )
        return memories
```

- `record_turn` gains `*, correlation_id: str | None = None` (after `note`), and flushes right after its embed call:

```python
        response = asyncio.run(
            self._gateway.embed(
                EmbeddingRequest(
                    texts=tuple(text for _, text in entries), model=self._model
                )
            )
        )
        self._flush(
            response.invocation,
            game_id=game_id,
            agent_id=perception.self_view.id,
            correlation_id=correlation_id,
            retrieval_count=0,
        )
```

- Add the flush helper:

```python
    def _flush(
        self,
        invocation: LLMInvocation,
        *,
        game_id: str,
        agent_id: str,
        correlation_id: str | None,
        retrieval_count: int,
    ) -> None:
        """Stamp the embed invocation with its context and hand it to the sink."""
        if self._telemetry is None:
            return
        stamped = stamp_invocation(
            invocation,
            game_id=game_id,
            agent_id=agent_id,
            correlation_id=correlation_id,
        )
        self._telemetry.record(
            dataclasses.replace(stamped, retrieval_count=retrieval_count)
        )
```

**8c. `src/application/gm/director.py`:**

- Add import: `from application.telemetry import TelemetrySink, stamp_invocation` (after `application.gm.profiles`).
- Constructor gains `telemetry: TelemetrySink | None = None` (keyword, last) and `self._telemetry = telemetry`.
- All three hooks gain `*, correlation_id: str | None = None` and pass it down:

```python
    def on_combat_open(
        self, game_id: GameId, *, correlation_id: str | None = None
    ) -> GmResult:
        view = self._game_service.get_view(game_id)
        system, user = build_gm_context(
            self._profile,
            view,
            [],
            self._conversation.recent(self._profile.history_limit),
            "narrate_open",
        )
        return self._decide(
            system, user, view, game_id=game_id, correlation_id=correlation_id
        )
```

```python
    def on_turn_report(
        self, game_id: GameId, report: TurnReport, *, correlation_id: str | None = None
    ) -> GmResult | None:
        """React to notable events only; None (zero LLM calls) otherwise (spec D3/D4).

        `game_id` is accepted for interface symmetry with the other hooks and
        for future API/Web adapters; the report carries its own scene view.
        """
        if not notable_events(report):
            return None
        name_by_id = {
            member.id: member.name
            for member in (*report.view.party, *report.view.enemies)
        }
        digest = digest_lines(report.events, name_by_id)
        system, user = build_gm_context(
            self._profile,
            report.view,
            digest,
            self._conversation.recent(self._profile.history_limit),
            "react_to_events",
        )
        return self._decide(
            system, user, report.view, game_id=game_id, correlation_id=correlation_id
        )
```

```python
    def on_player_say(
        self, game_id: GameId, text: str, *, correlation_id: str | None = None
    ) -> GmResult:
        view = self._game_service.get_view(game_id)
        self._conversation.append(
            GmMessage(speaker="player", text=" ".join(text.split()))
        )
        system, user = build_gm_context(
            self._profile,
            view,
            [],
            self._conversation.recent(self._profile.history_limit),
            "respond_to_player",
        )
        result = self._decide(
            system, user, view, game_id=game_id, correlation_id=correlation_id
        )
        if result.npc_reply is not None:
            self._conversation.append(
                GmMessage(speaker=result.addressed_to or "gm", text=result.npc_reply)
            )
        elif result.narration is not None:
            self._conversation.append(
                GmMessage(speaker="gm", text=result.narration)
            )
        return result
```

- `_decide` gains the keyword parameters and flushes on every path; add `_flush`:

```python
    def _decide(
        self,
        system: str,
        user: str,
        view: GameView,
        *,
        game_id: GameId,
        correlation_id: str | None,
    ) -> GmResult:
        """One structured GM decision; every failure becomes an empty GmResult."""
        try:
            response = self._runtime.decide_structured(
                profile=self._model_profile,
                system=system,
                user=user,
                schema=GM_RESPONSE_SCHEMA,
            )
        except AgentRuntimeError as error:
            invocation = (
                (error.last_invocation,) if error.last_invocation is not None else ()
            )
            return GmResult(
                invocations=self._flush(game_id, correlation_id, invocation)
            )
        try:
            narration, reply, addressed = map_gm_response(
                response.data, self._profile, view
            )
        except InvalidGmResponseError:
            return GmResult(
                invocations=self._flush(
                    game_id, correlation_id, (response.invocation,)
                )
            )
        return GmResult(
            narration=narration,
            npc_reply=reply,
            addressed_to=addressed,
            invocations=self._flush(game_id, correlation_id, (response.invocation,)),
        )

    def _flush(
        self,
        game_id: GameId,
        correlation_id: str | None,
        invocations: tuple[LLMInvocation, ...],
    ) -> tuple[LLMInvocation, ...]:
        """Stamp GM invocations (agent_id "gm") and hand them to the sink."""
        enriched = tuple(
            stamp_invocation(
                invocation,
                game_id=str(game_id),
                agent_id="gm",
                correlation_id=correlation_id,
            )
            for invocation in invocations
        )
        if self._telemetry is not None:
            for invocation in enriched:
                self._telemetry.record(invocation)
        return enriched
```

(The constructor stores `self._telemetry = telemetry` after `self._conversation = conversation`.)

- [ ] **Step 9: Run the enrichment tests to verify they pass**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/application/agents/test_agent_turn_service.py tests/application/memory/test_memory_service.py tests/application/gm/test_gm_director.py tests/ai/agents/test_runtime.py -q | tail -1`
Expected: all pass.

- [ ] **Step 10: Run the gate**

```bash
set -o pipefail
V=$PWD/.venv/bin/python
$V -m ruff check . && $V -m mypy | tail -1 && OPENROUTER_API_KEY= $V -m pytest -q | tail -1
```

Expected: ruff clean, mypy clean, **420 passed, 2 skipped**.

- [ ] **Step 11: Commit**

```bash
git add src/application/agents/agent_turn_service.py src/application/gm/director.py src/application/memory/memory_service.py tests/application/agents/test_agent_turn_service.py tests/application/memory/test_memory_service.py tests/application/gm/test_gm_director.py
git commit -m "feat(application): enrich agent, GM, and memory invocations with turn context

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: CLI surfacing — `--debug`, `/telemetry`, session summary

**Files:**
- Modify: `src/interfaces/cli/app.py`
- Modify: `README.md`
- Test: `tests/interfaces/test_cli.py`

**Interfaces:**
- Consumes: `CompositeTelemetrySink`, `TelemetrySink`, `new_correlation_id` (Task 2); `InMemoryTelemetrySink` + `snapshot()` (Task 2); `LoggingTelemetrySink` + `configure_telemetry_logging` (Task 3); `PostgresTelemetrySink` (Task 4); the Task-5 service signatures (`telemetry=` kwarg, `correlation_id=` kwargs).
- Produces: `--debug` flag; `/telemetry` command; end-of-session summary table before the goodbye (and on `/quit`); `_wire_party(..., telemetry)`, `_wire_gm(..., telemetry)` signatures.

- [ ] **Step 1: Write the failing CLI tests**

Append to `tests/interfaces/test_cli.py` (add `import json` to the stdlib import block at the top, after `from io import StringIO`):

```python
def test_main_telemetry_command_prints_session_totals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(
        argv=["--gm", "fake"],
        console=console,
        input_fn=_scripted("/telemetry", "/quit"),
    )
    assert code == 0
    output = buffer.getvalue()
    # once for /telemetry, once for the /quit session summary
    assert output.count("LLM telemetry") == 2
    assert "calls" in output and "retries" in output


def test_main_end_of_session_summary_precedes_thanks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    lines = (
        ["attack goblin scout"] * 30
        + ["attack goblin skulker"] * 30
        + ["attack orc brute"] * 60
    )
    code = main(argv=["--gm", "fake"], console=console, input_fn=_scripted(*lines))
    assert code == 0
    output = buffer.getvalue()
    assert output.index("LLM telemetry") < output.index("Thanks for playing!")


def test_main_debug_emits_parseable_telemetry_lines(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    log_file = tmp_path / "telemetry.jsonl"
    monkeypatch.setenv("CONCLAVE_TELEMETRY_LOG", str(log_file))
    console, buffer = _console()

    code = main(
        argv=["--gm", "fake", "--debug"],
        console=console,
        input_fn=_scripted("/quit"),
    )

    assert code == 0
    lines = [line for line in log_file.read_text(encoding="utf-8").splitlines() if line]
    assert lines  # the GM's opening call is already on the wire
    expected_keys = {
        "ts", "event", "game_id", "agent_id", "correlation_id", "request_id",
        "provider", "model", "operation", "status", "error_kind", "latency_ms",
        "input_tokens", "output_tokens", "total_tokens", "estimated_cost_usd",
        "attempt", "retrieval_count", "tools_called",
    }
    for line in lines:
        payload = json.loads(line)
        assert set(payload) == expected_keys
        assert payload["event"] == "llm_invocation"
        assert payload["agent_id"] == "gm"


def test_main_without_debug_stays_silent(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    log_file = tmp_path / "telemetry.jsonl"
    monkeypatch.setenv("CONCLAVE_TELEMETRY_LOG", str(log_file))
    console, buffer = _console()

    code = main(argv=["--gm", "fake"], console=console, input_fn=_scripted("/quit"))

    assert code == 0
    assert log_file.read_text(encoding="utf-8") == ""
```

- [ ] **Step 2: Run them to verify they fail**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/interfaces/test_cli.py -q | tail -1`
Expected: FAIL — `--debug: unrecognized argument` (argparse error exits 2) for the debug tests; `output.count("LLM telemetry") == 0` for the others (4 failures).

- [ ] **Step 3: Wire the CLI**

**3a.** In `src/interfaces/cli/app.py`:

- Add `from rich.table import Table` after `from rich.console import Console`.
- Add to the `application.*` import block: `from application.telemetry import CompositeTelemetrySink, TelemetrySink, new_correlation_id` (after `application.memory.memory_service`).
- Add to the `infrastructure.*` import block (alphabetical: `infrastructure.events...` < `infrastructure.llm...` < `infrastructure.memory...` < `infrastructure.persistence...` < `infrastructure.telemetry...`):

```python
from infrastructure.telemetry.in_memory import InMemoryTelemetrySink
from infrastructure.telemetry.logging_sink import (
    LoggingTelemetrySink,
    configure_telemetry_logging,
)
from infrastructure.telemetry.postgres import PostgresTelemetrySink
```

- Add the `--debug` argument to the parser (after the `--gm` argument):

```python
    parser.add_argument(
        "--debug",
        action="store_true",
        help="emit per-call LLM telemetry lines (JSON) to stderr or $CONCLAVE_TELEMETRY_LOG",
    )
```

- Replace `_gm_react`:

```python
def _gm_react(
    console: Console,
    gm_service: GmDirector | None,
    report: TurnReport,
    *,
    correlation_id: str | None = None,
) -> None:
    """React to a finished turn report; prints nothing when nothing is notable."""
    if gm_service is None:
        return
    result = gm_service.on_turn_report(
        GameId(report.game_id), report, correlation_id=correlation_id
    )
    if result is not None:
        render_gm_result(console, result, report.view)
```

- Replace `_wire_gm` (new last parameter, passed to the director):

```python
def _wire_gm(service: GameService, mode: str, telemetry: TelemetrySink) -> GmDirector:
    """Wire the GM director off the shipped gm.toml persona (spec D9)."""
    profile = load_gm_profile(_CONFIG_DIR / "gm.toml")
    model_catalog = load_model_profiles(_CONFIG_DIR / "llm.toml")
    if mode == "llm":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set; export it to run with --gm llm")
        gateway = create_gateway(model_catalog.default_provider, api_key=api_key)
    else:
        gateway = ScriptedGmGateway(FakeModelGateway(), _gm_decision)
    runtime = AgentRuntime(gateway, RetryPolicy())
    return GmDirector(
        service, runtime, model_catalog, profile, GmConversation(), telemetry=telemetry
    )
```

- Replace `_wire_party` signature and the two wiring lines inside it (everything else unchanged):

```python
def _wire_party(
    service: GameService,
    game_id: GameId,
    mode: str,
    console: Console,
    db: str,
    telemetry: TelemetrySink,
) -> AgentTurnService:
```

```python
    memory = MemoryService(
        embedder, _memory_repository(db), model=embedding_profile.model, telemetry=telemetry
    )
    runtime = AgentRuntime(gateway, RetryPolicy())
    agent_service = AgentTurnService(
        service, runtime, model_catalog, agent_profiles, memory=memory, telemetry=telemetry
    )
```

- Add two helpers above `main`:

```python
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
```

- In `main`, after the service-resolution block and before `game_id = service.create_game(...)`, insert:

```python
    configure_telemetry_logging(debug=args.debug)
    session_sink = InMemoryTelemetrySink()
    sinks: list[TelemetrySink] = [LoggingTelemetrySink(), session_sink]
    if args.db == "postgres":
        # build_service hard-fails on a missing DATABASE_URL unless `service`
        # was injected directly (tests); degrade to logging-only in that case.
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            sinks.append(PostgresTelemetrySink(connect(database_url)))
    telemetry: TelemetrySink = CompositeTelemetrySink(sinks)
```

- Update the two wiring call sites:

```python
            agent_service = _wire_party(
                service, game_id, args.agent, console, args.db, telemetry
            )
```

```python
            gm_service = _wire_gm(service, args.gm, telemetry)
```

- The combat-open call becomes:

```python
    if gm_service is not None:
        render_gm_result(
            console,
            gm_service.on_combat_open(game_id, correlation_id=new_correlation_id()),
            service.get_view(game_id),
        )
```

- The loop's ended branch becomes:

```python
        if view.status == "ended":
            _render_telemetry(console, session_sink)
            console.print("The adventure has ended. Thanks for playing!")
            return 0
```

- The enemy-turn branch's `_gm_react` call becomes:

```python
            _gm_react(console, gm_service, report, correlation_id=new_correlation_id())
```

- The agent-turn block becomes (one correlation id shared by the decision and the GM reaction):

```python
            try:
                correlation_id = new_correlation_id()
                agent_report = agent_service.take_turn(
                    GameId(view.game_id),
                    CharacterId(view.combat.active_actor_id),
                    correlation_id=correlation_id,
                )
            except DomainError as error:
                console.print(f"[red]{error}[/red]")
                continue
            _render_agent_turn(console, agent_report, view)
            _gm_react(
                console,
                gm_service,
                agent_report.turn_report,
                correlation_id=correlation_id,
            )
            continue
```

- The command branch becomes:

```python
        if kind == "command":
            if argument == "/quit":
                _render_telemetry(console, session_sink)
                return 0
            if argument == "/status":
                continue
            if argument == "/telemetry":
                _render_telemetry(console, session_sink)
                continue
            if argument == "/help":
                console.print(
                    "Commands: attack <target>, say <text>, /status, /telemetry, /help, /quit"
                )
            else:
                console.print(f"Unknown command: {argument}")
            continue
```

- The `say` branch becomes:

```python
        if kind == "say":
            if gm_service is None:
                console.print("The GM is off — run with --gm fake or --gm llm to talk.")
                continue
            render_gm_result(
                console,
                gm_service.on_player_say(
                    GameId(view.game_id),
                    argument,
                    correlation_id=new_correlation_id(),
                ),
                view,
            )
            continue
```

- The `attack` branch's `_gm_react` call becomes:

```python
            _gm_react(console, gm_service, report, correlation_id=new_correlation_id())
```

- [ ] **Step 4: Run the CLI tests to verify they pass**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/interfaces/test_cli.py -q | tail -1`
Expected: all pass (15 existing + 4 new).

- [ ] **Step 5: Run the gate**

```bash
set -o pipefail
V=$PWD/.venv/bin/python
$V -m ruff check . && $V -m mypy | tail -1 && OPENROUTER_API_KEY= $V -m pytest -q | tail -1
```

Expected: ruff clean, mypy clean, **424 passed, 2 skipped**.

- [ ] **Step 6: Update the README**

Append to `README.md` (after the GM section):

```markdown
## Observability (telemetry)

Every LLM call becomes a structured `LLMInvocation` record — never prompts,
payloads, or reasoning (CLAUDE.md §34). Three sinks: a JSON log line per call,
an in-session totals table, and, with `--db postgres`, one row per call in
`llm_invocations` (migration `003_llm_invocations.sql`; TEXT id columns so
fake-gateway ids persist too).

- `--debug` — per-call JSON lines on stderr, or to the file named by
  `$CONCLAVE_TELEMETRY_LOG`.
- `/telemetry` — per-agent/role session totals: calls, retries, tokens in/out,
  estimated cost. The same table prints once when the session ends.
- Telemetry never gates the game: a failing sink is dropped after one warning
  and the session continues (Postgres failures degrade to logging-only).
```

- [ ] **Step 7: Commit**

```bash
git add src/interfaces/cli/app.py tests/interfaces/test_cli.py README.md
git commit -m "feat(interfaces): surface telemetry with --debug and /telemetry

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: Carry-forwards + final verification

**Files:**
- Modify: `pyproject.toml`, `tests/integration/test_openrouter_live.py`, `src/ai/models/profiles.py`, `tests/ai/models/test_profiles.py`, `README.md`
- Create: nothing

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: the `live` pytest marker (default runs deselect live tests; `pytest -m live` runs them); `load_model_profiles` raises `ProfileConfigError` when `default_provider` is missing.

- [ ] **Step 1: Write the failing default_provider test**

Append to `tests/ai/models/test_profiles.py`:

```python
def test_missing_default_provider_raises(tmp_path: Path) -> None:
    config = _write(tmp_path, '[profiles.gm]\nprovider = "openrouter"\nmodel = "m"\n')
    with pytest.raises(ProfileConfigError, match="default_provider"):
        load_model_profiles(config)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/ai/models/test_profiles.py -q | tail -1`
Expected: FAIL — the loader currently falls back to `"openrouter"` instead of raising.

- [ ] **Step 3: Require an explicit default_provider**

In `src/ai/models/profiles.py`, insert after the TOML-parse block (after line 56, before the profiles loop):

```python
    default_provider = raw.get("default_provider")
    if not isinstance(default_provider, str) or not default_provider:
        raise ProfileConfigError(
            "model profile config missing required key: default_provider"
        )
```

and change the return statement (line 83-87) to:

```python
    return ModelProfileCatalog(
        default_provider=default_provider,
        profiles=profiles,
        pricing=pricing,
    )
```

(The shipped `config/llm.toml` already sets `default_provider = "openrouter"`; no config change is needed.)

- [ ] **Step 4: Register the `live` marker**

In `pyproject.toml`, replace the pytest section:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = ["-m", "not live"]
markers = [
    "live: tests that call the real OpenRouter API (require OPENROUTER_API_KEY)",
]
```

(`addopts` is an ini option and can only live in pyproject — the spec's "add to tests/conftest.py" wording is impossible; the intent — default runs exclude live tests — is preserved.)

In `tests/integration/test_openrouter_live.py`, replace the module-level `pytestmark` with:

```python
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set; live provider test skipped (CLAUDE.md §46)",
    ),
]
```

(The `skipif` stays as the safety net for an explicit `pytest -m live` run without a key.)

- [ ] **Step 5: Run the full offline gate**

```bash
set -o pipefail
V=$PWD/.venv/bin/python
$V -m pytest tests/ai/models/test_profiles.py -q | tail -1
$V -m ruff check . && $V -m mypy | tail -1
OPENROUTER_API_KEY= $V -m pytest -q | tail -1
```

Expected: profiles test passes; ruff + mypy clean; full suite **425 passed, 2 deselected** (the live tests are now deselected by the marker instead of skipped by the env check).

- [ ] **Step 6: Run the live suite (only when OPENROUTER_API_KEY is set)**

Run: `set -o pipefail; .venv/bin/python -m pytest tests/integration/test_openrouter_live.py -m live -q | tail -1`
Expected (with a key): 2 passed. Without a key: 2 skipped — note it and continue.

- [ ] **Step 7: Verify the domain diff is empty and smoke-run the CLI**

```bash
git log master..HEAD --oneline -- src/domain
```
Expected: empty output (domain untouched).

Worktree-safe smoke run (scripted input file; `--debug` writes telemetry to a file):

```bash
printf 'attack orc brute\n/telemetry\n/quit\n' > /tmp/obs_smoke_input.txt
CONCLAVE_TELEMETRY_LOG=/tmp/obs_telemetry.jsonl .venv/bin/python -c "import sys; sys.path.insert(0, 'src'); from interfaces.cli.app import main; sys.exit(main(sys.argv[1:]))" --agent fake --debug < /tmp/obs_smoke_input.txt > /tmp/obs_smoke.txt 2>&1
grep -c '"event": "llm_invocation"' /tmp/obs_telemetry.jsonl
grep -q "LLM telemetry" /tmp/obs_smoke.txt && echo "summary OK"
```

Expected: exit 0; the grep count is > 0; "summary OK" prints.

- [ ] **Step 8: Update the roadmap**

In `docs/superpowers/plans/README.md`, change row 8 from `| 8 | *observability* | ... | Not written |` to:

```markdown
| 8 | `2026-09-09-observability.md` | Phase 17 — `LLMInvocation` telemetry, structured logging, correlation IDs | Complete |
```

- [ ] **Step 9: Commit**

```bash
git add src/ai/models/profiles.py tests/ai/models/test_profiles.py pyproject.toml tests/integration/test_openrouter_live.py docs/superpowers/plans/README.md
git commit -m "feat(ai): require an explicit default_provider; mark live tests

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 10: Final whole-plan verification**

```bash
set -o pipefail
V=$PWD/.venv/bin/python
OPENROUTER_API_KEY= $V -m pytest -q | tail -1
$V -m ruff check .
$V -m mypy | tail -1
git log master..HEAD --oneline -- src/domain | wc -l
```

Expected: **425 passed, 2 deselected**; ruff and mypy clean; domain-diff count 0. Then use superpowers:finishing-a-development-branch.

---

## Completion checklist (mirrors spec §10)

- [ ] All tasks executed; full offline suite green (425 passed, 2 deselected).
- [ ] `src/domain` diff empty against master.
- [ ] mypy strict + ruff clean.
- [ ] Telemetry never gates the game — proven by `test_composite_drops_a_broken_sink_after_one_report` and `test_a_failed_insert_never_raises_and_warns_once`.
- [ ] No prompts, payloads, reasoning, or credentials in any telemetry payload (the logging payload is the exact 20-key allowlist asserted in Task 3).
- [ ] Configuration externalized: `CONCLAVE_TELEMETRY_LOG`, `--debug`, `--db postgres`.
- [ ] README documents the observability surface; roadmap row #8 marked Complete.
