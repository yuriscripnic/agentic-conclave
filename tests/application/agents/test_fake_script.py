"""ScriptedAgentGateway tests — the offline decision source."""

import asyncio

import pytest

from ai.models.errors import ModelInvalidResponseError
from ai.models.fake import FakeModelGateway
from ai.models.types import Message, ModelRequest
from application.agents.fake_script import ScriptedAgentGateway

_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


def _request() -> ModelRequest:
    return ModelRequest(messages=(Message(role="user", content="decide"),), model="test-model")


def test_reenqueue_the_decision_before_every_structured_call() -> None:
    inner = FakeModelGateway()
    calls: list[int] = []

    def _decision() -> dict[str, str]:
        calls.append(len(calls))
        return {"answer": f"ok-{len(calls)}"}

    gateway = ScriptedAgentGateway(inner, _decision)

    first = asyncio.run(gateway.generate_structured(_request(), _SCHEMA))
    second = asyncio.run(gateway.generate_structured(_request(), _SCHEMA))

    assert first.data == {"answer": "ok-1"}
    assert second.data == {"answer": "ok-2"}
    assert len(calls) == 2


def test_scripted_decisions_pass_real_schema_validation() -> None:
    gateway = ScriptedAgentGateway(FakeModelGateway(), lambda: {"answer": 3})

    with pytest.raises(ModelInvalidResponseError):
        asyncio.run(gateway.generate_structured(_request(), _SCHEMA))


def test_text_calls_pass_through_to_the_inner_gateway() -> None:
    inner = FakeModelGateway()
    inner.enqueue_text("hello")
    gateway = ScriptedAgentGateway(inner, lambda: {"answer": "unused"})

    response = asyncio.run(gateway.generate(_request()))

    assert response.text == "hello"
