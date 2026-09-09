# tests/application/telemetry/test_telemetry_port.py
"""TelemetrySink port and composite tests (Phase 17, spec §3.3, §4)."""

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
