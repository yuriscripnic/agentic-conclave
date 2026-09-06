"""OpenRouterModelGateway.embed: OpenAI-compatible /embeddings mapping (spec §3.2)."""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from ai.memory.types import EmbeddingRequest
from ai.models.errors import (
    ModelInvalidResponseError,
    ModelRateLimitedError,
    ModelUnavailableError,
)
from ai.models.profiles import ModelPricing
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway

_EMBED_BODY: dict[str, Any] = {
    "id": "emb-1",
    "model": "openai/text-embedding-3-small",
    "data": [
        {"index": 0, "embedding": [0.1, 0.2, 0.3]},
        {"index": 1, "embedding": [0.4, 0.5]},
    ],
    "usage": {"prompt_tokens": 9},
}


def _gateway(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    pricing: dict[str, ModelPricing] | None = None,
) -> OpenRouterModelGateway:
    return OpenRouterModelGateway(
        "test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        pricing=pricing,
    )


def _request(**overrides: Any) -> EmbeddingRequest:
    values: dict[str, Any] = {
        "texts": ("Brix attacks.", "Goblin falls."),
        "model": "openai/text-embedding-3-small",
    }
    values.update(overrides)
    return EmbeddingRequest(**values)


def test_embed_posts_the_openai_compatible_payload() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_EMBED_BODY)

    response = asyncio.run(_gateway(handler).embed(_request()))

    assert captured["url"].endswith("/embeddings")
    assert captured["authorization"] == "Bearer test-key"
    assert captured["body"] == {
        "model": "openai/text-embedding-3-small",
        "input": ["Brix attacks.", "Goblin falls."],
    }
    assert response.vectors == ((0.1, 0.2, 0.3), (0.4, 0.5))


def test_embed_maps_usage_invocation_and_cost() -> None:
    pricing = {
        "openai/text-embedding-3-small": ModelPricing(
            input_per_million_usd=0.02, output_per_million_usd=0.0
        )
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_EMBED_BODY)

    response = asyncio.run(_gateway(handler, pricing=pricing).embed(_request()))

    assert response.usage.input_tokens == 9
    assert response.usage.output_tokens == 0
    assert response.invocation.provider == "openrouter"
    assert response.invocation.model == "openai/text-embedding-3-small"
    assert response.invocation.operation == "embed"
    assert response.invocation.status == "ok"
    assert response.invocation.input_tokens == 9
    assert response.invocation.output_tokens == 0
    assert response.invocation.estimated_cost_usd == pytest.approx(9 / 1_000_000 * 0.02)
    assert response.invocation.request_id


def test_embed_rejects_a_count_mismatch() -> None:
    body = {**_EMBED_BODY, "data": _EMBED_BODY["data"][:1]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with pytest.raises(ModelInvalidResponseError, match="embeddings for 2"):
        asyncio.run(_gateway(handler).embed(_request()))


def test_embed_rejects_malformed_embeddings() -> None:
    non_numeric = {
        **_EMBED_BODY,
        "data": [
            {"index": 0, "embedding": ["x", None]},
            {"index": 1, "embedding": [0.1]},
        ],
    }
    not_an_object = {**_EMBED_BODY, "data": ["nope", "nope"]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=non_numeric)

    with pytest.raises(ModelInvalidResponseError, match="non-numeric"):
        asyncio.run(_gateway(handler).embed(_request()))

    def bad_shape(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=not_an_object)

    with pytest.raises(ModelInvalidResponseError, match="malformed"):
        asyncio.run(_gateway(bad_shape).embed(_request()))


def test_embed_maps_error_statuses_and_carries_the_invocation() -> None:
    def rate_limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"error": "slow down"}, headers={"retry-after": "7"}
        )

    with pytest.raises(ModelRateLimitedError) as limited:
        asyncio.run(_gateway(rate_limited).embed(_request()))
    assert limited.value.retry_after_seconds == 7.0
    assert limited.value.invocation is not None
    assert limited.value.invocation.operation == "embed"
    assert limited.value.invocation.status == "error"
    assert limited.value.invocation.error_kind == "rate_limited"

    def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    with pytest.raises(ModelUnavailableError):
        asyncio.run(_gateway(unavailable).embed(_request()))


def test_embed_rejects_a_non_json_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    with pytest.raises(ModelInvalidResponseError, match="non-JSON"):
        asyncio.run(_gateway(handler).embed(_request()))
