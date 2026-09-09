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
