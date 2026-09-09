"""ScriptedGmGateway tests — offline GM responses keyed off the task marker."""

import asyncio

from ai.models.fake import FakeModelGateway
from ai.models.types import Message, ModelRequest
from application.agents.fake_script import ScriptedGmGateway
from application.gm.director import GM_RESPONSE_SCHEMA


def _request(task: str) -> ModelRequest:
    return ModelRequest(
        messages=(
            Message(role="system", content="You are the GM."),
            Message(role="user", content=f"Task: {task}\nScene: ..."),
        ),
        model="test-model",
    )


def test_scripted_gm_keys_off_the_task_marker() -> None:
    inner = FakeModelGateway()
    gateway = ScriptedGmGateway(
        inner,
        lambda prompt: (
            {"narration": "reply"}
            if "Task: respond_to_player" in prompt
            else {"narration": "other"}
        ),
    )

    reply = asyncio.run(
        gateway.generate_structured(_request("respond_to_player"), GM_RESPONSE_SCHEMA)
    )
    other = asyncio.run(
        gateway.generate_structured(_request("narrate_open"), GM_RESPONSE_SCHEMA)
    )

    assert reply.data == {"narration": "reply"}
    assert other.data == {"narration": "other"}
    assert len(inner.invocations) == 2


def test_scripted_gm_serves_unlimited_calls() -> None:
    inner = FakeModelGateway()
    gateway = ScriptedGmGateway(
        inner, lambda _prompt: {"narration": "The fight begins."}
    )

    for _ in range(3):
        response = asyncio.run(
            gateway.generate_structured(_request("narrate_open"), GM_RESPONSE_SCHEMA)
        )
        assert response.data == {"narration": "The fight begins."}
