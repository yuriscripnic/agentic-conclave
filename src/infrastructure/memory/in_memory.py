"""In-memory MemoryRepository — same append/search contract as pgvector (spec §3.2)."""

from __future__ import annotations

import math

from ai.memory.types import MemoryKind, MemoryRecord


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryMemoryRepository:
    """List of records + pure-python cosine; exact-duplicate appends are no-ops."""

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []
        self._seen: set[tuple[str, str, MemoryKind, str]] = set()

    def append(self, record: MemoryRecord) -> None:
        key = (record.game_id, record.agent_key, record.kind, record.text)
        if key in self._seen:
            return
        self._seen.add(key)
        self._records.append(record)

    def search(
        self,
        game_id: str,
        agent_key: str,
        query: tuple[float, ...],
        limit: int,
    ) -> tuple[MemoryRecord, ...]:
        if limit <= 0:
            return ()
        scoped = [
            record
            for record in self._records
            if record.game_id == game_id and record.agent_key == agent_key
        ]
        scored = sorted(
            scoped,
            key=lambda record: _cosine(query, record.embedding),
            reverse=True,
        )
        return tuple(scored[:limit])
