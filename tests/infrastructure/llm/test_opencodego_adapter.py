import asyncio
import json

import httpx
import pytest

from ai.memory.types import EmbeddingRequest
from ai.models.errors import MissingAPIKeyError, ModelError
from ai.models.profiles import ModelPricing
from ai.models.types import Message, ModelRequest
from infrastructure.llm.opencodego.adapter import OpenCodeGoModelGateway

_SUCCESS_BODY = {
    "id": "resp-1",
    "model": "glm-5.3-flash",
    "choices": [
        {
            "message": {"role": "assistant", "content": "I will strike the goblin."},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
}


def _request(**overrides) -> ModelRequest:
    fields = {
        "messages": (Message(role="user", content="decide"),),
        "model": "glm-5.3-flash",
    }
    fields.update(overrides)
    return ModelRequest(**fields)


def _gateway(handler, **kwargs) -> OpenCodeGoModelGateway:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenCodeGoModelGateway("test-key", client=client, **kwargs)


def test_generate_hits_go_endpoint_with_go_headers() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["user_agent"] = request.headers.get("User-Agent")
        captured["session"] = request.headers.get("x-opencode-session")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_SUCCESS_BODY)

    gateway = _gateway(handler)
    response = asyncio.run(gateway.generate(_request(temperature=0.4)))

    assert captured["url"] == "https://opencode.ai/zen/go/v1/chat/completions"
    assert captured["auth"] == "Bearer test-key"
    assert captured["user_agent"] == "agentic-conclave/0.1"
    assert captured["session"]  # a stable non-empty session id exists
    assert captured["session"] == gateway.session_id
    assert captured["body"]["model"] == "glm-5.3-flash"
    assert captured["body"]["temperature"] == 0.4
    assert "HTTP-Referer" not in captured and "X-Title" not in captured

    assert response.text == "I will strike the goblin."
    assert response.invocation.provider == "opencode-go"
    assert response.invocation.status == "ok"
    assert response.invocation.operation == "generate"
    assert response.invocation.request_id


def test_generate_computes_cost_from_go_pricing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SUCCESS_BODY)

    pricing = {"glm-5.3-flash": ModelPricing(0.15, 0.50)}
    gateway = _gateway(handler, pricing=pricing)
    response = asyncio.run(gateway.generate(_request()))
    expected = 11 / 1_000_000 * 0.15 + 7 / 1_000_000 * 0.50
    assert response.invocation.estimated_cost_usd == pytest.approx(expected)


def test_session_id_is_stable_per_instance_and_explicit_override_wins() -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers.get("x-opencode-session") or "")
        return httpx.Response(200, json=_SUCCESS_BODY)

    gateway = _gateway(handler)
    asyncio.run(gateway.generate(_request()))
    asyncio.run(gateway.generate(_request()))
    assert sent[0] == sent[1] == gateway.session_id

    custom = _gateway(handler, session_id="my-session")
    asyncio.run(custom.generate(_request()))
    assert custom.session_id == "my-session"
    assert sent[-1] == "my-session"


def test_generate_structured_labels_provider_opencodego() -> None:
    body = {
        **_SUCCESS_BODY,
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"action_type": "attack"}),
                },
                "finish_reason": "stop",
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    gateway = _gateway(handler)
    response = asyncio.run(
        gateway.generate_structured(_request(), {"type": "object"})
    )
    assert response.data == {"action_type": "attack"}
    assert response.invocation.provider == "opencode-go"


def test_embed_raises_not_supported() -> None:
    gateway = OpenCodeGoModelGateway("test-key")
    with pytest.raises(ModelError, match="embeddings"):
        asyncio.run(
            gateway.embed(EmbeddingRequest(texts=("x",), model="glm-5.3-flash"))
        )


def test_empty_api_key_rejected_at_construction() -> None:
    with pytest.raises(MissingAPIKeyError):
        OpenCodeGoModelGateway("")
