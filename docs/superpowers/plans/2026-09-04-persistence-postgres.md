# PostgreSQL Persistence (Plan 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the in-memory repositories with PostgreSQL implementations behind the existing application ports — atomic saves of game state + events, optimistic locking via `game.version`, plain-SQL migrations, and a `--db {memory,postgres}` CLI flag — per spec `docs/superpowers/specs/2026-09-04-persistence-design.md`.

**Architecture:** Aggregate-document persistence: the `Game` aggregate serializes to one JSONB `state` document; events are first-class rows in an append-only `game_events` table. The write unit is `GameRepository.save(game, pending_events)` — a single transaction doing an optimistic-lock upsert (`WHERE games.version = expected`) plus event inserts, raising `ConcurrentGameModification` on a version conflict. Mapping rebuilds domain objects through their validating constructors so corrupt stored state fails loudly. Combat/RNG/collector state intentionally stays in `GameService` memory (spec decision D1): no event rehydration in this plan.

**Tech Stack:** Python 3.12, `psycopg` 3 (runtime driver, main deps), `pgserver` (embedded test/dev PostgreSQL with pgvector bundled, dev extras), plain SQL migration files with a small runner, pytest fixtures sharing one session-scoped pgserver instance, `uv` as the package manager.

**Spec:** `docs/superpowers/specs/2026-09-04-persistence-design.md` — the plan argues from the spec; executors read both. On conflict: CLAUDE.md → spec → tests → code.

## Global Constraints

These apply to **every task**:

- Python `>=3.12`; the domain layer (`src/domain/`) imports nothing from application/ai/infrastructure/interfaces and no third-party library (CLAUDE.md §4, §5). New domain code in Task 1 is stdlib-only.
- New dependencies are exactly: `psycopg[binary]>=3.2` (main) and `pgserver>=0.1.4` (dev). Nothing else — no ORM, no alembic, no pooling, no dotenv (CLAUDE.md §55, spec §9).
- Package management is `uv` (the venv has no pip). Install dependency changes with:
  `uv pip install --python .venv/bin/python -e ".[dev]"`
- All state mutation flows through explicit domain methods; the repository stamps `game.version` only after a committed save (CLAUDE.md §62, spec §3).
- Expected domain failures raise the explicit errors from CLAUDE.md §49 — never bare `Exception`. Driver errors never cross the infrastructure boundary: psycopg exceptions are wrapped as `PersistenceError` with `from error` chaining (spec §3, §7).
- Events are immutable: no code path issues UPDATE or DELETE against `game_events` (spec §5).
- SQL parameters hitting `uuid`/`timestamptz` columns always use explicit `::uuid` / `::timestamptz` casts (mapping produces plain strings; psycopg3 sends strings as text, which PostgreSQL will not implicitly cast to uuid).
- psycopg connections are opened with `row_factory=dict_row` (named-column access everywhere) and `autocommit=True`, so each `save` runs inside its own explicit `connection.transaction()` block.
- Tests never require a network: pgserver runs a local server over Unix sockets. pgserver tests skip cleanly (importorskip inside the fixture) when pgserver is not installed. mypy only checks `src/` (`files = ["src"]` in pyproject), but all `src/` code is strict-typed.
- The venv does not persist between shells; full-suite verification is always:
  `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
- Conventional commits scoped by architectural layer, each ending with the trailer `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
- Ruff line-length 100, rules `E,F,I,UP,B`.

---

### Task 1: Domain Groundwork — Persistence Errors & `Game.version`

**Files:**
- Modify: `src/domain/common/errors.py` (append after `AgentDecisionFailedError`, line 45)
- Modify: `src/domain/world/game.py` (add `version` field to the `Game` dataclass)
- Test: `tests/domain/test_errors.py` (extend), `tests/domain/test_game.py` (extend)

**Interfaces:**
- Consumes: existing `DomainError` base (`src/domain/common/errors.py`), existing `Game` dataclass (`src/domain/world/game.py`).
- Produces (later tasks rely on these exact names):
  - `ConcurrentGameModification(DomainError)` — raised when a save loses the version race (spec §3).
  - `PersistenceError(DomainError)` — raised at the infrastructure boundary for storage failures, chained from the driver error (spec §3).
  - `Game.version: int = 0` — new field with default; persistence metadata only, domain rules never read it. The default keeps every existing constructor valid.

- [ ] **Step 1: Write the failing tests**

Append to the end of `tests/domain/test_errors.py` (the file already imports `DomainError`):

```python
def test_persistence_errors_inherit_from_domain_error() -> None:
    from domain.common.errors import ConcurrentGameModification, PersistenceError

    assert issubclass(ConcurrentGameModification, DomainError)
    assert issubclass(PersistenceError, DomainError)
```

Append to the end of `tests/domain/test_game.py` (the file already has the `_game()` helper):

```python
def test_game_version_defaults_to_zero_and_is_persistence_metadata() -> None:
    game = _game()
    assert game.version == 0
    # Persistence metadata: stamped by the repository, never read by rules.
    game.version = 3
    assert game.version == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_errors.py tests/domain/test_game.py -v`
Expected: FAIL — `ImportError: cannot import name 'ConcurrentGameModification'` (and the version test fails with `AttributeError: 'Game' object has no attribute 'version'`).

- [ ] **Step 3: Write the implementation**

In `src/domain/common/errors.py`, append after `AgentDecisionFailedError` (line 45):

```python
class ConcurrentGameModification(DomainError):
    """A save lost the optimistic-lock race: the game was modified elsewhere."""


class PersistenceError(DomainError):
    """A storage failure occurred below the repository boundary."""
```

In `src/domain/world/game.py`, extend the `Game` dataclass — add the field after `status` (line 28):

```python
    status: GameStatus = GameStatus.CREATED
    # Persistence metadata: stamped (+1) by the repository after each committed
    # save; the optimistic-lock token for atomic writes. Domain rules never read it.
    version: int = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_errors.py tests/domain/test_game.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests PASS (nothing constructs `Game` positionally past `status`).

- [ ] **Step 6: Commit**

```bash
git add src/domain/common/errors.py src/domain/world/game.py tests/domain/test_errors.py tests/domain/test_game.py
git commit -m "feat(domain): add persistence error types and game version metadata" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: Port Contracts & Atomic In-Memory Save

**Files:**
- Modify: `src/application/ports.py` (replace whole file)
- Modify: `src/domain/events/repository.py` (replace whole file)
- Modify: `src/infrastructure/persistence/in_memory.py` (replace whole file)
- Modify: `src/application/game_service.py:82-87` (`_persist` method only)
- Modify: `tests/application/test_game_service.py` (`_service` helper)
- Modify: `tests/integration/test_mvp0_combat_sandbox.py:19-20` (`_service` helper)
- Test: `tests/infrastructure/test_in_memory_save.py` (new)

