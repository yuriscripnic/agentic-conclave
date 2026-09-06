"""Agent-layer error taxonomy (the AI layer does not reuse domain errors)."""

from __future__ import annotations

from ai.models.types import LLMInvocation


class AgentRuntimeError(Exception):
    """A bounded decision attempt exhausted its retry budget."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_invocation: LLMInvocation | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_invocation = last_invocation


class AgentRuntimeMisconfiguredError(AgentRuntimeError):
    """Non-retryable model/config failure; retrying an identical request cannot help."""
