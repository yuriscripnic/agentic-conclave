"""Deterministic, scriptable ModelGateway for tests and offline runs (Phase 10)."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

from ai.models.errors import ModelError, ModelInvalidResponseError, ModelTimeoutError
from ai.models.schema import validate_against_schema
from ai.models.types import (
    LLMInvocation,
    ModelRequest,
    ModelResponse,
    StructuredModelResponse,
    Usage,
)

_FAKE_USAGE = Usage(input_tokens=10, output_tokens=5)


class FakeGatewayExhaustedError(Exception):
    """Raised when a test makes more gateway calls than it scripted."""


class FakeGatewayScriptError(Exception):
    """Raised when the scripted response kind does not match the call."""


@dataclass
class _Entry:
    kind: str  # "text" | "structured" | "error"
    text: str | None = None
    data: dict[str, Any] | None = None
    error: ModelError | None = None


class FakeModelGateway:
    """Serves scripted responses in order; records every LLMInvocation."""

    def __init__(self) -> None:
        self._queue: list[_Entry] = []
        self.invocations: list[LLMInvocation] = []

    def enqueue_text(self, text: str) -> None:
        self._queue.append(_Entry(kind="text", text=text))

    def enqueue_structured(self, data: dict[str, Any]) -> None:
        self._queue.append(_Entry(kind="structured", data=data))

    def enqueue_error(self, error: ModelError) -> None:
        self._queue.append(_Entry(kind="error", error=error))

    async def generate(self, request: ModelRequest) -> ModelResponse:
        entry = self._next("text")
        if entry.error is not None:
            self._raise(request, "generate", entry.error)
        assert entry.text is not None
        invocation = self._record(request, "generate")
        return ModelResponse(
            text=entry.text,
            model=request.model,
            usage=_FAKE_USAGE,
            finish_reason="stop",
            invocation=invocation,
        )

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse:
        entry = self._next("structured")
        if entry.error is not None:
            self._raise(request, "generate_structured", entry.error)
        assert entry.data is not None
        try:
            validate_against_schema(entry.data, schema)
        except ModelInvalidResponseError as exc:
            invocation = self._failed(request, "generate_structured", "invalid_response")
            raise ModelInvalidResponseError(str(exc), invocation=invocation) from exc
        invocation = self._record(request, "generate_structured")
        return StructuredModelResponse(
            data=entry.data,
            model=request.model,
            usage=_FAKE_USAGE,
            finish_reason="stop",
            invocation=invocation,
        )

    def _next(self, expected: str) -> _Entry:
        if not self._queue:
            raise FakeGatewayExhaustedError("FakeModelGateway has no scripted responses left")
        entry = self._queue[0]
        if entry.error is None and entry.kind != expected:
            raise FakeGatewayScriptError(
                f"next scripted response is {entry.kind!r}, but the call expected {expected!r}"
            )
        return self._queue.pop(0)

    def _raise(
        self, request: ModelRequest, operation: str, error: ModelError
    ) -> NoReturn:
        status = "timeout" if isinstance(error, ModelTimeoutError) else "error"
        error.invocation = LLMInvocation(
            provider="fake",
            model=request.model,
            operation=operation,
            status=status,
            error_kind=status,
            latency_ms=0,
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            request_id=uuid.uuid4().hex,
        )
        self.invocations.append(error.invocation)
        raise error

    def _record(self, request: ModelRequest, operation: str) -> LLMInvocation:
        invocation = LLMInvocation(
            provider="fake",
            model=request.model,
            operation=operation,
            status="ok",
            error_kind=None,
            latency_ms=0,
            input_tokens=_FAKE_USAGE.input_tokens,
            output_tokens=_FAKE_USAGE.output_tokens,
            estimated_cost_usd=None,
            request_id=uuid.uuid4().hex,
        )
        self.invocations.append(invocation)
        return invocation

    def _failed(
        self, request: ModelRequest, operation: str, error_kind: str
    ) -> LLMInvocation:
        invocation = LLMInvocation(
            provider="fake",
            model=request.model,
            operation=operation,
            status="error",
            error_kind=error_kind,
            latency_ms=0,
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            request_id=uuid.uuid4().hex,
        )
        self.invocations.append(invocation)
        return invocation