**Interfaces:**
- Consumes: `EventEnvelope` (`domain.events.collector`), `Game`/`GameId`, `GameNotFoundError`, `InMemoryEventRepository.append` (stays as an implementation detail).
- Produces (later tasks implement these exact contracts):
  - `GameRepository.save(game: Game, pending_events: Sequence[EventEnvelope]) -> None` — the atomic unit: persists the aggregate AND appends pending events; stamps `game.version += 1` on success; `pending_events` may be empty.
  - `GameRepository.get(game_id: GameId) -> Game` — unchanged, raises `GameNotFoundError`.
  - `EventRepository` Protocol reduced to `get_events(game_id: GameId) -> list[EventEnvelope]` — `append` removed from the Protocol (the write path is now `GameRepository.save`).
  - `InMemoryGameRepository(event_store: InMemoryEventRepository)` — shares the event store so one `save` writes both stores.
  - `GameService._persist` becomes: drain collector → `self._games.save(game, drained)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/infrastructure/test_in_memory_save.py
"""In-memory repositories implement the same save contract as PostgreSQL (spec §10)."""

from domain.common.ids import CampaignId, GameId
from domain.events.collector import EventCollector
from domain.events.events import GameCreated
from domain.world.game import Game
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository


def _game() -> Game:
    return Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="Ruins",
        seed=42,
    )


def test_save_stamps_version_and_persists_events() -> None:
    event_store = InMemoryEventRepository()
    repository = InMemoryGameRepository(event_store)
    game = _game()
    collector = EventCollector(game_id=game.game_id)
    collector.record(GameCreated(campaign_id=game.campaign_id, seed=42))
    pending = collector.drain()

    repository.save(game, pending)

    assert game.version == 1
    assert repository.get(game.game_id) is game
    assert [e.event_type for e in event_store.get_events(game.game_id)] == [
        "game_created"
    ]


def test_save_with_empty_pending_events_is_normal() -> None:
    event_store = InMemoryEventRepository()
    repository = InMemoryGameRepository(event_store)
    game = _game()

    repository.save(game, [])

    assert repository.get(game.game_id) is game
    assert game.version == 1
    assert event_store.get_events(game.game_id) == []


def test_version_increments_across_saves() -> None:
    event_store = InMemoryEventRepository()
    repository = InMemoryGameRepository(event_store)
    game = _game()

    repository.save(game, [])
    repository.save(game, [])

    assert game.version == 2
```

Also update the two existing `_service()` helpers to the shared-store wiring. In `tests/application/test_game_service.py`, find the helper that currently reads:

```python
def _service() -> GameService:
    return GameService(InMemoryGameRepository(), InMemoryEventRepository())
```

