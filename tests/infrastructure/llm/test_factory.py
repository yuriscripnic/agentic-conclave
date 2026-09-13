import pytest

from ai.models.errors import UnknownProviderError
from infrastructure.llm import create_embedding_gateway, create_gateway
from infrastructure.llm.opencodego.adapter import OpenCodeGoModelGateway
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway


def test_factory_builds_openrouter_gateway() -> None:
    gateway = create_gateway("openrouter", api_key="k")
    assert isinstance(gateway, OpenRouterModelGateway)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(UnknownProviderError, match="ollama"):
        create_gateway("ollama", api_key="k")


def test_factory_builds_opencodego_gateway() -> None:
    gateway = create_gateway("opencode-go", api_key="k")
    assert isinstance(gateway, OpenCodeGoModelGateway)


def test_factory_rejects_opencodego_as_embedding_provider() -> None:
    with pytest.raises(UnknownProviderError, match="opencode-go"):
        create_embedding_gateway("opencode-go", api_key="k")
