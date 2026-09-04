# tests/infrastructure/test_postgres_migrations.py
"""Migration runner behaviour against real PostgreSQL (spec §8, §10)."""

import pytest

from domain.common.errors import PersistenceError
from infrastructure.persistence.postgres.connection import connect


def test_initial_migration_creates_tables_and_is_recorded(postgres_url: str) -> None:
    connection = connect(postgres_url)
    tables = {
        row["table_name"]
        for row in connection.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        ).fetchall()
    }
    assert {"games", "game_events", "schema_migrations"} <= tables

    applied = [
        row["version"]
        for row in connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    ]
    assert applied == [1]
    connection.close()


def test_applying_migrations_twice_is_idempotent(postgres_url: str) -> None:
    from infrastructure.persistence.postgres.migrate import apply_migrations

    connection = connect(postgres_url)
    assert apply_migrations(connection) == []
    applied = [
        row["version"]
        for row in connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    ]
    assert applied == [1]
    connection.close()


def test_connect_failure_raises_persistence_error() -> None:
    with pytest.raises(PersistenceError):
        connect("postgresql://nobody:nopass@127.0.0.1:1/does-not-exist")
