"""Core metric arithmetic over ScenarioResults (spec §4.5).

None means "not computable" — never a fake 0 or 1.
"""

from __future__ import annotations

import math

from evaluation.model import RunRecord, ScenarioResult

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