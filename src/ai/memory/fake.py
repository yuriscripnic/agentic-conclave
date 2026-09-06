"""Deterministic stdlib embedder for tests and offline runs (spec §2 Decision 9)."""

import hashlib
import math
import time
import uuid

from ai.memory.types import EmbeddingRequest, EmbeddingResponse
from ai.models.types import LLMInvocation, Usage


class DeterministicEmbeddingGateway:
    """Hash-based embedder: word buckets, L2-normalized; zero cost, fully offline."""

    DIM = 256
    PROVIDER = "deterministic"

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        started = time.perf_counter()
        vectors = tuple(self._embed_one(text) for text in request.texts)
        tokens = sum(len(self._tokens(text)) for text in request.texts)
        usage = Usage(input_tokens=tokens, output_tokens=0)
        invocation = LLMInvocation(
            provider=self.PROVIDER,
            model=request.model,
            operation="embed",
            status="ok",
            error_kind=None,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_tokens=tokens,
            output_tokens=0,
            estimated_cost_usd=None,
            request_id=uuid.uuid4().hex,
        )
        return EmbeddingResponse(vectors=vectors, usage=usage, invocation=invocation)

    def _embed_one(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.DIM
        for token in self._tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "big") % self.DIM
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return tuple(vector)
        return tuple(value / norm for value in vector)

    @staticmethod
    def _tokens(text: str) -> list[str]:
        tokens: list[str] = []
        for raw in text.lower().split():
            token = "".join(character for character in raw if character.isalnum())
            if token:
                tokens.append(token)
        return tokens
