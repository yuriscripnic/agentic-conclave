"""PgvectorMemoryRepository against real PostgreSQL + pgvector (offline via pgserver)."""

import uuid
from typing import Any

from ai.memory.types import MemoryKind, MemoryRecord
from infrastructure.memory.pgvector_repository import PgvectorMemoryRepository
from infrastructure.persistence.postgres.connection import connect


def _create_game(connection: Any, game_id: str) -> None:
    """agent_memories.game_id has an FK to games — every test creates a real row."""
    connection.execute(
        """
        INSERT INTO games (id, campaign_id, campaign_name, seed, status, state)
        VALUES (%s::uuid, %s::uuid, 'Plan 6', 1, 'running', '{}'::jsonb)
        """,
        (game_id, str(uuid.uuid4())),
    )


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


def test_migration_creates_the_table_and_the_vector_extension(postgres_url: str) -> None:
    connection = connect(postgres_url)
    extension = connection.execute(
        "SELECT extname FROM pg_extension WHERE extname = 'vector'"
    ).fetchone()
    table = connection.execute(
        "SELECT to_regclass('agent_memories') AS reg"
    ).fetchone()
    connection.close()

    assert extension is not None
    assert table is not None
    assert table["reg"] == "agent_memories"


def test_append_then_search_orders_by_cosine_similarity(postgres_url: str) -> None:
    game_id = str(uuid.uuid4())
    connection = connect(postgres_url)
    _create_game(connection, game_id)
    repo = PgvectorMemoryRepository(connection)
    repo.append(_record(game_id, "brix", "near", (1.0, 0.0, 0.0)))
    repo.append(_record(game_id, "brix", "far", (0.0, 1.0, 0.0)))

    results = repo.search(game_id, "brix", (1.0, 0.0, 0.0), limit=5)
    connection.close()

    assert [record.text for record in results] == ["near", "far"]


def test_search_scopes_to_game_and_agent(postgres_url: str) -> None:
    game_id = str(uuid.uuid4())
    other_game_id = str(uuid.uuid4())
    connection = connect(postgres_url)
    _create_game(connection, game_id)
    _create_game(connection, other_game_id)
    repo = PgvectorMemoryRepository(connection)
    repo.append(_record(game_id, "brix", "mine", (1.0, 0.0, 0.0)))
    repo.append(_record(game_id, "mira", "other agent", (1.0, 0.0, 0.0)))
    repo.append(_record(other_game_id, "brix", "other game", (1.0, 0.0, 0.0)))

    results = repo.search(game_id, "brix", (1.0, 0.0, 0.0), limit=5)
    connection.close()

    assert [record.text for record in results] == ["mine"]


def test_append_exact_duplicate_is_a_noop(postgres_url: str) -> None:
    game_id = str(uuid.uuid4())
    connection = connect(postgres_url)
    _create_game(connection, game_id)
    repo = PgvectorMemoryRepository(connection)
    repo.append(
        _record(game_id, "brix", "same text", (1.0, 0.0, 0.0), kind=MemoryKind.SEMANTIC)
    )
    repo.append(
        _record(game_id, "brix", "same text", (0.0, 1.0, 0.0), kind=MemoryKind.SEMANTIC)
    )

    results = repo.search(game_id, "brix", (1.0, 0.0, 0.0), limit=5)
    connection.close()

    assert len(results) == 1
    assert results[0].embedding == (1.0, 0.0, 0.0)  # first write wins


def test_search_empty_scope_and_non_positive_limit_return_empty(
    postgres_url: str,
) -> None:
    game_id = str(uuid.uuid4())
    connection = connect(postgres_url)
    _create_game(connection, game_id)
    repo = PgvectorMemoryRepository(connection)
    repo.append(_record(game_id, "brix", "mine", (1.0, 0.0, 0.0)))

    assert repo.search(str(uuid.uuid4()), "brix", (1.0, 0.0, 0.0), limit=5) == ()
    assert repo.search(game_id, "nobody", (1.0, 0.0, 0.0), limit=5) == ()
    assert repo.search(game_id, "brix", (1.0, 0.0, 0.0), limit=0) == ()
    connection.close()


def test_search_roundtrips_every_field(postgres_url: str) -> None:
    game_id = str(uuid.uuid4())
    connection = connect(postgres_url)
    _create_game(connection, game_id)
    repo = PgvectorMemoryRepository(connection)
    repo.append(
        _record(
            game_id,
            "brix",
            "note",
            (1.0, 0.5, 0.0),  # float32-exact values
            kind=MemoryKind.SEMANTIC,
            round_number=3,
        )
    )

    results = repo.search(game_id, "brix", (1.0, 0.5, 0.0), limit=5)
    connection.close()

    assert len(results) == 1
    record = results[0]
    assert len(record.memory_id) == 36  # ::uuid round-trips to the dashed form
    assert record.game_id == game_id
    assert record.agent_key == "brix"
    assert record.kind is MemoryKind.SEMANTIC
    assert record.text == "note"
    assert record.round_number == 3
    assert record.embedding == (1.0, 0.5, 0.0)
