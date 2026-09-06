"""InMemoryMemoryRepository: cosine search + duplicate suppression (spec §3.2)."""

import uuid

from ai.memory.types import MemoryKind, MemoryRecord
from infrastructure.memory.in_memory import InMemoryMemoryRepository


def _record(
    game_id: str,
    agent_key: str,
    text: str,
    embedding: tuple[float, ...],
    *,
    kind: MemoryKind = MemoryKind.EPISODIC,
    round_number: int | None = 1,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=uuid.uuid4().hex,
        game_id=game_id,
        agent_key=agent_key,
        kind=kind,
        text=text,
        round_number=round_number,
        embedding=embedding,
    )


def test_search_returns_the_most_similar_memory_first() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(_record("g1", "brix", "near", (1.0, 0.0)))
    repo.append(_record("g1", "brix", "far", (0.0, 1.0)))

    results = repo.search("g1", "brix", (1.0, 0.0), limit=5)

    assert [record.text for record in results] == ["near", "far"]


def test_search_scopes_to_game_and_agent() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(_record("g1", "brix", "mine", (1.0, 0.0)))
    repo.append(_record("g1", "mira", "other agent", (1.0, 0.0)))
    repo.append(_record("g2", "brix", "other game", (1.0, 0.0)))

    results = repo.search("g1", "brix", (1.0, 0.0), limit=5)

    assert [record.text for record in results] == ["mine"]


def test_search_respects_the_limit() -> None:
    repo = InMemoryMemoryRepository()
    for index in range(3):
        repo.append(_record("g1", "brix", f"memory {index}", (1.0, 0.0)))

    results = repo.search("g1", "brix", (1.0, 0.0), limit=2)

    assert len(results) == 2


def test_search_of_an_unknown_scope_is_empty() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(_record("g1", "brix", "near", (1.0, 0.0)))

    assert repo.search("nowhere", "brix", (1.0, 0.0), limit=5) == ()
    assert repo.search("g1", "nobody", (1.0, 0.0), limit=5) == ()


def test_search_with_non_positive_limit_is_empty() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(_record("g1", "brix", "near", (1.0, 0.0)))

    assert repo.search("g1", "brix", (1.0, 0.0), limit=0) == ()


def test_exact_duplicate_append_is_a_noop() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(
        _record("g1", "brix", "same text", (1.0, 0.0), kind=MemoryKind.SEMANTIC)
    )
    repo.append(
        _record("g1", "brix", "same text", (0.0, 1.0), kind=MemoryKind.SEMANTIC)
    )

    results = repo.search("g1", "brix", (1.0, 0.0), limit=5)

    assert len(results) == 1
    assert results[0].embedding == (1.0, 0.0)  # first write wins


def test_duplicate_key_includes_kind() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(_record("g1", "brix", "same text", (1.0, 0.0), kind=MemoryKind.EPISODIC))
    repo.append(_record("g1", "brix", "same text", (1.0, 0.0), kind=MemoryKind.SEMANTIC))

    results = repo.search("g1", "brix", (1.0, 0.0), limit=5)

    assert len(results) == 2
