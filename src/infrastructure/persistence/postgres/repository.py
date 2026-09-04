# src/infrastructure/persistence/postgres/repository.py
"""PostgreSQL GameRepository + EventRepository (spec §7).

save() is the atomic unit: one transaction performs the optimistic-lock
upsert of the aggregate and the append of pending events. Events are
append-only; sequences are contiguous within one process lifetime per game
(spec D1: no collector rehydration — a restarted process creates a new game).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from domain.common.errors import (
    ConcurrentGameModification,
    GameNotFoundError,
    PersistenceError,
)
from domain.common.ids import GameId
from domain.events.collector import EventEnvelope
from domain.world.game import Game
from infrastructure.persistence.postgres.mapping import (
    event_to_row,
    game_from_row,
    game_to_row,
    row_to_event,
)

_UPSERT_GAME = """
INSERT INTO games (id, campaign_id, campaign_name, seed, version, status, state)
VALUES (%(id)s::uuid, %(campaign_id)s::uuid, %(campaign_name)s, %(seed)s,
        %(version)s + 1, %(status)s, %(state)s)
ON CONFLICT (id) DO UPDATE
SET campaign_id = EXCLUDED.campaign_id,
    campaign_name = EXCLUDED.campaign_name,
    seed = EXCLUDED.seed,
    version = %(version)s + 1,
    status = EXCLUDED.status,
    state = EXCLUDED.state,
    updated_at = now()
WHERE games.version = %(version)s
"""

_INSERT_EVENT = """
INSERT INTO game_events (game_id, sequence, event_id, occurred_at, event_type, payload)
VALUES (%(game_id)s::uuid, %(sequence)s, %(event_id)s::uuid,
        %(occurred_at)s::timestamptz, %(event_type)s, %(payload)s)
"""


class PostgresGameRepository:
    def __init__(self, connection: psycopg.Connection[dict[str, Any]]) -> None:
        self._connection = connection

    def save(self, game: Game, pending_events: Sequence[EventEnvelope]) -> None:
        row = game_to_row(game)
        row["state"] = Jsonb(row["state"])  # JSONB adaptation needs the wrapper
        try:
            with self._connection.transaction():
                cursor = self._connection.execute(_UPSERT_GAME, row)
                if cursor.rowcount == 0:
                    raise ConcurrentGameModification(
                        f"game '{game.game_id}' was modified concurrently "
                        f"(expected version {game.version})"
                    )
                for envelope in pending_events:
                    event_row = event_to_row(game.game_id, envelope)
                    event_row["payload"] = Jsonb(event_row["payload"])
                    self._connection.execute(_INSERT_EVENT, event_row)
        except psycopg.Error as error:
            raise PersistenceError(
                f"could not save game '{game.game_id}': {error}"
            ) from error
        game.version += 1

    def get(self, game_id: GameId) -> Game:
        try:
            row = self._connection.execute(
                """
                SELECT id, campaign_id, campaign_name, seed, version, status, state
                FROM games WHERE id = %s::uuid
                """,
                (str(game_id),),
            ).fetchone()
        except psycopg.Error as error:
            raise PersistenceError(
                f"could not load game '{game_id}': {error}"
            ) from error
        if row is None:
            raise GameNotFoundError(f"no game with id '{game_id}'")
        return game_from_row(row)


class PostgresEventRepository:
    def __init__(self, connection: psycopg.Connection[dict[str, Any]]) -> None:
        self._connection = connection

    def get_events(self, game_id: GameId) -> list[EventEnvelope]:
        try:
            rows = self._connection.execute(
                """
                SELECT sequence, event_id, occurred_at, event_type, payload
                FROM game_events WHERE game_id = %s::uuid ORDER BY sequence
                """,
                (str(game_id),),
            ).fetchall()
        except psycopg.Error as error:
            raise PersistenceError(
                f"could not load events for game '{game_id}': {error}"
            ) from error
        return [row_to_event(row, game_id) for row in rows]