and replace it with (that file's imports already include `InMemoryEventRepository` and `InMemoryGameRepository`):

```python
def _service() -> GameService:
    event_store = InMemoryEventRepository()
    return GameService(InMemoryGameRepository(event_store), event_store)
```

Make the identical replacement to `_service` in `tests/integration/test_mvp0_combat_sandbox.py` (lines 19-20; the same imports are already present at lines 15-16).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_in_memory_save.py -v`
Expected: FAIL — `TypeError: InMemoryGameRepository() takes no arguments` (the constructor change is not made yet).

- [ ] **Step 3: Write the implementation**

Replace `src/application/ports.py` entirely with:

```python
"""Repository ports — implemented by infrastructure (CLAUDE.md §36)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from domain.common.ids import GameId
from domain.events.collector import EventEnvelope
from domain.world.game import Game


class GameRepository(Protocol):
    def save(self, game: Game, pending_events: Sequence[EventEnvelope]) -> None:
        """Atomically persist the aggregate and append pending events.

        Single transaction (spec §7): optimistic-lock the row on game.version,
        insert pending events, commit; on success stamp game.version += 1.
        A version conflict raises ConcurrentGameModification and persists nothing.
        pending_events may be empty (e.g. add_character persists with no events).
        """

    def get(self, game_id: GameId) -> Game: ...
```

Replace `src/domain/events/repository.py` entirely with:

```python
"""Port for event persistence — implemented in the infrastructure layer.

The write path is GameRepository.save (events travel with the aggregate so
they commit atomically); this protocol is read-only.
"""

from __future__ import annotations

from typing import Protocol

from domain.common.ids import GameId
from domain.events.collector import EventEnvelope


class EventRepository(Protocol):
    def get_events(self, game_id: GameId) -> list[EventEnvelope]: ...
```

Replace `src/infrastructure/persistence/in_memory.py` entirely with:

```python
"""In-memory GameRepository — same save contract as the PostgreSQL implementation."""

from __future__ import annotations

from collections.abc import Sequence

from domain.common.errors import GameNotFoundError
from domain.common.ids import GameId
from domain.events.collector import EventEnvelope
from domain.world.game import Game
from infrastructure.events.in_memory import InMemoryEventRepository


class InMemoryGameRepository:
    def __init__(self, event_store: InMemoryEventRepository) -> None:
        self._event_store = event_store
        self._games: dict[GameId, Game] = {}

    def save(self, game: Game, pending_events: Sequence[EventEnvelope]) -> None:
        # The store keeps the live aggregate object (MVP-0 semantics), so a
        # version conflict is impossible here; conflict semantics are covered
        # by the PostgreSQL tests. Version stamping matches the SQL contract.
        self._games[game.game_id] = game
        for envelope in pending_events:
            self._event_store.append(game.game_id, envelope)
        game.version += 1

    def get(self, game_id: GameId) -> Game:
        game = self._games.get(game_id)
        if game is None:
            raise GameNotFoundError(f"no game with id '{game_id}'")
        return game
```

`src/infrastructure/events/in_memory.py` is unchanged — its `append` method remains and the class still satisfies the reduced `EventRepository` protocol.

In `src/application/game_service.py`, replace the `_persist` method (lines 82-87) with:

```python
    def _persist(self, game: Game) -> list[EventEnvelope]:
        drained = self._collector(game).drain()
        self._games.save(game, drained)
        return drained
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests PASS — the existing suite plus the new file (removing `append` from the `EventRepository` Protocol affects only `game_service._persist`, already rewritten; `tests/infrastructure/test_event_repository.py` tests the concrete `InMemoryEventRepository`, whose `append` method stays).

- [ ] **Step 5: Run lint and typecheck**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/application/ports.py src/domain/events/repository.py src/infrastructure/persistence/in_memory.py src/application/game_service.py tests/infrastructure/test_in_memory_save.py tests/application/test_game_service.py tests/integration/test_mvp0_combat_sandbox.py
git commit -m "feat(application): make repository save atomic over game state and events" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: PostgreSQL Dependencies, Connection & Migrations

**Files:**
- Modify: `pyproject.toml` (dependencies + dev extras + package data)
- Create: `src/infrastructure/persistence/postgres/__init__.py` (empty)
- Create: `src/infrastructure/persistence/postgres/connection.py`
- Create: `src/infrastructure/persistence/postgres/migrations/__init__.py` (empty)
- Create: `src/infrastructure/persistence/postgres/migrations/001_init.sql`
- Create: `src/infrastructure/persistence/postgres/migrate.py`
- Create: `tests/conftest.py`
- Test: `tests/infrastructure/test_postgres_migrations.py`

**Interfaces:**
- Consumes: `PersistenceError` (Task 1), psycopg 3, `pgserver` (tests only).
- Spec refinement (§7): the spec says "one psycopg connection owned by a small `PostgresConnection` wrapper"; implemented as the `connect()` factory function below — same semantics (one connection, owned in one place, shared by both repositories, each `save` uses `connection.transaction()`, no pooling) with less ceremony.
- Produces (later tasks rely on these exact names):
  - `connect(database_url: str) -> psycopg.Connection` — autocommit connection with `row_factory=dict_row`; wraps `psycopg.Error` in `PersistenceError`.
  - `apply_migrations(connection: psycopg.Connection) -> list[int]` — applies pending `migrations/*.sql` in version order, records versions in `schema_migrations`, returns versions applied this call; idempotent.
  - `run_migrations(database_url: str) -> list[int]` — convenience used by the CLI (`build_service` in Task 6).
  - `python -m infrastructure.persistence.postgres.migrate [--database-url URL]` — CLI entry; falls back to the `DATABASE_URL` env var.
  - Schema tables: `games`, `game_events`, `schema_migrations` (columns per Step 5).
  - Test fixtures in `tests/conftest.py`: `postgres_server` (session-scoped pgserver instance) and `postgres_url` (its connection URL, schema applied once per session).

- [ ] **Step 1: Add the dependencies**

In `pyproject.toml`, change the `dependencies` list and the `dev` extras:

```toml
dependencies = [
    "rich>=13.7",
    "psycopg[binary]>=3.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "ruff>=0.6",
    "mypy>=1.11",
    "pgserver>=0.1.4",
]
```

and after the `[tool.setuptools.packages.find]` section add:

```toml
[tool.setuptools.package-data]
"infrastructure.persistence.postgres.migrations" = ["*.sql"]
```

Then install and verify the imports resolve:

```bash
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -c "import psycopg; print(psycopg.__version__)"
.venv/bin/python -c "import pgserver; print(pgserver.__version__)"
```

Expected: both print versions (psycopg 3.x, pgserver 0.1.x). If pgserver fails to import on this platform, STOP and ask — the fallback is apt `postgresql` + an unprivileged temp cluster with the same fixture shape (spec §10).

- [ ] **Step 2: Verify the pgserver API surface (drift check)**

```bash
.venv/bin/python - <<'EOF'
import inspect

import psycopg
import pgserver

print("get_server:", inspect.signature(pgserver.get_server))
server = pgserver.get_server("/tmp/conclave-pgcheck")
print("server type:", type(server).__name__)
print("has get_uri:", hasattr(server, "get_uri"))
print("uri sample:", str(server.get_uri())[:40], "...")
with psycopg.connect(server.get_uri()) as connection:
    print("pg version:", connection.execute("SELECT version()").fetchone()[0])
EOF
```

Expected: `get_server` exists, the server object exposes `get_uri()`, and the printed
`server version` shows PostgreSQL 13 or newer (spec §10). If the installed version's
API differs from `get_server`/`get_uri`, consult `help(pgserver)` and adjust the
fixture in Step 5 accordingly before proceeding.

- [ ] **Step 3: Write the failing tests**

```python
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
```

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_postgres_migrations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'infrastructure.persistence.postgres'`

- [ ] **Step 5: Write the connection, schema, and migration runner**

Create the package structure:

```bash
mkdir -p src/infrastructure/persistence/postgres/migrations
touch src/infrastructure/persistence/postgres/__init__.py
touch src/infrastructure/persistence/postgres/migrations/__init__.py
```

`src/infrastructure/persistence/postgres/connection.py`:

```python
"""PostgreSQL connection factory — the only place psycopg is constructed."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from domain.common.errors import PersistenceError


def connect(database_url: str) -> psycopg.Connection:
    """Open an autocommit connection with dict rows; failures surface as PersistenceError."""
    try:
        return psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
    except psycopg.Error as error:
        raise PersistenceError(f"could not connect to the database: {error}") from error
```

`src/infrastructure/persistence/postgres/migrations/001_init.sql`:

```sql
-- 001_init.sql — initial schema for the persistence plan (spec §5).
CREATE TABLE games (
    id            UUID PRIMARY KEY,
    campaign_id   UUID NOT NULL,
    campaign_name TEXT NOT NULL,
    seed          BIGINT NOT NULL,
    version       INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL,
    state         JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE game_events (
    game_id     UUID NOT NULL REFERENCES games(id),
    sequence    INTEGER NOT NULL,
    event_id    UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type  TEXT NOT NULL,
    payload     JSONB NOT NULL,
    PRIMARY KEY (game_id, sequence)
);

-- Append-only by construction: no code path issues UPDATE or DELETE here.
```

`src/infrastructure/persistence/postgres/migrate.py`:

```python
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


def apply_migrations(connection: psycopg.Connection) -> list[int]:
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_postgres_migrations.py -v`
Expected: PASS (3 tests; the first run initializes the pgserver data dir, which takes a few seconds).

- [ ] **Step 7: Run the full suite, lint, and typecheck**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: all PASS, no lint/type errors.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/infrastructure/persistence/postgres tests/conftest.py tests/infrastructure/test_postgres_migrations.py
git commit -m "feat(infrastructure): add postgres connection, migrations runner and initial schema" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: Aggregate Mapping — `Game` ↔ Row, Envelope ↔ Row

**Files:**
- Create: `src/infrastructure/persistence/postgres/mapping.py`
- Test: `tests/infrastructure/test_postgres_mapping.py`

**Interfaces:**
- Consumes: domain types (`Game`, `GameStatus`, `Character`, `CharacterType`, `CharacterClass`, `AbilityScores`, `AbilityType`, `HitPoints`, `Inventory`, `Item`, `Weapon`), `EventEnvelope`, typed ids, `ValidationError` (Task 1).
- Produces (Task 5 relies on these exact signatures):
  - `game_to_row(game: Game) -> dict[str, object]` — column values: `id`, `campaign_id`, `campaign_name`, `seed`, `version`, `status`, `state` (JSONB document: characters, party_ids, enemy_ids, status).
  - `game_from_row(row: Mapping[str, object]) -> Game` — rebuilds through domain constructors; shape problems raise `ValidationError("corrupt persisted state: ...")`. Accepts both `str` and `uuid.UUID` for id-shaped values (psycopg returns `uuid.UUID` for uuid columns).
  - `event_to_row(game_id: GameId, envelope: EventEnvelope) -> dict[str, object]` — columns `game_id, sequence, event_id, occurred_at, event_type, payload`.
  - `row_to_event(row: Mapping[str, object], game_id: GameId) -> EventEnvelope` — converts a timestamptz `datetime` back to the domain's ISO string.

- [ ] **Step 1: Write the failing tests**

```python
# tests/infrastructure/test_postgres_mapping.py
"""Aggregate ↔ row mapping roundtrips through domain constructors (spec §6)."""

import uuid

import pytest

from domain.character.abilities import AbilityScores
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.inventory import Inventory
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.common.errors import ValidationError
from domain.common.ids import CampaignId, CharacterId, EventId, GameId
from domain.events.collector import EventEnvelope
from domain.world.game import Game, GameStatus
from infrastructure.persistence.postgres.mapping import (
    event_to_row,
    game_from_row,
    game_to_row,
    row_to_event,
)


def _weapon() -> Weapon:
    return Weapon(
        weapon_id="longsword",
        name="Longsword",
        damage_die_count=1,
        damage_die_size=8,
    )


def _character(
    name: str,
    character_type: CharacterType,
    hp: int = 12,
) -> Character:
    return Character(
        id=CharacterId.generate(),
        name=name,
        character_type=character_type,
        character_class=(
            CharacterClass.FIGHTER
            if character_type is CharacterType.PLAYER_CHARACTER
            else None
        ),
        level=1,
        ability_scores=AbilityScores(
            strength=16,
            dexterity=13,
            constitution=15,
            intelligence=10,
            wisdom=12,
            charisma=9,
        ),
        armor_class=16,
        speed_ft=30,
        hit_points=HitPoints(current=hp, maximum=hp),
        conditions=("prone",),
        inventory=Inventory(gold=25),
        equipped_weapon=_weapon()
        if character_type is CharacterType.PLAYER_CHARACTER
        else None,
    )


def _full_game() -> Game:
    game = Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="The Forgotten Ruins",
        seed=42,
    )
    game.add_party_member(_character("Arin", CharacterType.PLAYER_CHARACTER, hp=12))
    game.add_enemy(_character("Goblin", CharacterType.MONSTER, hp=7))
    game.get_character(game.enemy_ids[0]).apply_damage(7)  # hp clamps to 0: defeated
    game.mark_started()
    game.version = 2  # simulate an aggregate that has already been saved twice
    return game


def test_game_roundtrip_preserves_every_field() -> None:
    game = _full_game()
    row = game_to_row(game)

    assert row["id"] == str(game.game_id)
    assert row["campaign_id"] == str(game.campaign_id)
    assert row["seed"] == 42
    assert row["version"] == 2
    assert row["status"] == "running"

    rebuilt = game_from_row(row)
    assert rebuilt.game_id == game.game_id
    assert rebuilt.campaign_id == game.campaign_id
    assert rebuilt.campaign_name == game.campaign_name
    assert rebuilt.seed == game.seed
    assert rebuilt.status is GameStatus.RUNNING
    assert rebuilt.version == 2
    assert rebuilt.party_ids == game.party_ids
    assert rebuilt.enemy_ids == game.enemy_ids

    for original in game.characters.values():
        clone = rebuilt.characters[original.id]
        assert clone.name == original.name
        assert clone.character_type is original.character_type
        assert clone.character_class is original.character_class
        assert clone.ability_scores == original.ability_scores
        assert clone.hit_points == original.hit_points
        assert clone.conditions == original.conditions
        assert clone.inventory == original.inventory
        assert clone.equipped_weapon == original.equipped_weapon
        assert clone.is_defeated() == original.is_defeated()


def test_row_document_holds_characters_and_sides() -> None:
    game = _full_game()
    document = game_to_row(game)["state"]
    assert isinstance(document, dict)
    assert len(document["characters"]) == 2
    assert document["party_ids"] == [str(cid) for cid in game.party_ids]
    assert document["enemy_ids"] == [str(cid) for cid in game.enemy_ids]
    assert document["characters"][0]["equipped_weapon"]["weapon_id"] == "longsword"
    assert document["characters"][0]["inventory"]["gold"] == 25
    assert document["status"] == "running"


def test_roundtrip_from_uuid_row_values() -> None:
    """psycopg returns uuid.UUID for uuid columns; the mapping must accept them."""
    game = _full_game()
    row = game_to_row(game)
    row["id"] = uuid.UUID(str(row["id"]))
    row["campaign_id"] = uuid.UUID(str(row["campaign_id"]))

    rebuilt = game_from_row(row)
    assert rebuilt.game_id == game.game_id


def test_corrupt_row_raises_validation_error() -> None:
    game = _full_game()

    tampered = game_to_row(game)
    tampered["state"]["characters"][0]["hit_points"]["maximum"] = 0  # domain-invalid
    with pytest.raises(ValidationError, match="corrupt persisted state"):
        game_from_row(tampered)

    missing = game_to_row(game)
    del missing["state"]["characters"][0]["name"]
    with pytest.raises(ValidationError, match="corrupt persisted state"):
        game_from_row(missing)


def test_event_envelope_roundtrip() -> None:
    game_id = GameId.generate()
    envelope = EventEnvelope(
        sequence=7,
        event_id=EventId.generate(),
        game_id=game_id,
        occurred_at="2026-01-01T00:00:00+00:00",
        event_type="attack_resolved",
        payload={"attacker_id": "a", "hit": True, "amount": 4},
    )
    row = event_to_row(game_id, envelope)
    assert row["game_id"] == str(game_id)
    assert row["sequence"] == 7
    assert row["event_type"] == "attack_resolved"
    assert row["payload"] == {"attacker_id": "a", "hit": True, "amount": 4}

    rebuilt = row_to_event(row, game_id)
    assert rebuilt == envelope
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_postgres_mapping.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'infrastructure.persistence.postgres.mapping'`

- [ ] **Step 3: Write the implementation**

```python
# src/infrastructure/persistence/postgres/mapping.py
"""Game ↔ row and EventEnvelope ↔ row mapping (spec §6).

Serialization is explicit (no blind asdict): ids become strings, enums their
values. Rebuilding goes through the domain constructors so invalid stored
state fails loudly on load instead of silently propagating. Rows read from
PostgreSQL carry uuid.UUID / datetime values; hand-built dicts carry strings —
both are accepted.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime

from domain.character.abilities import AbilityScores, AbilityType
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.inventory import Inventory, Item
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.common.errors import ValidationError
from domain.common.ids import CampaignId, CharacterId, EventId, GameId
from domain.events.collector import EventEnvelope
from domain.world.game import Game, GameStatus


def _require(document: Mapping[str, object], key: str) -> object:
    if key not in document:
        raise ValidationError(f"corrupt persisted state: missing key '{key}'")
    return document[key]


def _as_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"corrupt persisted state: {label} must be an integer")
    return value


def _as_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"corrupt persisted state: {label} must be a string")
    return value


def _as_id(value: object, label: str) -> str:
    if isinstance(value, uuid.UUID):
        return str(value)
    return _as_str(value, label)


def _require_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValidationError(f"corrupt persisted state: {label} must be an object")
    return value


def _require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValidationError(f"corrupt persisted state: {label} must be a list")
    return value


# -- serialization (domain -> row values) ------------------------------------


def _ability_scores_document(scores: AbilityScores) -> dict[str, int]:
    return {
        "strength": scores.strength,
        "dexterity": scores.dexterity,
        "constitution": scores.constitution,
        "intelligence": scores.intelligence,
        "wisdom": scores.wisdom,
        "charisma": scores.charisma,
    }


def _inventory_document(inventory: Inventory) -> dict[str, object]:
    return {
        "gold": inventory.gold,
        "items": {
            item.item_id: {"name": item.name, "quantity": item.quantity}
            for item in inventory.items.values()
        },
    }


def _weapon_document(weapon: Weapon) -> dict[str, object]:
    return {
        "weapon_id": weapon.weapon_id,
        "name": weapon.name,
        "damage_die_count": weapon.damage_die_count,
        "damage_die_size": weapon.damage_die_size,
        "ability": weapon.ability.value,
        "range_ft": weapon.range_ft,
    }


def _character_document(character: Character) -> dict[str, object]:
    return {
        "id": str(character.id),
        "name": character.name,
        "character_type": character.character_type.value,
        "character_class": (
            character.character_class.value if character.character_class else None
        ),
        "level": character.level,
        "ability_scores": _ability_scores_document(character.ability_scores),
        "armor_class": character.armor_class,
        "speed_ft": character.speed_ft,
        "hit_points": {
            "current": character.hit_points.current,
            "maximum": character.hit_points.maximum,
        },
        "conditions": list(character.conditions),
        "inventory": _inventory_document(character.inventory),
        "equipped_weapon": (
            None if character.equipped_weapon is None
            else _weapon_document(character.equipped_weapon)
        ),
    }


def game_to_row(game: Game) -> dict[str, object]:
    """Serialize the aggregate to games-table column values (state = JSONB doc)."""
    return {
        "id": str(game.game_id),
        "campaign_id": str(game.campaign_id),
        "campaign_name": game.campaign_name,
        "seed": game.seed,
        "version": game.version,
        "status": game.status.value,
        "state": {
            "characters": [
                _character_document(character)
                for character in game.characters.values()
            ],
            "party_ids": [str(character_id) for character_id in game.party_ids],
            "enemy_ids": [str(character_id) for character_id in game.enemy_ids],
            "status": game.status.value,
        },
    }


# -- deserialization (row values -> domain) -----------------------------------


def _hit_points_from(document: Mapping[str, object]) -> HitPoints:
    return HitPoints(
        current=_as_int(_require(document, "current"), "hit_points.current"),
        maximum=_as_int(_require(document, "maximum"), "hit_points.maximum"),
    )


def _ability_scores_from(document: Mapping[str, object]) -> AbilityScores:
    return AbilityScores(
        strength=_as_int(_require(document, "strength"), "ability.strength"),
        dexterity=_as_int(_require(document, "dexterity"), "ability.dexterity"),
        constitution=_as_int(
            _require(document, "constitution"), "ability.constitution"
        ),
        intelligence=_as_int(
            _require(document, "intelligence"), "ability.intelligence"
        ),
        wisdom=_as_int(_require(document, "wisdom"), "ability.wisdom"),
        charisma=_as_int(_require(document, "charisma"), "ability.charisma"),
    )


def _inventory_from(document: Mapping[str, object]) -> Inventory:
    items_document = _require_dict(_require(document, "items"), "inventory.items")
    items: dict[str, Item] = {}
    for item_id, entry in items_document.items():
        item_document = _require_dict(entry, f"inventory.items[{item_id}]")
        items[item_id] = Item(
            item_id=item_id,
            name=_as_str(_require(item_document, "name"), "item.name"),
            quantity=_as_int(_require(item_document, "quantity"), "item.quantity"),
        )
    return Inventory(
        items=items, gold=_as_int(_require(document, "gold"), "inventory.gold")
    )


def _weapon_from(document: Mapping[str, object]) -> Weapon:
    ability_value = _as_str(_require(document, "ability"), "weapon.ability")
    try:
        ability = AbilityType(ability_value)
    except ValueError as error:
        raise ValidationError(
            f"corrupt persisted state: unknown ability '{ability_value}'"
        ) from error
    return Weapon(
        weapon_id=_as_str(_require(document, "weapon_id"), "weapon.weapon_id"),
        name=_as_str(_require(document, "name"), "weapon.name"),
        damage_die_count=_as_int(
            _require(document, "damage_die_count"), "weapon.die_count"
        ),
        damage_die_size=_as_int(
            _require(document, "damage_die_size"), "weapon.die_size"
        ),
        ability=ability,
        range_ft=_as_int(_require(document, "range_ft"), "weapon.range_ft"),
    )


def _character_from(document: Mapping[str, object]) -> Character:
    class_value = _require(document, "character_class")
    try:
        character_type = CharacterType(
            _as_str(_require(document, "character_type"), "character.character_type")
        )
        character_class = (
            None
            if class_value is None
            else CharacterClass(_as_str(class_value, "character.character_class"))
        )
    except ValueError as error:
        raise ValidationError(
            f"corrupt persisted state: unknown character enum value: {error}"
        ) from error
    conditions = [
        _as_str(condition, "character.condition")
        for condition in _require_list(
            _require(document, "conditions"), "character.conditions"
        )
    ]
    weapon_value = _require(document, "equipped_weapon")
    return Character(
        id=CharacterId(_as_id(_require(document, "id"), "character.id")),
        name=_as_str(_require(document, "name"), "character.name"),
        character_type=character_type,
        character_class=character_class,
        level=_as_int(_require(document, "level"), "character.level"),
        ability_scores=_ability_scores_from(
            _require_dict(
                _require(document, "ability_scores"), "character.ability_scores"
            )
        ),
        armor_class=_as_int(_require(document, "armor_class"), "character.armor_class"),
        speed_ft=_as_int(_require(document, "speed_ft"), "character.speed_ft"),
        hit_points=_hit_points_from(
            _require_dict(_require(document, "hit_points"), "character.hit_points")
        ),
        conditions=tuple(conditions),
        inventory=_inventory_from(
            _require_dict(_require(document, "inventory"), "character.inventory")
        ),
        equipped_weapon=(
            None
            if weapon_value is None
            else _weapon_from(_require_dict(weapon_value, "character.equipped_weapon"))
        ),
    )


def game_from_row(row: Mapping[str, object]) -> Game:
    """Rebuild the aggregate from column values; ValidationError on any corruption."""
    try:
        status = GameStatus(_as_str(_require(row, "status"), "game.status"))
    except ValueError as error:
        raise ValidationError(f"corrupt persisted state: {error}") from error
    state = _require_dict(_require(row, "state"), "game.state")

    characters: dict[CharacterId, Character] = {}
    for entry in _require_list(_require(state, "characters"), "game.state.characters"):
        character = _character_from(_require_dict(entry, "game.state.characters[]"))
        characters[character.id] = character

    game = Game(
        game_id=GameId(_as_id(_require(row, "id"), "game.id")),
        campaign_id=CampaignId(
            _as_id(_require(row, "campaign_id"), "game.campaign_id")
        ),
        campaign_name=_as_str(_require(row, "campaign_name"), "game.campaign_name"),
        seed=_as_int(_require(row, "seed"), "game.seed"),
        characters=characters,
        party_ids=[
            CharacterId(_as_id(value, "game.party_ids[]"))
            for value in _require_list(_require(state, "party_ids"), "game.party_ids")
        ],
        enemy_ids=[
            CharacterId(_as_id(value, "game.enemy_ids[]"))
            for value in _require_list(_require(state, "enemy_ids"), "game.enemy_ids")
        ],
        status=status,
    )
    game.version = _as_int(_require(row, "version"), "game.version")
    return game


def event_to_row(game_id: GameId, envelope: EventEnvelope) -> dict[str, object]:
    return {
        "game_id": str(game_id),
        "sequence": envelope.sequence,
        "event_id": str(envelope.event_id),
        "occurred_at": envelope.occurred_at,
        "event_type": envelope.event_type,
        "payload": envelope.payload,
    }


def row_to_event(row: Mapping[str, object], game_id: GameId) -> EventEnvelope:
    """Rebuild an envelope; DB rows carry datetime/UUID values, dicts carry strings."""
    occurred_at = _require(row, "occurred_at")
    return EventEnvelope(
        sequence=_as_int(_require(row, "sequence"), "event.sequence"),
        event_id=EventId(_as_id(_require(row, "event_id"), "event.event_id")),
        game_id=game_id,
        occurred_at=(
            occurred_at.isoformat()
            if isinstance(occurred_at, datetime)
            else _as_str(occurred_at, "event.occurred_at")
        ),
        event_type=_as_str(_require(row, "event_type"), "event.event_type"),
        payload=_require_dict(_require(row, "payload"), "event.payload"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_postgres_mapping.py -v`
Expected: PASS

- [ ] **Step 5: Run lint and typecheck**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/infrastructure/persistence/postgres/mapping.py tests/infrastructure/test_postgres_mapping.py
git commit -m "feat(infrastructure): add game aggregate and event envelope mapping" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: PostgreSQL Repositories — Atomic Save & Optimistic Locking

**Files:**
- Create: `src/infrastructure/persistence/postgres/repository.py`
- Test: `tests/infrastructure/test_postgres_repository.py`

**Interfaces:**
- Consumes: `connect` (Task 3), mapping functions (Task 4), `GameRepository`/`EventRepository` protocols (Task 2), `ConcurrentGameModification`, `GameNotFoundError`, `PersistenceError`, `Game.version` (Task 1), `EventEnvelope`.
- Produces (Task 6 relies on these exact names):
  - `class PostgresGameRepository`: `__init__(connection: psycopg.Connection)`; `save(game, pending_events) -> None` — one transaction performing an optimistic-lock upsert of the aggregate plus event inserts; stamps `game.version += 1` after commit; `get(game_id) -> Game` raises `GameNotFoundError`.
  - `class PostgresEventRepository`: `__init__(connection)`; `get_events(game_id) -> list[EventEnvelope]` ordered by sequence.
  - Both wrap `psycopg.Error` as `PersistenceError` with chaining.
  - Sequences are contiguous within one process lifetime per game (spec D1: no collector rehydration — a restarted process creates a new game).

- [ ] **Step 1: Write the failing tests**

```python
# tests/infrastructure/test_postgres_repository.py
"""Optimistic locking, atomic saves, and event integrity against real PostgreSQL."""

import copy

import pytest

from domain.character.abilities import AbilityScores
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.common.errors import (
    ConcurrentGameModification,
    GameNotFoundError,
    PersistenceError,
)
from domain.common.ids import CampaignId, CharacterId, EventId, GameId
from domain.events.collector import EventEnvelope
from domain.world.game import Game
from infrastructure.persistence.postgres.connection import connect
from infrastructure.persistence.postgres.repository import (
    PostgresEventRepository,
    PostgresGameRepository,
)


def _party_member() -> Character:
    return Character(
        id=CharacterId.generate(),
        name="Arin",
        character_type=CharacterType.PLAYER_CHARACTER,
        character_class=CharacterClass.FIGHTER,
        level=1,
        ability_scores=AbilityScores(
            strength=16,
            dexterity=13,
            constitution=15,
            intelligence=10,
            wisdom=12,
            charisma=9,
        ),
        armor_class=16,
        speed_ft=30,
        hit_points=HitPoints(current=12, maximum=12),
        equipped_weapon=Weapon(
            weapon_id="longsword", name="Longsword",
            damage_die_count=1, damage_die_size=8,
        ),
    )


def _game() -> Game:
    game = Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="Ruins",
        seed=42,
    )
    game.add_party_member(_party_member())
    return game


def _envelope(game_id: GameId, sequence: int, event_type: str) -> EventEnvelope:
    return EventEnvelope(
        sequence=sequence,
        event_id=EventId.generate(),
        game_id=game_id,
        occurred_at="2026-01-01T00:00:00+00:00",
        event_type=event_type,
        payload={"sequence": sequence},
    )


def test_save_and_get_roundtrip_full_aggregate(postgres_url: str) -> None:
    connection = connect(postgres_url)
    repository = PostgresGameRepository(connection)
    game = _game()
    game.mark_started()
    game.get_character(game.party_ids[0]).apply_damage(5)

    repository.save(game, [])
    loaded = repository.get(game.game_id)

    assert loaded.game_id == game.game_id
    assert loaded.status == game.status
    assert loaded.version == game.version
    original = game.get_character(game.party_ids[0])
    clone = loaded.get_character(loaded.party_ids[0])
    assert clone.name == original.name
    assert clone.hit_points == original.hit_points
    assert clone.equipped_weapon == original.equipped_weapon
    connection.close()


def test_save_stamps_version_incrementally(postgres_url: str) -> None:
    connection = connect(postgres_url)
    repository = PostgresGameRepository(connection)
    game = _game()

    assert game.version == 0
    repository.save(game, [])
    assert game.version == 1
    repository.save(game, [])
    assert game.version == 2
    assert repository.get(game.game_id).version == 2
    connection.close()


def test_stale_version_save_raises_and_persists_nothing(postgres_url: str) -> None:
    connection = connect(postgres_url)
    repository = PostgresGameRepository(connection)
    game = _game()
    repository.save(game, [])  # version -> 1

    stale = copy.deepcopy(game)
    stale.get_character(stale.party_ids[0]).apply_damage(9)
    stale.version = 0  # pretend this replica never saw the first save

    with pytest.raises(ConcurrentGameModification):
        repository.save(stale, [])

    loaded = repository.get(game.game_id)
    assert loaded.version == 1
    assert loaded.get_character(loaded.party_ids[0]).hit_points.current == 12
    connection.close()


def test_events_are_contiguous_across_saves(postgres_url: str) -> None:
    connection = connect(postgres_url)
    games = PostgresGameRepository(connection)
    events = PostgresEventRepository(connection)
    game = _game()
    game.mark_started()

    games.save(
        game,
        [
            _envelope(game.game_id, 1, "game_created"),
            _envelope(game.game_id, 2, "game_started"),
        ],
    )
    games.save(game, [_envelope(game.game_id, 3, "combat_started")])

    stored = events.get_events(game.game_id)
    assert [e.sequence for e in stored] == [1, 2, 3]
    assert [e.event_type for e in stored] == [
        "game_created",
        "game_started",
        "combat_started",
    ]
    assert all(e.game_id == game.game_id for e in stored)
    connection.close()


def test_duplicate_sequence_insert_is_rejected(postgres_url: str) -> None:
    connection = connect(postgres_url)
    games = PostgresGameRepository(connection)
    game = _game()
    games.save(game, [_envelope(game.game_id, 1, "game_created")])

    with pytest.raises(PersistenceError):
        games.save(game, [_envelope(game.game_id, 1, "game_started")])

    loaded = games.get(game.game_id)
    assert loaded.version == 1  # the failed save left the aggregate untouched
    connection.close()


def test_get_events_for_unknown_game_is_empty(postgres_url: str) -> None:
    connection = connect(postgres_url)
    events = PostgresEventRepository(connection)
    assert events.get_events(GameId.generate()) == []
    connection.close()


def test_get_unknown_game_raises_game_not_found(postgres_url: str) -> None:
    connection = connect(postgres_url)
    repository = PostgresGameRepository(connection)
    with pytest.raises(GameNotFoundError):
        repository.get(GameId.generate())
    connection.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_postgres_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'infrastructure.persistence.postgres.repository'`

- [ ] **Step 3: Write the implementation**

```python
# src/infrastructure/persistence/postgres/repository.py
"""PostgreSQL GameRepository + EventRepository (spec §7).

save() is the atomic unit: one transaction performs the optimistic-lock
upsert of the aggregate and the append of pending events. Events are
append-only; sequences are contiguous within one process lifetime per game
(spec D1: no collector rehydration — a restarted process creates a new game).
"""

from __future__ import annotations

from collections.abc import Sequence

import psycopg

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
    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def save(self, game: Game, pending_events: Sequence[EventEnvelope]) -> None:
        row = game_to_row(game)
        try:
            with self._connection.transaction():
                cursor = self._connection.execute(_UPSERT_GAME, row)
                if cursor.rowcount == 0:
                    raise ConcurrentGameModification(
                        f"game '{game.game_id}' was modified concurrently "
                        f"(expected version {game.version})"
                    )
                for envelope in pending_events:
                    self._connection.execute(
                        _INSERT_EVENT, event_to_row(game.game_id, envelope)
                    )
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
    def __init__(self, connection: psycopg.Connection) -> None:
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
```

Semantics worth understanding while implementing:
- The `ON CONFLICT (id) DO UPDATE ... WHERE games.version = %(version)s` is the
  optimistic lock: a fresh insert stores `version + 1`; an update only lands when the
  stored version still equals `game.version`. `cursor.rowcount == 0` means the WHERE
  rejected the update → `ConcurrentGameModification`, raised inside the
  `transaction()` block so psycopg rolls back everything (it is a `DomainError`, so it
  is NOT swallowed by the `psycopg.Error` handler around the block).
- A duplicate `(game_id, sequence)` event insert trips the primary key →
  `psycopg.Error` → `PersistenceError`, whole transaction rolled back.
- `game.version += 1` runs only after the `with` block committed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_postgres_repository.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite, lint, and typecheck**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: all PASS, no errors

- [ ] **Step 6: Commit**

```bash
git add src/infrastructure/persistence/postgres/repository.py tests/infrastructure/test_postgres_repository.py
git commit -m "feat(infrastructure): add postgres repositories with atomic save and optimistic locking" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: CLI `--db` Flag, Configuration & Docs

**Files:**
- Modify: `src/interfaces/cli/app.py` (`build_service` at lines 38-39; `main` at lines 100-113)
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/integration/test_postgres_wiring.py` (new)
- Test: `tests/interfaces/test_cli.py` (extend)

**Interfaces:**
- Consumes: `PostgresGameRepository`, `PostgresEventRepository` (Task 5), `run_migrations`, `connect` (Task 3), in-memory pair (Task 2), `PersistenceError` (Task 1).
- Produces:
  - `build_service(db: str = "memory") -> GameService` — `"memory"` wires the shared in-memory pair (behaviour unchanged); `"postgres"` requires `DATABASE_URL` (missing → plain `ValueError` with an explanatory message — a configuration mistake, not `PersistenceError`, per spec §8), runs migrations idempotently, wires the PG repositories on one connection. Any other value → `ValueError("unknown database backend: ...")`.
  - `main(...)` gains `--db {memory,postgres}` (default `memory`) and returns exit code 2 with a red message when backend construction raises `ValueError` or `PersistenceError`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/interfaces/test_cli.py` (the file already defines `_console`, `_scripted`, and imports `main`):

```python
def test_build_service_postgres_requires_database_url(monkeypatch) -> None:
    from interfaces.cli.app import build_service

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        build_service("postgres")


def test_main_reports_missing_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(argv=["--db", "postgres"], console=console, input_fn=_scripted())
    assert code == 2
    assert "DATABASE_URL" in buffer.getvalue()


def test_build_service_rejects_unknown_backend() -> None:
    from interfaces.cli.app import build_service

    with pytest.raises(ValueError, match="unknown database backend"):
        build_service("oracle")
```

Add `import pytest` to the top of the file with the other imports.

```python
# tests/integration/test_postgres_wiring.py
"""build_service(db="postgres") wires the real PG repositories end to end (spec §10)."""

from io import StringIO

from rich.console import Console

from application.commands import CreateGameCommand
from infrastructure.persistence.postgres.connection import connect


def _console() -> tuple[Console, StringIO]:
    buffer = StringIO()
    return Console(file=buffer, width=100, force_terminal=False), buffer


def _scripted(*lines: str):
    iterator = iter(lines)

    def _input(prompt: str) -> str:
        try:
            return next(iterator)
        except StopIteration as error:
            raise EOFError from error

    return _input


def test_build_service_postgres_persists_to_real_database(
    postgres_url: str, monkeypatch
) -> None:
    from interfaces.cli.app import build_service

    monkeypatch.setenv("DATABASE_URL", postgres_url)
    service = build_service("postgres")

    game_id = service.create_game(CreateGameCommand(seed=7, campaign_name="Wiring"))

    connection = connect(postgres_url)
    row = connection.execute(
        "SELECT version, status FROM games WHERE id = %s::uuid", (str(game_id),)
    ).fetchone()
    events = connection.execute(
        "SELECT event_type FROM game_events ORDER BY sequence"
    ).fetchall()
    connection.close()

    assert row is not None
    assert row["version"] == 1
    assert row["status"] == "created"
    assert [e["event_type"] for e in events] == ["game_created"]


def test_cli_game_on_postgres_persists_game_and_events(
    postgres_url: str, monkeypatch
) -> None:
    from interfaces.cli.app import main

    monkeypatch.setenv("DATABASE_URL", postgres_url)
    console, buffer = _console()

    code = main(
        argv=["--db", "postgres", "--seed", "42"],
        console=console,
        input_fn=_scripted(*(["attack goblin"] * 60)),
    )

    assert code == 0
    assert "The adventure has ended" in buffer.getvalue()

    connection = connect(postgres_url)
    games = connection.execute("SELECT status, version FROM games").fetchall()
    event_types = [
        row["event_type"]
        for row in connection.execute(
            "SELECT event_type FROM game_events ORDER BY game_id, sequence"
        ).fetchall()
    ]
    connection.close()

    assert len(games) == 1
    assert games[0]["status"] == "ended"
    assert games[0]["version"] > 1
    assert "attack_resolved" in event_types
    assert "damage_applied" in event_types
    assert "combat_ended" in event_types
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/interfaces/test_cli.py tests/integration/test_postgres_wiring.py -v`
Expected: FAIL — `TypeError: build_service() takes 0 positional arguments but 1 was given`; the `--db` flag tests fail with argparse's `unrecognized arguments` error.

- [ ] **Step 3: Write the implementation**

In `src/interfaces/cli/app.py`:

a) Add `import os` after `import argparse` (line 5).

b) Change the existing `from domain.common.errors import DomainError` (line 19) to:

```python
from domain.common.errors import DomainError, PersistenceError
```

c) Add these imports after the existing infrastructure imports (lines 21-22):

```python
from infrastructure.persistence.postgres.connection import connect
from infrastructure.persistence.postgres.migrate import run_migrations
from infrastructure.persistence.postgres.repository import (
    PostgresEventRepository,
    PostgresGameRepository,
)
```

d) Replace `build_service` (lines 38-39) with:

```python
def build_service(db: str = "memory") -> GameService:
    """Wire the application layer onto a persistence backend (spec §8)."""
    if db == "memory":
        event_store = InMemoryEventRepository()
        return GameService(InMemoryGameRepository(event_store), event_store)
    if db == "postgres":
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise ValueError(
                "DATABASE_URL is not set; copy .env.example and configure it "
                "to run with --db postgres"
            )
        run_migrations(database_url)
        connection = connect(database_url)
        return GameService(
            PostgresGameRepository(connection),
            PostgresEventRepository(connection),
        )
    raise ValueError(f"unknown database backend: {db!r}")
```

e) In `main`, add the flag next to `--seed` (after line 107):

```python
    parser.add_argument("--db", choices=("memory", "postgres"), default="memory")
```

f) Replace the service construction (line 112-113, `service = service or build_service()`) with:

```python
    console = console or Console()
    if service is None:
        try:
            service = build_service(args.db)
        except (ValueError, PersistenceError) as error:
            console.print(f"[red]{error}[/red]")
            return 2
```

Everything else in `main` is unchanged.

Replace `.env.example` entirely with:

```bash
# Copy to .env and fill in. .env is gitignored; never commit real credentials.
OPENROUTER_API_KEY=

# PostgreSQL connection for --db postgres (Plan 2 persistence).
# Example: postgresql://conclave:secret@localhost:5432/conclave
DATABASE_URL=
```

In `README.md`, after the "## Play (MVP-0 deterministic combat sandbox)" section, add:

```markdown
## Persistence (PostgreSQL, optional)

MVP-0 runs fully in memory by default. To persist games and events:

```bash
export DATABASE_URL=postgresql://user:pass@localhost:5432/conclave
.venv/bin/python -m infrastructure.persistence.postgres.migrate   # idempotent
.venv/bin/python -m interfaces.cli.app --db postgres --seed 42
```

Without `--db postgres` the game behaves exactly as before (in-memory).
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/interfaces/test_cli.py tests/integration/test_postgres_wiring.py -v`
Expected: PASS (the two existing CLI tests still pass — the default `db="memory"` preserves behaviour).

- [ ] **Step 5: Run the full suite, lint, and typecheck**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: all PASS, no errors

- [ ] **Step 6: Commit**

```bash
git add src/interfaces/cli/app.py .env.example README.md tests/interfaces/test_cli.py tests/integration/test_postgres_wiring.py
git commit -m "feat(interfaces): add --db flag wiring postgres persistence into the cli" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: Roadmap Update, Full Verification & Manual Acceptance

**Files:**
- Modify: `docs/superpowers/plans/README.md`
- Verify: everything

**Interfaces:**
- Consumes: all prior tasks.
- Produces: documentation state matching reality (Plan 1 complete, Plan 2 complete, pgserver decision recorded).

- [ ] **Step 1: Update the plans roadmap**

In `docs/superpowers/plans/README.md`, change the Plan 1 and Plan 2 rows of the table to:

```markdown
| 1 | `2026-09-03-deterministic-core-mvp0.md` | Phases 0–7 — Repository bootstrap, domain primitives, dice, checks, actions, combat, events, first playable CLI (**MVP-0**) | Complete |
| 2 | `2026-09-04-persistence-postgres.md` | Phase 8 — PostgreSQL repositories, transactions, optimistic locking | Complete |
```

And in the "Known documentation gaps" section, add a resolution note as a new bullet:

```markdown
- Resolved (Plan 2): PostgreSQL test/dev strategy uses `pgserver` (pip-installable,
  root-free, pgvector bundled for Plan 7); runtime uses `psycopg` 3 + `DATABASE_URL`
  with plain-SQL migrations. CLAUDE.md §36 needed no amendments.
```

- [ ] **Step 2: Full verification battery**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: all PASS, no errors. Record the test count (MVP-0 baseline: 145 tests).

- [ ] **Step 3: Manual acceptance — play a game on PostgreSQL**

```bash
export DATABASE_URL=$(.venv/bin/python - <<'EOF'
import pgserver
print(pgserver.get_server("/tmp/conclave-manual-pg").get_uri())
EOF
)
.venv/bin/python -m infrastructure.persistence.postgres.migrate
.venv/bin/python -m interfaces.cli.app --db postgres --seed 42
```

Play `attack goblin` until `The adventure has ended`, then verify from another shell:

```bash
.venv/bin/python - <<'EOF'
import os
from infrastructure.persistence.postgres.connection import connect
connection = connect(os.environ["DATABASE_URL"])
print("games:", connection.execute("SELECT status, version FROM games").fetchall())
print(
    "events:",
    connection.execute(
        "SELECT event_type, count(*) AS n FROM game_events"
        " GROUP BY event_type ORDER BY event_type"
    ).fetchall(),
)
connection.close()
EOF
```

Expected: one `ended` game at version > 1, and event counts including `attack_resolved`, `damage_applied`, and `combat_ended`. Finally stop the throwaway server:

```bash
.venv/bin/python -c "import pgserver; pgserver.get_server('/tmp/conclave-manual-pg').cleanup()"
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/README.md
git commit -m "docs: mark plans 1-2 complete and record the pgserver decision" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Completion Standard (CLAUDE.md §73)

- **What changed?** PostgreSQL persistence behind the existing ports: atomic `save(game, pending_events)` with optimistic locking (`version` + `ConcurrentGameModification`), append-only `game_events`, SQL migrations + runner, `--db` CLI wiring, `pgserver`-based integration tests.
- **Which architectural layer owns it?** Domain: `version` field + error vocabulary. Application: port contract + `_persist` orchestration. Infrastructure: connection, mapping, SQL, repositories, migrations. Interfaces: `--db` flag.
- **Which tests verify it?** `tests/infrastructure/test_in_memory_save.py`, `test_postgres_migrations.py`, `test_postgres_mapping.py`, `test_postgres_repository.py`, `tests/integration/test_postgres_wiring.py`; the full prior suite stays green.
- **Can the feature work without a real LLM?** Yes — no LLM anywhere in this plan.
- **Can an invalid action corrupt game state?** No — domain validation is unchanged; a failed save rolls back atomically and a stale version raises without writing.
- **Did any provider-specific dependency leak across boundaries?** psycopg/SQL exist only under `src/infrastructure/persistence/postgres/`; domain and application remain stdlib-only; interfaces touch only `build_service`.
- **Were existing tests run at every step?** Yes — full battery after each task.
