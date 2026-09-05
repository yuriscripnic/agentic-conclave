"""OpenRouter adapter: single-attempt ModelGateway over the OpenAI-compatible API."""

import time
import uuid
from collections.abc import Mapping
from typing import Any

import httpx

from ai.models.errors import MissingAPIKeyError, ModelInvalidResponseError
from ai.models.profiles import ModelPricing
from ai.models.types import (
    LLMInvocation,
    ModelRequest,
    ModelResponse,
    StructuredModelResponse,
    Usage,
)

_FINISH_REASONS = {"stop", "length", "content_filter"}


class OpenRouterModelGateway:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        client: httpx.AsyncClient | None = None,
        pricing: Mapping[str, ModelPricing] | None = None,
        app_url: str | None = None,
        app_title: str | None = None,
    ) -> None:
        if not api_key:
            raise MissingAPIKeyError("OpenRouter API key is empty; set OPENROUTER_API_KEY")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._pricing = dict(pricing) if pricing is not None else {}
        self._app_url = app_url
        self._app_title = app_title

    async def generate(self, request: ModelRequest) -> ModelResponse:
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        body, content = await self._execute(request, "generate")
        usage = self._usage(body)
        model = str(body.get("model", request.model))
        invocation = LLMInvocation(
            provider="openrouter",
            model=model,
            operation="generate",
            status="ok",
            error_kind=None,
            latency_ms=self._latency_ms(started),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost_usd=self._cost(model, usage),
            request_id=request_id,
        )
        return ModelResponse(
            text=content,
            model=model,
            usage=usage,
            finish_reason=self._finish_reason(body),
            invocation=invocation,
        )

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse:
        raise NotImplementedError("structured output lands in a later task")

    async def _execute(
        self, request: ModelRequest, operation: str
    ) -> tuple[dict[str, Any], str]:
        payload = self._payload(request, operation)
        response = await self._post(request, payload)
        body = self._body(response)
        return body, self._content(body)

    def _payload(self, request: ModelRequest, operation: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if operation == "generate_structured":
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def _post(
        self, request: ModelRequest, payload: dict[str, Any]
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._app_url is not None:
            headers["HTTP-Referer"] = self._app_url
        if self._app_title is not None:
            headers["X-Title"] = self._app_title
        timeout = httpx.Timeout(request.timeout_seconds)
        url = f"{self._base_url}/chat/completions"
        if self._client is not None:
            return await self._client.post(
                url, json=payload, headers=headers, timeout=timeout
            )
        async with httpx.AsyncClient() as client:
            return await client.post(url, json=payload, headers=headers, timeout=timeout)

    def _body(self, response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()  # interim: replaced by error mapping in a later task
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelInvalidResponseError("OpenRouter returned a non-JSON body") from exc
        if not isinstance(body, dict):
            raise ModelInvalidResponseError("OpenRouter returned an unexpected JSON body")
        return body

    @staticmethod
    def _content(body: dict[str, Any]) -> str:
        choices = body.get("choices") or []
        if not choices:
            raise ModelInvalidResponseError("OpenRouter returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content:
            raise ModelInvalidResponseError("OpenRouter returned empty message content")
        return content

    @staticmethod
    def _usage(body: dict[str, Any]) -> Usage:
        usage = body.get("usage") or {}
        return Usage(
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
        )

    @staticmethod
    def _finish_reason(body: dict[str, Any]) -> str:
        choices = body.get("choices") or []
        raw = choices[0].get("finish_reason") if choices else None
        if raw is None:
            return "error"
        return raw if raw in _FINISH_REASONS else str(raw)

    def _cost(self, model: str, usage: Usage) -> float | None:
        pricing = self._pricing.get(model)
        if pricing is None:
            return None
        return (
            usage.input_tokens / 1_000_000 * pricing.input_per_million_usd
            + usage.output_tokens / 1_000_000 * pricing.output_per_million_usd
        )

    @staticmethod
    def _latency_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
