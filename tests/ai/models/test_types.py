from dataclasses import FrozenInstanceError, replace

import pytest

from ai.models.errors import (
    InvalidProfileError,
    MissingAPIKeyError,
    ModelError,
    ModelInvalidResponseError,
    ModelRateLimitedError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
    ProfileConfigError,
    ProfileNotFoundError,
    UnknownProviderError,
    UnsupportedSchemaError,
)
from ai.models.types import (
    LLMInvocation,
    Message,
    ModelRequest,
    ModelResponse,
    StructuredModelResponse,
    Usage,
)


def _invocation() -> LLMInvocation:
    return LLMInvocation(
        provider="fake",
        model="m",
        operation="generate",
        status="ok",
        error_kind=None,
        latency_ms=1,
        input_tokens=1,
        output_tokens=1,
        estimated_cost_usd=None,
        request_id="abc",
    )


def test_usage_total_tokens() -> None:
    assert Usage(input_tokens=11, output_tokens=7).total_tokens == 18


def test_model_request_defaults() -> None:
    request = ModelRequest(messages=(Message(role="user", content="hi"),), model="m")
    assert request.temperature == 0.7
    assert request.max_tokens is None
    assert request.timeout_seconds == 60.0


def test_message_is_frozen() -> None:
    message = Message(role="user", content="hello")
    with pytest.raises(FrozenInstanceError):
        message.content = "mutated"


def test_response_types_carry_invocation() -> None:
    invocation = _invocation()
    response = ModelResponse(
        text="ok", model="m", usage=Usage(1, 1), finish_reason="stop",
        invocation=invocation,
    )
    structured = StructuredModelResponse(
        data={"a": 1}, model="m", usage=Usage(1, 1), finish_reason="stop",
        invocation=invocation,
    )
    assert response.invocation is invocation
    assert structured.data == {"a": 1}


def test_model_error_stores_invocation() -> None:
    invocation = _invocation()
    error = ModelError("boom", invocation=invocation)
    assert error.invocation is invocation
    assert ModelError("bare").invocation is None


def test_rate_limited_error_carries_retry_after() -> None:
    error = ModelRateLimitedError("slow down", retry_after_seconds=7.0)
    assert error.retry_after_seconds == 7.0
    assert isinstance(error, ModelError)


def test_error_hierarchy() -> None:
    for cls in (
        ModelTimeoutError,
        ModelRateLimitedError,
        ModelRequestError,
        ModelUnavailableError,
        ModelInvalidResponseError,
        MissingAPIKeyError,
        UnsupportedSchemaError,
        ProfileConfigError,
        ProfileNotFoundError,
        InvalidProfileError,
        UnknownProviderError,
    ):
        assert issubclass(cls, ModelError)


def test_llm_invocation_telemetry_fields_have_defaults() -> None:
    invocation = _invocation()

    assert invocation.timestamp is None
    assert invocation.game_id is None
    assert invocation.agent_id is None
    assert invocation.correlation_id is None
    assert invocation.attempt == 1
    assert invocation.retrieval_count == 0
    assert invocation.tools_called == 0


def test_llm_invocation_is_enrichable_with_replace() -> None:
    original = _invocation()

    enriched = replace(
        original,
        timestamp="2026-09-09T12:00:00+00:00",
        game_id="game-1",
        agent_id="brix",
        correlation_id="corr-1",
        attempt=2,
        retrieval_count=3,
    )

    assert enriched.game_id == "game-1"
    assert enriched.agent_id == "brix"
    assert enriched.correlation_id == "corr-1"
    assert enriched.attempt == 2
    assert enriched.retrieval_count == 3
    assert enriched.provider == "fake"  # transport facts survive enrichment
    # the original frozen record is untouched
    assert original.game_id is None
    assert original.attempt == 1
