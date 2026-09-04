"""Versioned plain-SQL migration runner (spec §8) — no ORM, no alembic.

Usage:
    python -m infrastructure.persistence.postgres.migrate [--database-url URL]

Reads DATABASE_URL from the environment when --database-url is absent.
"""

from __future__ import annotations

import argparse
import os
import sys
from importlib import resources
from typing import Any

import psycopg

from domain.common.errors import PersistenceError
from infrastructure.persistence.postgres.connection import connect

MIGRATIONS_PACKAGE = "infrastructure.persistence.postgres.migrations"


def _load_migrations() -> list[tuple[int, str]]:
    """(version, sql) pairs parsed from ``NNN_name.sql`` files, sorted by version."""
    migrations: list[tuple[int, str]] = []
    for entry in resources.files(MIGRATIONS_PACKAGE).iterdir():
        name = entry.name
        if not name.endswith(".sql"):
            continue
        version = int(name.split("_", 1)[0])
        migrations.append((version, entry.read_text(encoding="utf-8")))
    return sorted(migrations, key=lambda pair: pair[0])


def apply_migrations(connection: psycopg.Connection[dict[str, Any]]) -> list[int]:
    """Apply pending migrations in order; each runs in its own transaction."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    applied_rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    applied = {row["version"] for row in applied_rows}

    applied_now: list[int] = []
    for version, sql in _load_migrations():
        if version in applied:
            continue
        try:
            with connection.transaction():
                connection.execute(sql)
                connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
                )
        except psycopg.Error as error:
            raise PersistenceError(f"migration {version} failed: {error}") from error
        applied_now.append(version)
    return applied_now


def run_migrations(database_url: str) -> list[int]:
    with connect(database_url) as connection:
        return apply_migrations(connection)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="conclave-migrate")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL URL (defaults to $DATABASE_URL)",
    )
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("DATABASE_URL is not set and --database-url was not given")
    try:
        applied = run_migrations(args.database_url)
    except PersistenceError as error:
        print(f"migration error: {error}", file=sys.stderr)
        return 1
    print("applied migrations:", applied or "(none pending)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
