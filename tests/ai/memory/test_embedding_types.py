"""Memory platform value types and ports (spec §3.1)."""

import dataclasses

import pytest

from ai.memory.ports import EmbeddingGateway, MemoryRepository
from ai.memory.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    MemoryKind,
    MemoryRecord,
)
from ai.models.types import LLMInvocation, Usage


def _invocation() -> LLMInvocation:
    return LLMInvocation(
        provider="deterministic",
        model="test-model",
        operation="embed",
        status="ok",
        error_kind=None,
        latency_ms=0,
        input_tokens=3,
        output_tokens=0,
        estimated_cost_usd=None,
        request_id="req-1",
    )


def test_memory_kind_values_match_the_persisted_labels() -> None:
    assert MemoryKind.EPISODIC.value == "episodic"
    assert MemoryKind.SEMANTIC.value == "semantic"


def test_memory_record_is_frozen() -> None:
    record = MemoryRecord(
        memory_id="mem-1",
        game_id="game-1",
        agent_key="brix",
        kind=MemoryKind.EPISODIC,
        text="Round 1: attacked Goblin.",
        round_number=1,
        embedding=(1.0, 0.0),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.text = "mutated"  # type: ignore[misc]


def test_embedding_request_defaults_to_sixty_second_timeout() -> None:
    request = EmbeddingRequest(texts=("hello",), model="test-model")
    assert request.texts == ("hello",)
    assert request.model == "test-model"
    assert request.timeout_seconds == 60.0


def test_embedding_response_is_frozen() -> None:
    response = EmbeddingResponse(
        vectors=((1.0, 0.0),),
        usage=Usage(input_tokens=3, output_tokens=0),
        invocation=_invocation(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        response.vectors = ((0.0, 1.0),)  # type: ignore[misc]


def test_ports_accept_structural_implementations() -> None:
    class _StubEmbedder:
        async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
            raise AssertionError("not called")

    class _StubRepository:
        def append(self, record: MemoryRecord) -> None:
            raise AssertionError("not called")

        def search(
            self,
            game_id: str,
            agent_key: str,
            query: tuple[float, ...],
            limit: int,
        ) -> tuple[MemoryRecord, ...]:
            return ()

    assert isinstance(_StubEmbedder(), EmbeddingGateway)
    assert isinstance(_StubRepository(), MemoryRepository)
