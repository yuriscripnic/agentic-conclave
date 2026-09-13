"""Provider-side model gateway implementations and the provider factory (CLAUDE.md §24)."""

from collections.abc import Mapping
from typing import cast

from ai.memory.ports import EmbeddingGateway
from ai.models.errors import UnknownProviderError
from ai.models.gateway import ModelGateway
from ai.models.profiles import ModelPricing
from infrastructure.llm.opencodego.adapter import OpenCodeGoModelGateway
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway

_PROVIDERS: dict[str, type] = {
    "openrouter": OpenRouterModelGateway,
    "opencode-go": OpenCodeGoModelGateway,
}

_EMBEDDING_PROVIDERS: dict[str, type] = {
    "openrouter": OpenRouterModelGateway,
}


def create_gateway(
    provider: str,
    *,
    api_key: str,
    pricing: Mapping[str, ModelPricing] | None = None,
) -> ModelGateway:
    """Build the gateway registered for *provider*; fail fast on unknown names."""
    adapter_class = _PROVIDERS.get(provider)
    if adapter_class is None:
        raise UnknownProviderError(f"no model gateway registered for provider {provider!r}")
    return cast(ModelGateway, adapter_class(api_key, pricing=pricing))


def create_embedding_gateway(provider: str, *, api_key: str) -> EmbeddingGateway:
    """Build the embedding gateway registered for *provider* (Plan 6 carve-out)."""
    adapter_class = _EMBEDDING_PROVIDERS.get(provider)
    if adapter_class is None:
        raise UnknownProviderError(
            f"no embedding gateway registered for provider {provider!r}"
        )
    return cast(EmbeddingGateway, adapter_class(api_key))
