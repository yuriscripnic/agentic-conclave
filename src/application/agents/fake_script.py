"""Scripted decisions for --agent fake and offline tests: the queue never exhausts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ai.models.fake import FakeModelGateway
from ai.models.types import ModelRequest, ModelResponse, StructuredModelResponse


class ScriptedAgentGateway:
    """Wraps a FakeModelGateway and re-enqueues a canned decision before every call."""

    def __init__(
        self,
        inner: FakeModelGateway,
        decision: Callable[[], Mapping[str, Any]],
    ) -> None:
        self._inner = inner
        self._decision = decision

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return await self._inner.generate(request)

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse:
        self._inner.enqueue_structured(dict(self._decision()))
        return await self._inner.generate_structured(request, schema)


class ScriptedGmGateway:
    """Wraps a FakeModelGateway; re-enqueues a canned GM response before every call.

    The decision callable receives the user prompt so it can key off the GM
    task marker (narrate_open | react_to_events | respond_to_player).
    """

    def __init__(
        self,
        inner: FakeModelGateway,
        decision: Callable[[str], Mapping[str, Any]],
    ) -> None:
        self._inner = inner
        self._decision = decision

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return await self._inner.generate(request)

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse:
        self._inner.enqueue_structured(dict(self._decision(request.messages[-1].content)))
        return await self._inner.generate_structured(request, schema)
