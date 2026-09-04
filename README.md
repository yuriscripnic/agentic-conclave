# Agentic Conclave

An AI-powered multi-agent D&D RPG built on a deterministic rules engine:
LLMs propose. The domain decides. The game engine executes. Events record what happened.

## Setup

```bash
uv venv .venv --python 3.12
uv pip install -e ".[dev]"
```

## Run tests / lint / typecheck

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy
```

## Play (MVP-0 deterministic combat sandbox)

```bash
.venv/bin/python -m interfaces.cli.app --seed 42
```

## Persistence (PostgreSQL, optional)

MVP-0 runs fully in memory by default. To persist games and events:

```bash
export DATABASE_URL=postgresql://user:pass@localhost:5432/conclave
.venv/bin/python -m infrastructure.persistence.postgres.migrate   # idempotent
.venv/bin/python -m interfaces.cli.app --db postgres --seed 42
```

Without `--db postgres` the game behaves exactly as before (in-memory).
