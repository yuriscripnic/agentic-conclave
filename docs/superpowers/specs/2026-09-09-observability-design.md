# Observability Design — Phase 17 (Roadmap Plan #8)

Date: 2026-09-09
Status: Approved (design sections approved in session; see git history)
Upstream: `CLAUDE.md` (§20, §28, §34, §35, §36, §50, §60, §65, §66), `docs/Agentic Conclave-Implementation Plan.md` §20 (Phase 17), `docs/superpowers/plans/README.md` row #8

## 1. Goal

Make the AI platform's per-call telemetry observable: every LLM call (chat, structured decision, embedding) becomes a structured log line, a persistent Postgres row, and part of an in-session totals table — always as bookkeeping, never as a gate on the game.

Phase 17's Implementation-Plan checklist: `LLMInvocation` with `request_id`, `game_id`, `agent_id`, `model`, `provider`, `input_tokens`, `output_tokens`, `total_tokens`, `latency_ms`, `estimated_cost`, `tools_called`, `retrieval_count`, `retry_count`, `timestamp`, `status`, `error`. OpenTelemetry is explicitly deferred ("when the core implementation is stable").

## 2. Current state (ground truth this design builds on)

- `LLMInvocation` exists (`src/ai/models/types.py`) with 10 fields: `provider`, `model`, `operation`, `status`, `error_kind`, `latency_ms`, `input_tokens`, `output_tokens`, `estimated_cost_usd`, `request_id`. Every model/embedding response and every report already carries invocations.
- 8 construction sites, all transport-side: OpenRouter adapter (4), fake model gateway (3), deterministic fake embedder (1).
- Zero consumers: no `logging` anywhere in `src/`, no correlation IDs, no CLI surfacing, no persistence.
- Pricing is already configured in `config/llm.toml` (z-ai chat models + the embedding model) and `estimated_cost_usd` is already computed per call.
- `AgentRuntime` is the single choke point through which every structured model call flows; retry attempts already surface as separate invocations (each attempt is its own record).

## 3. Architecture

One enriched record type, one application-defined port, three infrastructure sinks:

```text
AgentTurnService ──┐
GmDirector ────────┤  enrich (dataclasses.replace) → TelemetrySink.record()
MemoryService ─────┘                     │
                    ┌────────────────────┼──────────────────────┐
                    ▼                    ▼                      ▼
          LoggingTelemetrySink   InMemoryTelemetrySink   PostgresTelemetrySink
          (stdlib logging,       (session accumulator    (llm_invocations table,
           JSON lines, stderr)    the CLI reads)          only with --db postgres)
```

### 3.1 Enriched `LLMInvocation` (src/ai/models/types.py)

New fields, all with defaults so existing construction sites keep working:

```python
timestamp: str | None = None
game_id: str | None = None
agent_id: str | None = None
correlation_id: str | None = None
attempt: int = 1
retrieval_count: int = 0
tools_called: int = 0
```

- Transport facts stay gateway-owned exactly as today: `provider`, `model`, `operation`, `status`, `error_kind`, `latency_ms`, `input_tokens`, `output_tokens`, `estimated_cost_usd`, `request_id`.
- `attempt > 1` means the call was a retry. `retrieval_count` is stamped by the memory path. `tools_called` is always 0 until a tool layer exists (Phase 17 asks for the field; there are no tools yet).
- `timestamp` is a UTC ISO-8601 string stamped by the application layer at enrichment time.
- The record never contains prompts, payloads, or reasoning (§34).

### 3.2 Per-turn correlation (§35 minimum)

- Each turn generates a fresh UUID-style `correlation_id`, shared by **every** LLM call made while servicing that turn: human input, agent decision (+ its retries and memory retrieval), enemy turns, GM reactions.
- Each call keeps its unique `request_id` (gateway-owned, as today).
- `causation_id` is explicitly out of scope until multi-step agent chains exist.
- `game_id` and `agent_id` are stamped on every record from the servicing context. GM calls use `agent_id="gm"`; embedding calls use the owning character's id.

### 3.3 `TelemetrySink` port (src/application/telemetry/)

Application-layer `Protocol` with one method:

```python
class TelemetrySink(Protocol):
    def record(self, invocation: LLMInvocation) -> None: ...
```

The application layer composes sinks (a simple list, called in order). The port is deliberately narrow; no batch, no query, no lifecycle beyond construction.

### 3.4 Sinks (src/infrastructure/telemetry/)

**LoggingTelemetrySink** — stdlib `logging`, logger name `conclave.telemetry`, one JSON object per line with keys: `ts`, `event` (`"llm_invocation"`), `game_id`, `agent_id`, `correlation_id`, `request_id`, `provider`, `model`, `operation`, `status`, `error_kind`, `latency_ms`, `input_tokens`, `output_tokens`, `total_tokens`, `estimated_cost_usd`, `attempt`, `retrieval_count`, `tools_called`. Handler setup: if env var `CONCLAVE_TELEMETRY_LOG` holds a path, attach a `FileHandler` to it; otherwise a stderr handler. Effective level is WARNING (silent for telemetry lines) unless `--debug` sets DEBUG.

**InMemoryTelemetrySink** — per-session accumulator. `snapshot()` returns per-agent and per-role aggregates: call count, retry count (records with `attempt > 1`), input/output tokens, estimated cost. Role assignment: `gm` (agent_id `"gm"`), `embedding` (operation is an embedding), otherwise `player-agent`.

**PostgresTelemetrySink** — plain-SQL `INSERT` into `llm_invocations`, one row per invocation. Unparseable id fields (fake gateways use ids like `req-0001`) insert as `NULL` instead of failing — fake-mode determinism is preserved. Migration `003_llm_invocations.sql`:

