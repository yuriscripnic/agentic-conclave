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
