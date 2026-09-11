"""Evaluation data model (spec §4.2/§4.3): scenarios, run records, results."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScenarioCheck:
    """One deterministic predicate over a finished result (spec §4.2)."""

    name: str
    description: str
    evaluate: Callable[[ScenarioResult], bool]


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