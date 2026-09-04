# Persistence (Plan 2) — Design Specification

**Date:** 2026-09-04
**Status:** Approved design, pending implementation plan
**Covers:** Implementation Plan doc Phase 8 (§11) — PostgreSQL repositories, transactions, optimistic locking
**Governing docs:** CLAUDE.md (§36–§39, §49, §55, §72), `docs/Agentic Conclave-Implementation Plan.md` §11, `docs/Agentic Conclave-architecture-overview.md` §23/§30

---

## 1. Goal

Replace the in-memory repository implementations with PostgreSQL implementations
behind the existing application ports, so that game state and domain events are
persisted transactionally with optimistic locking. The MVP-0 combat sandbox keeps
working unchanged (in-memory by default); `--db postgres` runs the same
application layer on PostgreSQL.

**Explicitly in scope:**

- PostgreSQL implementations of the persistence ports
- Atomic save of game state + pending events in one transaction
- Optimistic locking via `game.version` with `ConcurrentGameModification`
- Versioned plain-SQL migrations with a small runner
- CLI `--db {memory,postgres}` wiring
- Real-PostgreSQL integration tests via `pgserver`

**Explicitly out of scope (see §9):** combat/RNG rehydration, pgvector, async,
ORM/migration frameworks, retry policies.

## 2. Decision log

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Durability scope | Ports swap only; combat state, dice RNG stream, and event collectors stay in `GameService` memory | Full restart resilience requires event replay/rehydration — premature per CLAUDE.md §11. Deferred to a later plan. |
| D2 | Database | PostgreSQL; `psycopg` 3 (runtime driver), `pgserver` (test/dev server) | Matches CLAUDE.md §36 and Implementation Plan §11 as written — no doc amendments. `pgserver` is pip-installable, root-free, bundles pgvector (unused until Plan 7). |
| D3 | CLI visibility | `--db {memory,postgres}`, default `memory` | Demonstrates the ports swapping implementations (portfolio claim) while preserving MVP-0's zero-setup property. |
| D4 | Schema & write path | Aggregate-document (JSONB) + combined atomic save; domain `version` field; plain SQL migrations | Approach 1 of the brainstorm (2026-09-04): smallest honest scope; the aggregate is the consistency boundary; events stay queryable rows; no speculative normalization. Migration path to a UnitOfWork or normalized design touches only infrastructure. |

## 3. Domain changes (small)

1. **`Game.version`** — new field `version: int = 0` on the `Game` aggregate
   (`src/domain/world/game.py`). It is persistence metadata: domain rules never
   read it. The repository stamps it (`+1`) after a successful save. The
   default keeps every existing constructor and test fixture valid.
2. **New domain errors** in `src/domain/common/errors.py` (both are named in
   CLAUDE.md §49 but do not exist yet):
   - `ConcurrentGameModification(DomainError)` — save lost the version race.
   - `PersistenceError(DomainError)` — infrastructure/storage failure, raised
     at the repository boundary with `from e` chaining; driver types never
     cross into application/interfaces.

The domain remains stdlib-only and database-ignorant: it defines the error
vocabulary, infrastructure implements the storage.

## 4. Port contracts (application layer)

```python
class GameRepository(Protocol):
    def save(self, game: Game, pending_events: Sequence[EventEnvelope]) -> None:
        """Atomically persist the aggregate and append pending events.

        - Single transaction (BEGIN ... COMMIT).
        - Optimistic lock: UPDATE games ... WHERE id = ? AND version = game.version;
          zero rows updated -> ROLLBACK -> ConcurrentGameModification.
        - On success: events appended, version stamped game.version += 1.
        - pending_events may be empty (e.g. add_character persists with no events).
        """
    def get(self, game_id: GameId) -> Game:  # raises GameNotFoundError

class EventRepository(Protocol):
    def get_events(self, game_id: GameId) -> list[EventEnvelope]:
        """Full history for a game, ordered by sequence."""
```

- `append` is **removed from the `EventRepository` Protocol** — the write path
  is `GameRepository.save`. (The in-memory event store keeps an `append`
  method as an implementation detail used by its sibling repository.)
- `GameService._persist` becomes: `drained = collector.drain(); games.save(game, drained)`.
- Wiring: `InMemoryGameRepository(event_store)` receives the shared
  `InMemoryEventRepository` so one `save` writes both stores; the Postgres
  pair shares one connection. Construction sites (CLI `build_service`, test
  helpers) are updated mechanically.

## 5. Schema (migration 001)

