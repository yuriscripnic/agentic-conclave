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
    event_summaries: tuple[EventSummary, ...] = (),
    invocations: tuple[InvocationSummary, ...] = (),
    *,
    turn_reports: tuple[str, ...] = (),
    party_messages: tuple[str, ...] = (),
) -> RunRecord:
    return RunRecord(
        run_index=index,
        seed=42,
        event_summaries=event_summaries,
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