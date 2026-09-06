"""Value types for the memory platform (spec §3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai.models.types import LLMInvocation, Usage


class MemoryKind(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class MemoryRecord:
    """One persisted agent memory; embedding is mandatory (embed before append)."""

    memory_id: str
    game_id: str
    agent_key: str
    kind: MemoryKind
    text: str
    round_number: int | None
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class EmbeddingRequest:
    """Batch embedding request: one call embeds all inputs."""

    texts: tuple[str, ...]
    model: str
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class EmbeddingResponse:
    """Vectors are parallel to the request's texts."""

    vectors: tuple[tuple[float, ...], ...]
    usage: Usage
    invocation: LLMInvocation