```sql
CREATE TABLE IF NOT EXISTS llm_invocations (
    request_id      UUID PRIMARY KEY,
    game_id         UUID,
    agent_id        UUID,
    correlation_id  UUID,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    operation       TEXT NOT NULL,
    status          TEXT NOT NULL,
    error_kind      TEXT,
    latency_ms      INTEGER,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    estimated_cost_usd NUMERIC(12, 6),
    attempt         INTEGER NOT NULL DEFAULT 1,
    retrieval_count INTEGER NOT NULL DEFAULT 0,
    tools_called    INTEGER NOT NULL DEFAULT 0,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Idempotent, same plain-SQL runner as migrations 001/002.

### 3.5 Enrichment points (application layer)

- `AgentTurnService.take_turn` / enemy-turn paths: stamp `game_id`, `agent_id` (acting character), turn `correlation_id`, `timestamp` on every invocation in the produced report.
- `GmDirector` hooks (`on_combat_open`, `on_turn_report`, `on_player_say`): stamp `game_id`, `agent_id="gm"`, turn `correlation_id`, `timestamp`.
- `MemoryService` retrieval/embedding: stamp `agent_id` = owning character id, plus `retrieval_count` = number of memories returned, plus `game_id`/`correlation_id`/`timestamp`.
- Enrichment is `dataclasses.replace` on frozen records — total, side-effect-free, additive.

### 3.6 CLI surfacing (src/interfaces/cli/)

- `--debug` flag: telemetry logger to DEBUG on stderr → per-call JSON lines during play. Default runs stay clean (logger stays at WARNING).
- `/telemetry` command: prints a session table — per agent/role row: calls, retries, tokens in/out, estimated cost.
- End-of-session summary: the same totals printed once at game end, before "Thanks for playing!".
- Sink composition: logging sink (always), in-RAM sink (always), Postgres sink (only with `--db postgres`).

## 4. Error-handling policy: telemetry never gates the game

One rule, applied at every layer (same discipline as memory and GM failures — §28, §66):

- **Sink `record()` failures are swallowed** inside each sink; the Postgres sink may log one WARNING line via the telemetry logger.
- **The CLI wiring wraps the composite sink**: an unexpected sink exception is reported once and that sink is dropped; the session continues with the remaining sinks.
- **Postgres unavailability mid-session** degrades to logging-only; startup unreachability with `--db postgres` still hard-fails (existing behavior for game tables).
- **Enrichment cannot fail a turn**: `replace` on frozen dataclasses is total and side-effect-free.
- **Fake-mode determinism is untouched**: the sink pipeline is additive; the offline suite must pass unchanged except for its new tests.

## 5. Layer boundaries

- `src/domain/` — zero diff. Verified per task: `git log master..HEAD -- src/domain` stays empty.
- `src/ai/models/types.py` — the enriched `LLMInvocation` (AI platform layer; already LLM-aware, correct home).
- `src/application/telemetry/` — the `TelemetrySink` Protocol (application owns ports).
- `src/infrastructure/telemetry/` — the three sinks. The Postgres sink imports only psycopg and the existing connection helper; no provider SDKs beyond what already exists.
- `src/interfaces/cli/` — composition and presentation only; no game rules.
- Provider names remain only under `src/infrastructure/` and as config values.

## 6. Testing

- **Unit:** enrichment at each service (game/agent/correlation/attempt/retrieval stamps correct); each sink's `record()`/`snapshot()`; Postgres tolerance of non-UUID ids; logging shape via `caplog`.
- **Integration:** pgserver session fixture round-trips an invocation row (migration 003 + insert + read-back); CLI `--debug`, `/telemetry`, and end-of-session summary via the existing `_console()`/`_scripted()` helpers; a full offline scripted game with `--debug` emits parseable JSON lines and exits 0.
- **Regression:** full offline gate green without `OPENROUTER_API_KEY`; live OpenRouter tests unaffected.

## 7. Carry-forwards folded into this plan

1. **`live` pytest marker** — register `live` in `pyproject.toml`, add `tests/conftest.py` with `addopts = ["-m", "not live"]` so the default run skips the two live OpenRouter tests cleanly offline; mark those tests `@pytest.mark.live`; `pytest -m live` (with key) runs them. The `OPENROUTER_API_KEY=` env-dance in documented commands disappears.
2. **Explicit `default_provider`** — `src/ai/models/profiles.py:84` drops the `"openrouter"` fallback; a missing `default_provider` in `config/llm.toml` is an explicit load error naming the missing key.

## 8. Non-goals (YAGNI)

- No OpenTelemetry, no metrics libraries, no `causation_id`, no tool-call tracing beyond the `tools_called` counter, no replay/debug UI, no log rotation, no runtime-configurable levels beyond `--debug`, no telemetry API endpoints.

## 9. Plan shape

Estimated ~7 tasks: (1) enriched `LLMInvocation`, (2) `TelemetrySink` port + in-RAM sink, (3) logging sink, (4) Postgres sink + migration 003, (5) enrichment wiring in the three services, (6) CLI `--debug`/`/telemetry`/summary + README, (7) carry-forwards + final verification. Exact code, test projections, and gates are defined in the implementation plan.

## 10. Completion checklist (mirrors Implementation Plan §25)

- Behavior implemented, tests exist and pass, mypy strict + ruff clean.
- Architecture boundaries respected; domain diff empty.
- Invalid inputs handled (non-UUID ids, sink failures, missing env keys).
- Telemetry never gates the game (proven by tests).
- Configuration externalized (`CONCLAVE_TELEMETRY_LOG`, `--debug`, `--db`).
- No secrets committed; telemetry never logs prompts/payloads/reasoning.
