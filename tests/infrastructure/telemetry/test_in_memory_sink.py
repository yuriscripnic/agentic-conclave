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
    assert row.total_tokens == 45
    assert row.estimated_cost_usd == pytest.approx(0.002)
