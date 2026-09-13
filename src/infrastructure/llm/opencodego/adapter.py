"""OpenCode Go adapter: OpenRouterModelGateway pointed at the Go endpoint."""

import uuid
from collections.abc import Mapping

import httpx

from ai.memory.types import EmbeddingRequest, EmbeddingResponse
from ai.models.errors import MissingAPIKeyError, ModelError
from ai.models.profiles import ModelPricing
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway

_USER_AGENT = "agentic-conclave/0.1"


class OpenCodeGoModelGateway(OpenRouterModelGateway):
    PROVIDER_NAME = "opencode-go"
    DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        pricing: Mapping[str, ModelPricing] | None = None,
        session_id: str | None = None,
    ) -> None:
        if not api_key:
            raise MissingAPIKeyError("OpenCode Go API key is empty; set OPENCODE_API_KEY")
        super().__init__(api_key, base_url=base_url, client=client, pricing=pricing)
        self.session_id = session_id or uuid.uuid4().hex

    def _default_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": _USER_AGENT,
            "x-opencode-session": self.session_id,
        }

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Go exposes no /embeddings endpoint; memory embeds deterministically."""
        raise ModelError("OpenCode Go does not expose an embeddings endpoint")
