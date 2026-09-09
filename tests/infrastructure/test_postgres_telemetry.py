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
