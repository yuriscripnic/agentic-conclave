import pytest

from ai.models.errors import UnknownProviderError
from infrastructure.llm import create_gateway
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway


def test_factory_builds_openrouter_gateway() -> None:
    gateway = create_gateway("openrouter", api_key="k")
    assert isinstance(gateway, OpenRouterModelGateway)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(UnknownProviderError, match="ollama"):
        create_gateway("ollama", api_key="k")
