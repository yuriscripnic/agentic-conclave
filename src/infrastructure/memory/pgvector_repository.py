"""pgvector-backed memory repository: cosine search over agent memories (spec §3.2)."""

from __future__ import annotations

from typing import Any

import psycopg

from ai.memory.types import MemoryKind, MemoryRecord
from domain.common.errors import PersistenceError


def _vector_literal(vector: tuple[float, ...]) -> str:
    """pgvector's text format: '[1,0.5,0.25]' — cast with ::vector in the SQL."""
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


def _embedding_from_row(raw: object) -> tuple[float, ...]:
    """psycopg sees the untyped vector column as text ('[1,0.5,0.25]') or a list."""
    if isinstance(raw, str):
        stripped = raw.strip().strip("[]")
        if not stripped:
            return ()
        return tuple(float(part) for part in stripped.split(","))
    if isinstance(raw, (list, tuple)):
        return tuple(float(value) for value in raw)
    raise PersistenceError(f"unexpected embedding column type: {type(raw)!r}")


class PgvectorMemoryRepository:
    """Cosine search via pgvector's <=> operator; exact-duplicate appends are no-ops."""

    def __init__(self, connection: psycopg.Connection[dict[str, Any]]) -> None:
        self._connection = connection

    def append(self, record: MemoryRecord) -> None:
        try:
            with self._connection.transaction():
                duplicate = self._connection.execute(
                    """
                    SELECT 1 FROM agent_memories
                    WHERE game_id = %s::uuid AND agent_key = %s
                      AND kind = %s AND text = %s
                    """,
                    (
                        record.game_id,
                        record.agent_key,
                        record.kind.value,
                        record.text,
                    ),
                ).fetchone()
                if duplicate is not None:
                    return
                self._connection.execute(
                    """
                    INSERT INTO agent_memories
                        (memory_id, game_id, agent_key, kind, text, round_number,
                         embedding)
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s::vector)
                    """,
                    (
                        record.memory_id,
                        record.game_id,
                        record.agent_key,
                        record.kind.value,
                        record.text,
                        record.round_number,
                        _vector_literal(record.embedding),
                    ),
                )
        except psycopg.Error as error:
            raise PersistenceError(f"could not append memory: {error}") from error

    def search(
        self,
        game_id: str,
        agent_key: str,
        query: tuple[float, ...],
        limit: int,
    ) -> tuple[MemoryRecord, ...]:
        if limit <= 0:
            return ()
        try:
            rows = self._connection.execute(
                """
                SELECT memory_id, game_id, agent_key, kind, text, round_number,
                       embedding
                FROM agent_memories
                WHERE game_id = %s::uuid AND agent_key = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (game_id, agent_key, _vector_literal(query), limit),
            ).fetchall()
        except psycopg.Error as error:
            raise PersistenceError(f"could not search memories: {error}") from error
        return tuple(
            MemoryRecord(
                memory_id=str(row["memory_id"]),
                game_id=str(row["game_id"]),
                agent_key=row["agent_key"],
                kind=MemoryKind(row["kind"]),
                text=row["text"],
                round_number=row["round_number"],
                embedding=_embedding_from_row(row["embedding"]),
            )
            for row in rows
        )
