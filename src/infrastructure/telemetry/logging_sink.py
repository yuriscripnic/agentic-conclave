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
        self._logger = (
            logger if logger is not None else logging.getLogger(TELEMETRY_LOGGER)
        )

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
