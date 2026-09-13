"""OpenRouter adapter: single-attempt ModelGateway over the OpenAI-compatible API."""

import json
import time
import uuid
from collections.abc import Mapping
from typing import Any

import httpx

from ai.memory.types import EmbeddingRequest, EmbeddingResponse
from ai.models.errors import (
    MissingAPIKeyError,
    ModelError,
    ModelInvalidResponseError,
    ModelRateLimitedError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from ai.models.profiles import ModelPricing
from ai.models.schema import validate_against_schema
from ai.models.types import (
    LLMInvocation,
    ModelRequest,
    ModelResponse,
    StructuredModelResponse,
    Usage,
)

_FINISH_REASONS = {"stop", "length", "content_filter"}


def _error_kind(exc: ModelError) -> str:
    if isinstance(exc, ModelTimeoutError):
        return "timeout"
    if isinstance(exc, ModelRateLimitedError):
        return "rate_limited"
    if isinstance(exc, ModelRequestError):
        return "bad_request"
    if isinstance(exc, ModelUnavailableError):
        return "unavailable"
    if isinstance(exc, ModelInvalidResponseError):
        return "invalid_response"
    return "error"


class OpenRouterModelGateway:
    PROVIDER_NAME = "openrouter"
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        pricing: Mapping[str, ModelPricing] | None = None,
        app_url: str | None = None,
        app_title: str | None = None,
    ) -> None:
        if not api_key:
            raise MissingAPIKeyError("OpenRouter API key is empty; set OPENROUTER_API_KEY")
        self._api_key = api_key
        self._base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self._client = client
        self._pricing = dict(pricing) if pricing is not None else {}
        self._app_url = app_url
        self._app_title = app_title

    async def generate(self, request: ModelRequest) -> ModelResponse:
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        try:
            body, content = await self._execute(request, "generate")
        except ModelError as exc:
            raise self._with_invocation(
                request.model, "generate", started, request_id, exc
            ) from exc
        usage = self._usage(body)
        model = str(body.get("model", request.model))
        invocation = LLMInvocation(
            provider=self.PROVIDER_NAME,
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
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        try:
            body, content = await self._execute(request, "generate_structured")
            data = self._structured_data(content, schema)
        except ModelError as exc:
            raise self._with_invocation(
                request.model, "generate_structured", started, request_id, exc
            ) from exc
        usage = self._usage(body)
        model = str(body.get("model", request.model))
        invocation = LLMInvocation(
            provider=self.PROVIDER_NAME,
            model=model,
            operation="generate_structured",
            status="ok",
            error_kind=None,
            latency_ms=self._latency_ms(started),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost_usd=self._cost(model, usage),
            request_id=request_id,
        )
        return StructuredModelResponse(
            data=data,
            model=model,
            usage=usage,
            finish_reason=self._finish_reason(body),
            invocation=invocation,
        )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Embed a batch of texts via the OpenAI-compatible /embeddings endpoint."""
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        try:
            body, vectors = await self._execute_embeddings(request)
        except ModelError as exc:
            raise self._with_invocation(
                request.model, "embed", started, request_id, exc
            ) from exc
        usage = Usage(
            input_tokens=int((body.get("usage") or {}).get("prompt_tokens", 0)),
            output_tokens=0,
        )
        model = str(body.get("model", request.model))
        invocation = LLMInvocation(
            provider=self.PROVIDER_NAME,
            model=model,
            operation="embed",
            status="ok",
            error_kind=None,
            latency_ms=self._latency_ms(started),
            input_tokens=usage.input_tokens,
            output_tokens=0,
            estimated_cost_usd=self._cost(model, usage),
            request_id=request_id,
        )
        return EmbeddingResponse(vectors=vectors, usage=usage, invocation=invocation)

    @staticmethod
    def _structured_data(content: str, schema: Mapping[str, Any]) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ModelInvalidResponseError(
                f"structured output is not valid JSON: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ModelInvalidResponseError("structured output is not a JSON object")
        validate_against_schema(parsed, schema)
        return parsed

    def _with_invocation(
        self,
        model: str,
        operation: str,
        started: float,
        request_id: str,
        exc: ModelError,
    ) -> ModelError:
        status = "timeout" if isinstance(exc, ModelTimeoutError) else "error"
        exc.invocation = LLMInvocation(
            provider=self.PROVIDER_NAME,
            model=model,
            operation=operation,
            status=status,
            error_kind=_error_kind(exc),
            latency_ms=self._latency_ms(started),
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            request_id=request_id,
        )
        return exc

    async def _execute(
        self, request: ModelRequest, operation: str
    ) -> tuple[dict[str, Any], str]:
        payload = self._payload(request, operation)
        try:
            response = await self._post(
                f"{self._base_url}/chat/completions",
                payload,
                request.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(f"OpenRouter request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ModelError(f"OpenRouter transport error: {exc}") from exc
        body = self._body(response)
        return body, self._content(body)

    async def _execute_embeddings(
        self, request: EmbeddingRequest
    ) -> tuple[dict[str, Any], tuple[tuple[float, ...], ...]]:
        payload = {"model": request.model, "input": list(request.texts)}
        try:
            response = await self._post(
                f"{self._base_url}/embeddings", payload, request.timeout_seconds
            )
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(f"OpenRouter request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ModelError(f"OpenRouter transport error: {exc}") from exc
        body = self._body(response)
        return body, self._embedding_vectors(body, len(request.texts))

    @staticmethod
    def _embedding_vectors(
        body: dict[str, Any], expected: int
    ) -> tuple[tuple[float, ...], ...]:
        data = body.get("data")
        if not isinstance(data, list):
            raise ModelInvalidResponseError("OpenRouter returned no embedding data")
        if len(data) != expected:
            raise ModelInvalidResponseError(
                f"OpenRouter returned {len(data)} embeddings for {expected} input(s)"
            )
        vectors: list[tuple[float, ...]] = []
        for entry in data:
            raw = entry.get("embedding") if isinstance(entry, dict) else None
            if not isinstance(raw, list) or not raw:
                raise ModelInvalidResponseError(
                    "OpenRouter returned a malformed embedding"
                )
            try:
                vectors.append(tuple(float(value) for value in raw))
            except (TypeError, ValueError) as exc:
                raise ModelInvalidResponseError(
                    "OpenRouter returned a non-numeric embedding"
                ) from exc
        return tuple(vectors)

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

    def _default_headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._app_url is not None:
            headers["HTTP-Referer"] = self._app_url
        if self._app_title is not None:
            headers["X-Title"] = self._app_title
        return headers

    async def _post(
        self, url: str, payload: dict[str, Any], timeout_seconds: float
    ) -> httpx.Response:
        headers = self._default_headers()
        timeout = httpx.Timeout(timeout_seconds)
        if self._client is not None:
            return await self._client.post(
                url, json=payload, headers=headers, timeout=timeout
            )
        async with httpx.AsyncClient() as client:
            return await client.post(url, json=payload, headers=headers, timeout=timeout)

    def _body(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 429:
            raise ModelRateLimitedError(
                "OpenRouter rate limit hit (HTTP 429)",
                retry_after_seconds=self._retry_after(response),
            )
        if 400 <= response.status_code < 500:
            raise ModelRequestError(
                f"OpenRouter rejected the request (HTTP {response.status_code}): "
                f"{response.text[:200]}"
            )
        if response.status_code >= 500:
            raise ModelUnavailableError(
                f"OpenRouter unavailable (HTTP {response.status_code})"
            )
        if response.status_code != 200:
            raise ModelError(
                f"OpenRouter returned unexpected status HTTP {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelInvalidResponseError("OpenRouter returned a non-JSON body") from exc
        if not isinstance(body, dict):
            raise ModelInvalidResponseError("OpenRouter returned an unexpected JSON body")
        return body

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        raw = response.headers.get("retry-after")
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

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
