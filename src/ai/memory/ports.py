"""Memory platform ports — the only memory seams (spec §3.1, CLAUDE.md §7)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai.memory.types import EmbeddingRequest, EmbeddingResponse, MemoryRecord


@runtime_checkable
class EmbeddingGateway(Protocol):
    """Single-attempt embedding transport; retry policy belongs to the caller."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...


@runtime_checkable
class MemoryRepository(Protocol):
    """Append + cosine search scoped to one (game, agent) pair."""

    def append(self, record: MemoryRecord) -> None: ...

    def search(
        self,
        game_id: str,
        agent_key: str,
        query: tuple[float, ...],
        limit: int,
        *,
        location: str | None = None,
    ) -> tuple[MemoryRecord, ...]: ...
    # location filters EPISODIC records to the agent's scene; SEMANTIC
    # records and untagged records always surface (grill decision #7).
