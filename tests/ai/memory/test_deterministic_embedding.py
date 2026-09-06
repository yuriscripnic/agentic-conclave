"""DeterministicEmbeddingGateway: offline, reproducible embeddings (spec §3.1)."""

import asyncio
import math

from ai.memory.fake import DeterministicEmbeddingGateway
from ai.memory.types import EmbeddingRequest, EmbeddingResponse


def _embed(*texts: str) -> EmbeddingResponse:
    gateway = DeterministicEmbeddingGateway()
    return asyncio.run(
        gateway.embed(EmbeddingRequest(texts=texts, model="test-model"))
    )


def test_same_text_same_vector_across_instances_and_calls() -> None:
    first = _embed("Brix attacked the Goblin.")
    second = _embed("Brix attacked the Goblin.")
    assert first.vectors == second.vectors


def test_vectors_are_fixed_dimension_and_unit_length() -> None:
    vector = _embed("Brix attacked the Goblin.").vectors[0]
    assert len(vector) == DeterministicEmbeddingGateway.DIM
    assert math.isclose(sum(value * value for value in vector), 1.0, rel_tol=1e-9)


def test_batch_texts_map_to_parallel_vectors() -> None:
    response = _embed("alpha", "beta", "gamma")
    assert len(response.vectors) == 3


def test_related_texts_score_higher_than_unrelated() -> None:
    response = _embed(
        "the orc hits hard stay at range",
        "the orc hits hard",
        "zebra quantum piano",
    )

    def dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert dot(response.vectors[0], response.vectors[1]) > dot(
        response.vectors[0], response.vectors[2]
    )


def test_punctuation_and_case_do_not_change_the_vector() -> None:
    response = _embed("Goblin!", "goblin")
    assert response.vectors[0] == response.vectors[1]


def test_empty_text_yields_a_zero_vector() -> None:
    response = _embed("   ")
    assert response.vectors[0] == (0.0,) * DeterministicEmbeddingGateway.DIM


def test_invocation_metadata_records_the_embed_operation() -> None:
    response = _embed("hello world")
    assert response.invocation.provider == "deterministic"
    assert response.invocation.model == "test-model"
    assert response.invocation.operation == "embed"
    assert response.invocation.status == "ok"
    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens == 0
    assert response.invocation.estimated_cost_usd is None
