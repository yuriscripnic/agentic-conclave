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
