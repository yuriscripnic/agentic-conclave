# tests/conftest.py
"""Shared fixtures — real PostgreSQL via pgserver (spec §10).

pgserver is an optional dev dependency: tests requiring it skip cleanly with a
clear reason when it is not installed. One server is created per test run
(unix-socket based, no port conflicts); the schema is applied once per session
by the migrations runner under test.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest


@pytest.fixture(scope="session")
def postgres_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    pgserver = pytest.importorskip("pgserver", reason="pgserver not installed")
    data_dir = tmp_path_factory.mktemp("pgserver-data")
    server = pgserver.get_server(str(data_dir))
    try:
        yield server
    finally:
        try:
            server.cleanup()
        except Exception:  # noqa: BLE001 - teardown is best-effort
            pass


@pytest.fixture(scope="session")
def postgres_url(postgres_server: Any) -> str:
    """Connection URL for the session server, with the schema applied."""
    from infrastructure.persistence.postgres.connection import connect
    from infrastructure.persistence.postgres.migrate import apply_migrations

    url = postgres_server.get_uri()
    apply_migrations(connect(url))
    return url
