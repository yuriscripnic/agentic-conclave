import asyncio
import json

import httpx
import pytest

from ai.models.errors import MissingAPIKeyError
from ai.models.profiles import ModelPricing
from ai.models.types import Message, ModelRequest
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway

_SUCCESS_BODY = {
    "id": "resp-1",
    "model": "z-ai/glm-5.3-flash",
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
        "model": "z-ai/glm-5.3-flash",
    }
    fields.update(overrides)
    return ModelRequest(**fields)


def _gateway(handler, **kwargs) -> OpenRouterModelGateway:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenRouterModelGateway("test-key", client=client, **kwargs)


def test_generate_maps_success_response() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_SUCCESS_BODY)

    gateway = _gateway(handler)
    response = asyncio.run(gateway.generate(_request(temperature=0.4)))

    assert captured["url"].endswith("/chat/completions")
    assert captured["auth"] == "Bearer test-key"
    assert captured["body"]["model"] == "z-ai/glm-5.3-flash"
    assert captured["body"]["temperature"] == 0.4
    assert captured["body"]["messages"][0] == {"role": "user", "content": "decide"}
    assert "response_format" not in captured["body"]

    assert response.text == "I will strike the goblin."
    assert response.model == "z-ai/glm-5.3-flash"
    assert (response.usage.input_tokens, response.usage.output_tokens) == (11, 7)
    assert response.finish_reason == "stop"
    assert response.invocation.provider == "openrouter"
    assert response.invocation.status == "ok"
    assert response.invocation.operation == "generate"
    assert response.invocation.estimated_cost_usd is None
    assert response.invocation.request_id


def test_generate_computes_cost_from_pricing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SUCCESS_BODY)

    pricing = {"z-ai/glm-5.3-flash": ModelPricing(0.07125, 0.2375)}
    gateway = _gateway(handler, pricing=pricing)
    response = asyncio.run(gateway.generate(_request()))
    expected = 11 / 1_000_000 * 0.07125 + 7 / 1_000_000 * 0.2375
    assert response.invocation.estimated_cost_usd == pytest.approx(expected)


def test_unknown_finish_reason_passes_through() -> None:
    body = {
        **_SUCCESS_BODY,
        "choices": [{**_SUCCESS_BODY["choices"][0], "finish_reason": "weird_reason"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    gateway = _gateway(handler)
    response = asyncio.run(gateway.generate(_request()))
    assert response.finish_reason == "weird_reason"


def test_missing_finish_reason_maps_to_error() -> None:
    body = {**_SUCCESS_BODY, "choices": [{"message": {"role": "assistant", "content": "x"}}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    gateway = _gateway(handler)
    response = asyncio.run(gateway.generate(_request()))
    assert response.finish_reason == "error"


def test_empty_api_key_rejected_at_construction() -> None:
    with pytest.raises(MissingAPIKeyError):
        OpenRouterModelGateway("")


def test_timeout_seconds_propagates_to_request() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["timeout"] = request.extensions["timeout"]
        return httpx.Response(200, json=_SUCCESS_BODY)

    gateway = _gateway(handler)
    asyncio.run(gateway.generate(_request(timeout_seconds=1.5)))
    assert captured["timeout"]["read"] == 1.5
