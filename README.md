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

## Model gateway (offline by default)

LLM access goes through a provider-agnostic `ModelGateway` (`src/ai/models/`).
Tests and offline runs use the deterministic `FakeModelGateway`; live calls use
the OpenRouter adapter behind `OPENROUTER_API_KEY`:

```bash
export OPENROUTER_API_KEY=sk-or-...
```

Model profiles (`gm`, `player`, `cheap`, `reasoning`, `creative`, `embedding`)
are configured in `config/llm.toml`. The first consumer is the AI character
agent (`--agent llm`).

## AI party (offline by default)

`--agent llm` adds three AI-controlled party members (Brix, Mira, Sera) who
decide their own attacks through the model gateway and coordinate through
party chatter; the human keeps commanding Arin:

```bash
export OPENROUTER_API_KEY=sk-or-...
.venv/bin/python -m interfaces.cli.app --agent llm --seed 42
```

An offline demo that never touches the network:

```bash
.venv/bin/python -m interfaces.cli.app --agent fake --seed 42
```

Agent identity, persona, objective, and statlines live in `config/agents.toml`;
the encounter lives in `config/encounter.toml` and is loaded in every mode;
retry budgets sit under `[agent]`. Agents may broadcast one short
`party_message` per accepted turn; the last 8 messages join every agent's
prompt. The agent proposes, the rules engine decides — invalid proposals are
retried with the rejection reason, then a deterministic fallback attack.

## Agent memory (offline by default)

AI party members remember what happens to them. Each accepted turn records an
**episodic** memory (derived from the turn's domain events) and, when the model
includes a `memory_note` in its decision, a **semantic** one (the model's own
note-to-self). Before each turn the five most relevant memories are retrieved by
embedding similarity and rendered into the agent's prompt.

- `--agent fake` uses a deterministic stdlib embedder and the in-memory
  repository — fully offline.
- `--agent llm` embeds with `openai/text-embedding-3-small` through OpenRouter
  (the one sanctioned carve-out from the cheap-chat-model directive).
- `--db postgres` persists memories to `agent_memories` (pgvector cosine search,
  migration `002_agent_memories.sql`; a PostgreSQL with the `vector` extension
  available is required — pgserver ships it); `--db memory` keeps them in RAM.

Memory is bookkeeping, never a gate: retrieval or embedding failures degrade to
an empty memory for that turn and the game continues (CLAUDE.md §28, §66).
Memory contents are private context and are never logged or displayed outside
the owning agent's own prompt (§20, §34).

## The Game Master (offline by default)

The GM is an AI narrator: it opens the fight with a short scene-setting line,
reacts to notable events (critical hits, defeats, combat end), and answers
`say <text>` in the voice of the most fitting living enemy. It never mutates
game state — the rules engine stays the sole authority (LLMs propose; the
domain decides).

```bash
# Deterministic offline demo: scripted agents + scripted GM (both defaults)
.venv/bin/python -c "import sys; from interfaces.cli.app import main; sys.exit(main(sys.argv[1:]))"

# Real models via OpenRouter (--agent llm --gm llm; [profiles.gm] in config/llm.toml)
export OPENROUTER_API_KEY=...   # shell only; never commit keys
.venv/bin/python -c "import sys; from interfaces.cli.app import main; sys.exit(main(sys.argv[1:]))" --agent llm --gm llm
```

- `--gm off|llm|fake` — default `fake` (offline by default, like `--agent`).
- Persona and caps live in `config/gm.toml`; model selection in `config/llm.toml` (`[profiles.gm]`).
- GM failures never gate the game: a failed call simply prints nothing.

## Observability (telemetry)

Every LLM call becomes a structured `LLMInvocation` record — never prompts,
payloads, or reasoning (CLAUDE.md §34). Three sinks: a JSON log line per call,
an in-session totals table, and, with `--db postgres`, one row per call in
`llm_invocations` (migration `003_llm_invocations.sql`; TEXT id columns so
fake-gateway ids persist too).

- `--debug` — per-call JSON lines on stderr, or to the file named by
  `$CONCLAVE_TELEMETRY_LOG`.
- `/telemetry` — per-agent/role session totals: calls, retries, tokens in/out,
  estimated cost. The same table prints once when the session ends.
- Telemetry never gates the game: a failing sink is dropped after one warning
  and the session continues (Postgres failures degrade to logging-only).
