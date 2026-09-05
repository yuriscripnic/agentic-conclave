import asyncio
import os

import pytest

from ai.models.types import Message, ModelRequest
from infrastructure.llm import create_gateway

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set; live provider test skipped (CLAUDE.md §46)",
)


def test_openrouter_live_generate() -> None:
    gateway = create_gateway("openrouter", api_key=os.environ["OPENROUTER_API_KEY"])
    request = ModelRequest(
        messages=(Message(role="user", content="Reply with exactly: ok"),),
        model="z-ai/glm-5.3-flash",
        temperature=0.0,
        max_tokens=10,
        timeout_seconds=30.0,
    )
    response = asyncio.run(gateway.generate(request))
    assert response.text
    assert response.invocation.provider == "openrouter"
    assert response.invocation.status == "ok"
    assert response.usage.total_tokens > 0
