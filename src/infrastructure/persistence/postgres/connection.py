"""PostgreSQL connection factory — the only place psycopg is constructed."""

from __future__ import annotations

from typing import Any, cast

import psycopg
from psycopg.rows import dict_row

from domain.common.errors import PersistenceError


def connect(database_url: str) -> psycopg.Connection[dict[str, Any]]:
    """Open an autocommit connection with dict rows; failures surface as PersistenceError."""
    try:
        # psycopg's stubs type connect() as tuple-rowed and non-generic over
        # row_factory; at runtime dict_row makes every row a dict, which the
        # declared return type reflects.
        return cast(
            "psycopg.Connection[dict[str, Any]]",
            psycopg.connect(database_url, autocommit=True, row_factory=dict_row),
        )
    except psycopg.Error as error:
        raise PersistenceError(f"could not connect to the database: {error}") from error
