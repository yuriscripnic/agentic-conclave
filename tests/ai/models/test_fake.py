import asyncio

import pytest

from ai.models.errors import ModelInvalidResponseError, ModelTimeoutError
from ai.models.fake import FakeGatewayExhaustedError, FakeGatewayScriptError, FakeModelGateway
from ai.models.types import Message, ModelRequest

_ACTION_SCHEMA = {
    "type": "object",
    "properties": {"action_type": {"type": "string"}},
    "required": ["action_type"],
    "additionalProperties": False,
}


def _request() -> ModelRequest:
    return ModelRequest(
        messages=(Message(role="user", content="decide"),), model="test-model"
    )


def test_serves_scripted_text_in_order() -> None:
    fake = FakeModelGateway()
    fake.enqueue_text("first")
    fake.enqueue_text("second")

    first = asyncio.run(fake.generate(_request()))
    second = asyncio.run(fake.generate(_request()))

    assert (first.text, second.text) == ("first", "second")
    assert first.finish_reason == "stop"
    assert first.model == "test-model"
    assert first.usage.total_tokens == 15
    assert first.invocation.provider == "fake"
    assert first.invocation.status == "ok"
    assert len(fake.invocations) == 2


def test_serves_structured_payload() -> None:
    fake = FakeModelGateway()
    fake.enqueue_structured({"action_type": "attack"})

    response = asyncio.run(fake.generate_structured(_request(), _ACTION_SCHEMA))

    assert response.data == {"action_type": "attack"}
    assert response.invocation.provider == "fake"
    assert response.invocation.operation == "generate_structured"


def test_rejects_invalid_scripted_payload() -> None:
    fake = FakeModelGateway()
    fake.enqueue_structured({"action_type": 3})

    with pytest.raises(ModelInvalidResponseError) as excinfo:
        asyncio.run(fake.generate_structured(_request(), _ACTION_SCHEMA))

    assert "action_type" in str(excinfo.value)
    assert excinfo.value.invocation is not None
    assert excinfo.value.invocation.error_kind == "invalid_response"
    assert fake.invocations[-1].status == "error"


def test_empty_queue_raises() -> None:
    fake = FakeModelGateway()
    with pytest.raises(FakeGatewayExhaustedError):
        asyncio.run(fake.generate(_request()))


def test_kind_mismatch_does_not_consume_queue() -> None:
    fake = FakeModelGateway()
    fake.enqueue_text("hello")

    with pytest.raises(FakeGatewayScriptError):
        asyncio.run(fake.generate_structured(_request(), _ACTION_SCHEMA))

    response = asyncio.run(fake.generate(_request()))
    assert response.text == "hello"


def test_error_injection_attaches_invocation() -> None:
    fake = FakeModelGateway()
    fake.enqueue_error(ModelTimeoutError("slow"))

    with pytest.raises(ModelTimeoutError) as excinfo:
        asyncio.run(fake.generate(_request()))

    assert excinfo.value.invocation is not None
    assert excinfo.value.invocation.status == "timeout"
    assert fake.invocations[-1].status == "timeout"
