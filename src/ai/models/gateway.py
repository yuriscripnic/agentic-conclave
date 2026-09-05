"""ModelGateway port — the AI platform's provider-agnostic model boundary."""

from collections.abc import Mapping
from typing import Any, Protocol

from ai.models.types import ModelRequest, ModelResponse, StructuredModelResponse


class ModelGateway(Protocol):
    """Single-attempt transport (CLAUDE.md §23). Retries belong to the caller (§28)."""

    async def generate(self, request: ModelRequest) -> ModelResponse: ...

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse: ...