```sql
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
    game_id    UUID NOT NULL REFERENCES games(id),
    sequence   INTEGER NOT NULL,
    event_id   UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    payload    JSONB NOT NULL,
    PRIMARY KEY (game_id, sequence)
);

CREATE TABLE schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- Primary key `(game_id, sequence)` enforces ordering and rejects duplicate
  appends (a repeated persist of the same envelopes is a bug and must fail).
- `game_events` is append-only by construction: no code path issues UPDATE or
  DELETE against it.
- The secondary event index is deliberately omitted — `get_events` scans by
  the PK prefix; no other event query exists yet (YAGNI).

## 6. Mapping (infrastructure/persistence/postgres/mapping.py)

- **`Game` → state JSONB:** explicit serializer (not blind `asdict`): IDs →
  strings, enums → values, HP → `{current, maximum}`, conditions → list,
  inventory → `{items: {item_id: {name, quantity}}, gold}`, equipped_weapon →
  nullable weapon object, characters → list (order preserved), sides as
  `party_ids`/`enemy_ids`, `status` string. `version` lives in its own column,
  not in the document.
- **Rows → `Game`:** rebuilt through the domain constructors (`Character`,
  `AbilityScores`, `HitPoints`, `Weapon`, `Inventory`), so validation re-runs
  on load and corrupted stored state fails loudly instead of silently
  propagating.
- **`EventEnvelope` ↔ row:** direct column mapping; payload stays JSONB.

## 7. Transactions & concurrency semantics

- Transaction shape per CLAUDE.md §37:
  `BEGIN → UPDATE games (version check) → INSERT game_events → COMMIT`.
- On version mismatch: rollback, raise `ConcurrentGameModification` — the
  aggregate and events are left untouched.
- No automatic retry: the current process model is one logical command queue
  per game (CLAUDE.md §38); a version conflict signals a bug and is surfaced.
  A retry policy is a future, configuration-gated addition.
- Connection handling: one psycopg connection owned by a small
  `PostgresConnection` wrapper and shared by both repositories; each `save`
  uses `with connection.transaction()`. No pooling package (YAGNI; CLI and
  tests are single-user).

## 8. Configuration, CLI & migrations

- `DATABASE_URL` (e.g. `postgresql://user:pass@localhost:5432/conclave`) read
  via `os.environ` — no dotenv dependency; `.env.example` documents it.
- `build_service(db="memory")` — memory wiring unchanged.
  `build_service(db="postgres")`: requires `DATABASE_URL` (a missing variable
  is a configuration mistake and raises a plain `ValueError` with an
  explanatory message — not `PersistenceError`), applies migrations
  idempotently, wires `PostgresGameRepository` + `PostgresEventRepository`.
  Migration or connection failures surface as `PersistenceError` with the
  driver error chained.
- Migration runner: `python -m infrastructure.persistence.postgres.migrate`
  (reads `DATABASE_URL` or `--database-url`), applies `migrations/*.sql` in
  filename order, records applied versions in `schema_migrations`, skips
  already-applied ones. SQL files live inside the package
  (`importlib.resources`), so they ship with the installed app.

## 9. Non-goals

pgvector / semantic memory (Plan 7) · combat/RNG/collector rehydration (future
event-replay plan) · async repositories · connection pooling · alembic /
SQLAlchemy / any ORM · auto-retry on conflicts · multi-user concurrency ·
HTTP API (Plan 10).

## 10. Testing strategy

- **Existing suite:** all 145 tests keep passing; only mechanical updates to
  `_service()` helpers for the new in-memory wiring.
- **New unit tests:** in-memory save/event atomicity semantics, version
  stamping, error mapping.
- **New integration tests** (real PostgreSQL via `pgserver`, marked as a
  dedicated module):
  - fixture: session-scoped `pgserver.get_server(tempdir)`; function-scoped
    `CREATE DATABASE` per test (fast, fully isolated).
  - aggregate roundtrip: `save → get` reproduces the full aggregate
    (characters, sides, HP, inventory, conditions, weapon, status).
  - optimistic locking: stale-version save raises `ConcurrentGameModification`
    and persists nothing; successful save stamps `version + 1`.
  - events: contiguous sequences survive across multiple saves; duplicate
    sequence insert is rejected; `get_events` returns full ordered history.
  - corrupted state on load surfaces as a domain error, not a silent rebuild.
- **CLI wiring test:** `build_service(db="postgres")` against the fixture
  server; `--db postgres` without `DATABASE_URL` fails with a clear message.
- **Dependencies:** `psycopg[binary]` → main deps; `pgserver` → dev extras.
  During the plan's first task, verify pgserver's bundled PostgreSQL version
  meets Plan 2 needs (any supported PG ≥ 13 does); fallback if broken: apt
  `postgresql` + unprivileged temp cluster (same fixture shape).

## 11. Documentation updates

- `.env.example`: `DATABASE_URL=`.
- Repo `README.md`: optional PostgreSQL setup + `--db postgres` usage.
- `docs/superpowers/plans/README.md`: mark Plan 1 ✅ complete, Plan 2
  written/in progress; note the pgserver decision.

## 12. Completion standard (CLAUDE.md §73)

- **What changed?** PostgreSQL persistence of the game aggregate + events with
  atomic saves, optimistic locking, migrations, CLI wiring; domain gains
  `version` + two error classes; ports gain the combined atomic save.
- **Which layer owns it?** Domain: `version`, error vocabulary. Application:
  port contracts + `_persist` orchestration. Infrastructure: mapping, SQL,
  migrations, connection. Interfaces: `--db` flag.
- **Which tests verify it?** Roundtrip, optimistic-lock, event-integrity,
  wiring tests against real PG; full existing suite still green.
- **Works without a real LLM?** Yes — no LLM anywhere.
- **Can an invalid action corrupt state?** No — unchanged domain validation;
  a failed/conflicting save leaves zero partial state (transaction + rollback).
- **Provider-specific leaks?** psycopg, pgserver and SQL exist only under
  `infrastructure/persistence/postgres`; domain/application stay stdlib-only.
- **Were existing tests run?** Full `pytest`, `ruff`, `mypy` per task.
