"""AgentRuntime decision-loop tests."""

from collections.abc import Mapping
from typing import Any

import pytest

from ai.agents.errors import AgentRuntimeError, AgentRuntimeMisconfiguredError
from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.models.errors import ModelRequestError, ModelTimeoutError
from ai.models.fake import FakeModelGateway
from ai.models.profiles import ModelProfile
from ai.models.types import Message, ModelRequest, ModelResponse, StructuredModelResponse

_PROFILE = ModelProfile(
    name="player",
    provider="fake",
    model="test-model",
    temperature=0.1,
    max_tokens=64,
)
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}
_DECISION: dict[str, Any] = {"answer": "ok"}
_SYSTEM = "system prompt"
_USER = "user prompt"


def _policy(sleeps: list[float], max_attempts: int = 3) -> RetryPolicy:
    def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return RetryPolicy(max_attempts=max_attempts, backoff_seconds=0.25, sleep=_sleep)


def test_success_on_first_attempt() -> None:
    fake = FakeModelGateway()
    fake.enqueue_structured(dict(_DECISION))
    runtime = AgentRuntime(fake)

    response = runtime.decide_structured(
        profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA
    )

    assert response.data == _DECISION
    assert len(fake.invocations) == 1


def test_retries_transient_error_then_succeeds() -> None:
    fake = FakeModelGateway()
    fake.enqueue_error(ModelTimeoutError("boom"))
    fake.enqueue_structured(dict(_DECISION))
    sleeps: list[float] = []
    runtime = AgentRuntime(fake, _policy(sleeps))

    response = runtime.decide_structured(
        profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA
    )

    assert response.data == _DECISION
    assert sleeps == [0.25]
    assert len(fake.invocations) == 2


def test_exhausted_budget_raises_agent_runtime_error() -> None:
    fake = FakeModelGateway()
    fake.enqueue_error(ModelTimeoutError("boom"))
    fake.enqueue_error(ModelTimeoutError("boom"))
    sleeps: list[float] = []
    runtime = AgentRuntime(fake, _policy(sleeps, max_attempts=2))

    with pytest.raises(AgentRuntimeError) as excinfo:
        runtime.decide_structured(profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA)

    assert excinfo.value.attempts == 2
    assert excinfo.value.last_invocation is not None
    assert sleeps == [0.25]


def test_sleep_is_not_called_after_the_final_attempt() -> None:
    fake = FakeModelGateway()
    fake.enqueue_error(ModelTimeoutError("boom"))
    sleeps: list[float] = []
    runtime = AgentRuntime(fake, _policy(sleeps, max_attempts=1))

    with pytest.raises(AgentRuntimeError):
        runtime.decide_structured(profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA)

    assert sleeps == []


def test_non_retryable_error_fails_fast_without_retry() -> None:
    fake = FakeModelGateway()
    fake.enqueue_error(ModelRequestError("bad request"))
    sleeps: list[float] = []
    runtime = AgentRuntime(fake, _policy(sleeps))

    with pytest.raises(AgentRuntimeMisconfiguredError) as excinfo:
        runtime.decide_structured(profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA)

    assert excinfo.value.attempts == 1
    assert excinfo.value.last_invocation is not None
    assert len(fake.invocations) == 1
    assert sleeps == []


class _RecordingGateway:
    """Records the exact request the runtime builds, then fails retryably."""

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []
        self.schemas: list[Mapping[str, Any]] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        raise ModelTimeoutError("boom")

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse:
        self.requests.append(request)
        self.schemas.append(schema)
        raise ModelTimeoutError("boom")


def test_request_is_built_from_the_profile() -> None:
    gateway = _RecordingGateway()
    runtime = AgentRuntime(gateway, RetryPolicy(max_attempts=1))

    with pytest.raises(AgentRuntimeError):
        runtime.decide_structured(profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA)

    request = gateway.requests[0]
    assert request.model == "test-model"
    assert request.temperature == 0.1
    assert request.max_tokens == 64
    assert request.messages == (
        Message(role="system", content=_SYSTEM),
        Message(role="user", content=_USER),
    )
    assert gateway.schemas[0] == _SCHEMA
