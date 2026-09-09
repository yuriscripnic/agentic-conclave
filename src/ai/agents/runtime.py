"""Synchronous decision runtime bridging the async model gateway."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Mapping
from typing import Any

from ai.agents.errors import AgentRuntimeError, AgentRuntimeMisconfiguredError
from ai.agents.retry import RetryPolicy, is_retryable
from ai.models.errors import ModelError
from ai.models.gateway import ModelGateway
from ai.models.profiles import ModelProfile
from ai.models.types import LLMInvocation, Message, StructuredModelResponse


def _with_attempt(
    invocation: LLMInvocation | None, attempt: int
) -> LLMInvocation | None:
    """Stamp the transport retry number on the record (attempt > 1 = retry)."""
    if invocation is None or attempt == 1:
        return invocation
    return dataclasses.replace(invocation, attempt=attempt)


class AgentRuntime:
    """One bounded decision request per call; transport retries live here."""

    def __init__(self, gateway: ModelGateway, retry_policy: RetryPolicy | None = None) -> None:
        self._gateway = gateway
        self._retry_policy = retry_policy if retry_policy is not None else RetryPolicy()

    def decide_structured(
        self,
        *,
        profile: ModelProfile,
        system: str,
        user: str,
        schema: Mapping[str, Any],
    ) -> StructuredModelResponse:
        """Build one request from the profile and run it under the retry budget."""
        request = profile.to_request(
            [
                Message(role="system", content=system),
                Message(role="user", content=user),
            ]
        )
        last_error: ModelError | None = None
        last_invocation: LLMInvocation | None = None
        for attempt in range(1, self._retry_policy.max_attempts + 1):
            try:
                response = asyncio.run(self._gateway.generate_structured(request, schema))
            except ModelError as error:
                last_error = error
                last_invocation = _with_attempt(error.invocation, attempt)
                if not is_retryable(error):
                    raise AgentRuntimeMisconfiguredError(
                        f"non-retryable model failure after {attempt} attempt(s): {error}",
                        attempts=attempt,
                        last_invocation=last_invocation,
                    ) from error
                if attempt < self._retry_policy.max_attempts:
                    self._retry_policy.sleep(self._retry_policy.backoff_seconds)
            else:
                if attempt > 1:
                    response = dataclasses.replace(
                        response,
                        invocation=dataclasses.replace(response.invocation, attempt=attempt),
                    )
                return response
        raise AgentRuntimeError(
            f"model decision failed after {self._retry_policy.max_attempts} "
            f"attempt(s): {last_error}",
            attempts=self._retry_policy.max_attempts,
            last_invocation=last_invocation,
        )
