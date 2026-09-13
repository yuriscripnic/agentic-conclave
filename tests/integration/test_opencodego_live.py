import asyncio
import os

import pytest

from ai.models.types import Message, ModelRequest
from infrastructure.llm import create_gateway

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("OPENCODE_API_KEY"),
        reason="OPENCODE_API_KEY not set; live provider test skipped (CLAUDE.md §46)",
    ),
]


def test_opencodego_live_generate() -> None:
    gateway = create_gateway("opencode-go", api_key=os.environ["OPENCODE_API_KEY"])
    request = ModelRequest(
        messages=(Message(role="user", content="Reply with exactly: ok"),),
        model="glm-5.3-flash",
        temperature=0.0,
        max_tokens=100,
        timeout_seconds=30.0,
    )
    response = asyncio.run(gateway.generate(request))
    assert response.text
    assert response.invocation.provider == "opencode-go"
    assert response.invocation.status == "ok"
    assert response.usage.total_tokens > 0
