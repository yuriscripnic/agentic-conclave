# Agent Memory + pgvector Design (Plan 6)

**Status:** Approved design → spec
**Date:** 2026-09-06
**Phase:** 10 (memory + pgvector; §21 memory types, §36 pgvector, §22 context engineering)
**References:** `CLAUDE.md` (§6–7, §10, §20–23, §28, §33–34, §36, §45–48, §51, §55), `docs/superpowers/specs/2026-09-06-multi-agent-party-design.md` (binding for the agent stack this plan extends), `docs/superpowers/specs/2026-09-05-character-agent-design.md` (decision pipeline, retry budgets, fallback)

---

## 1. Purpose

Plans 4–5 gave every agent a decision pipeline, a shared party board, and per-turn
perception — but each turn starts from amnesia: nothing an agent experienced in round 2
informs its decision in round 7 beyond one prompt of chatter. Plan 6 adds the memory
platform: agents **record** what happened to them and what they concluded, and **retrieve**
the relevant pieces into every decision prompt.

The invariant is unchanged: **the LLM proposes, the domain decides, the engine executes,
events record.** Memory never becomes game truth (§10): it shapes prompts, never state.
Nothing in this plan touches `src/domain/`. Memory failures never fail a turn.

## 2. Decisions

1. **Port-first architecture (Approach A).** Memory gets the Plan 3 treatment: a game-free
   platform layer (`src/ai/memory/`) owning the value types and ports, an application
   policy service (`src/application/memory/`), and swappable infrastructure backends
   (in-memory, pgvector). Memory is an AI-platform concept reusable beyond D&D (§7);
   flattening it into the game layer was rejected.
2. **Real provider embeddings — the one sanctioned carve-out.** `[profiles.embedding]`
   becomes `openai/text-embedding-3-small` via OpenRouter's embeddings endpoint
   (`POST /api/v1/embeddings`, OpenAI-compatible): same provider, same
   `OPENROUTER_API_KEY`, no new account. **Explicit user decision 2026-09-06**, overriding
   the standing all-profiles-glm-5.3-flash directive for this one profile (§72: explicit
   user requirements first); all chat profiles stay `z-ai/glm-5.3-flash`. glm-5.3-flash is
   a chat model and cannot produce embeddings at all.
3. **A separate `EmbeddingGateway` port.** Additive to the platform: `ModelGateway` and
   every existing implementer (fake, scripted, OpenRouter) stay untouched. `embed()` is a
   new method on the OpenRouter adapter (it already owns the key, base URL, httpx, and
   error mapping). Offline runs use a deterministic stdlib embedder behind the same port.
4. **EPISODIC and SEMANTIC persist; WORKING is the prompt itself.** Per turn, working
   memory is the perception + party chatter + retrieved memories already assembled into
   the prompt — persisting it would duplicate what the loop rebuilds anyway. Persisted
   rows carry a `kind` of `episodic` or `semantic`.
5. **Semantic memory = the model's note-to-self.** The decision schema gains an optional
   `memory_note` string (≤200 chars, same defensive mapping as `party_message`): on
   accepted model turns the agent may write one short durable fact ("the orc hits hard —
   stay at range"). Omitting it is silence, never a rejection.
6. **Episodic memory = deterministic derivation from domain events.** The accepted turn's
   `AttackResolved` / `DamageApplied` / `CharacterDefeated` events (payloads carry
   `attacker_id`, `target_id`, `character_id`, `amount`, `hit`, `critical` as plain
   strings/numbers) render one line: "Round 3: attacked Goblin Scout and dealt 5 damage",
   "...and missed", "... (critical)", "; Goblin Scout fell". Names resolve through the
   perception (opponents of the actor); unknown ids fall back to the raw id string.
   Damage is attributed by summing `DamageApplied` events whose `character_id` matches
   the attack's `target_id` (the enemy chain that follows the actor's turn also appears
   in the same `TurnReport.events`, but enemy attacks only ever target party members,
   so this attribution is exact for the supported action set).
   No attack event → no episodic record. Enemy-turn memories (remembering *being*
   attacked) are deferred.
7. **Storage shape: untyped `vector`, no ANN index, embeddings NOT NULL.** The pgvector
   column has no typmod, so a future embedding-model swap needs no migration; a game
   produces tens of memories, so sequential scan with cosine distance is instant (§51).
   A memory that fails to embed is never written — every stored row is searchable.
   Exact-duplicate suppression: the same (game, agent, kind, text) is not re-appended.
   Memories are scoped per (game_id, agent_key) — agent-specific (§21), party members
   share nothing automatically.
8. **Memory is an enhancement, never a gate.** Retrieval failure → the turn proceeds with
   no memories (the failed embed's invocation still reaches telemetry). Recording failure
   → the accepted action stands and the write is dropped (telemetry only). Only
   `ModelError` and `PersistenceError` are swallowed; anything else is a bug and
   propagates. Memory can never reject a turn or mutate state (§28, §66).
9. **Offline discipline unchanged.** `--agent fake` uses the deterministic embedder and
   never touches the network (§46). The pgvector repository is tested offline against
   pgserver — verified to ship pgvector 0.6.2 — so CI needs no keys and no external
   database. Real-embedding determinism is not assumed (§47): retrieval only shapes
   prompts, so engine determinism is unaffected either way.
10. **Observability without exposure (§34).** Embedding calls produce the standard
    `LLMInvocation(operation="embed")`; `AgentTurnReport` gains `memory_retrieved: int`.
    Memory **contents** are never logged and never displayed outside the owning agent's
    own prompt (§20: they are the agent's private context).

## 3. Components

### 3.1 `src/ai/memory/` — new platform layer, game-free

```python
# types.py
class MemoryKind(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"

@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str                 # uuid4 hex
    game_id: str
    agent_key: str                 # character id as string — keeps ai/ game-free
    kind: MemoryKind
    text: str
    round_number: int | None
    embedding: tuple[float, ...]   # NOT NULL by policy: embed before append

@dataclass(frozen=True)
class EmbeddingRequest:
    texts: tuple[str, ...]         # batch: one call embeds all inputs
    model: str
    timeout_seconds: float = 60.0

@dataclass(frozen=True)
class EmbeddingResponse:
    vectors: tuple[tuple[float, ...], ...]   # parallel to texts
    usage: Usage                             # from ai.models.types
    invocation: LLMInvocation                # operation="embed"

# ports.py
class EmbeddingGateway(Protocol):
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...

class MemoryRepository(Protocol):
    def append(self, record: MemoryRecord) -> None: ...
    def search(self, game_id: str, agent_key: str,
               query: tuple[float, ...], limit: int) -> tuple[MemoryRecord, ...]: ...
```

`search` returns the most-similar records first (cosine), scoped to the
(game, agent) pair. `limit <= 0` → `()`. `Usage`/`LLMInvocation` are imported from
`ai.models.types` — the embedding port shares the model platform's telemetry types.

```python
# fake.py — DeterministicEmbeddingGateway (offline / --agent fake)
# stdlib only: tokenize (lowercased words), hash each word into a fixed
# 256-dim bucket vector (deterministic hash, e.g. blake2b of the word),
# accumulate, L2-normalize. Deterministic across runs; cosine ranking
# reflects word overlap, so retrieval tests can assert relevance order.
class DeterministicEmbeddingGateway:
    DIM = 256
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...
```

### 3.2 `src/infrastructure/memory/` — two backends + the OpenRouter embed

```python
# in_memory.py — InMemoryMemoryRepository: list of records, pure-python cosine
# (stdlib math), most-similar first. Same append/search contract as pgvector.

# pgvector_repository.py — PgvectorMemoryRepository(connection):
#   append:  INSERT INTO agent_memories (memory_id, game_id, agent_key, kind, text,
#            round_number, embedding) VALUES (...::uuid, ..., %s::vector)
#   search:  SELECT ... FROM agent_memories
#            WHERE game_id = %s::uuid AND agent_key = %s
#            ORDER BY embedding <=> %(query)s::vector LIMIT %s
# psycopg errors wrap into the existing PersistenceError (same as game repos).
```

`OpenRouterModelGateway` gains `embed()` (same class — it already owns auth, base URL,
httpx, timeout, error mapping, and cost): POST `{base_url}/embeddings` with
`{"model", "input": [texts]}`; parses `data[].embedding` (validates list-of-floats and
count == len(texts)); `operation="embed"`; usage from the response's `usage.prompt_tokens`;
cost via the existing per-model pricing table (input tokens only). All existing error
mapping applies unchanged (429 → `ModelRateLimitedError`, 4xx → `ModelRequestError`,
5xx → `ModelUnavailableError`, non-JSON → `ModelInvalidResponseError`).

### 3.3 `src/application/memory/memory_service.py` — new: the policy layer

```python
class MemoryService:
    def __init__(self, gateway: EmbeddingGateway, repository: MemoryRepository, *,
                 model: str, retrieval_limit: int = 5) -> None: ...

    def retrieve(self, game_id: str, perception: AgentPerception) -> tuple[MemoryRecord, ...]:
        """Embed a situation line, search the agent's memories, top-k most relevant."""

    def record_turn(self, game_id: str, perception: AgentPerception,
                    turn_report: TurnReport, *, note: str | None = None) -> None:
        """Derive episodic text from turn_report.events; semantic from note;
        batch-embed (one call); append with dedup. Rejected turns write nothing."""
```

(Plan-writing refinement, 2026-09-06: `model` is a required argument because
`EmbeddingRequest` needs a model id and `MemoryService` is the only embed caller;
`game_id` is an explicit argument because `AgentPerception` carries no game id;
`record_turn` takes the note as a plain string rather than the whole `AgentDecision`
so the fallback path — which has no decision — can record episodic memory too.)

- Query text (retrieval): `"{name} the {class}; round {n}; opponents: {names}"` —
  built from the perception only (§20: no hidden state).
- Episodic derivation is deterministic event→text rendering (Decision 6); semantic text
  is the note verbatim.
- `record_turn` embeds **all** new texts in one batch call. Duplicate suppression
  (same game, agent, kind, text) is the repository's concern: `append` becomes a no-op
  for exact duplicates (in-memory: a seen-set; pgvector: an existence check).
- Sync methods bridging the async gateway via `asyncio.run` — the established pattern
  (`AgentRuntime.decide_structured` does the same).

### 3.4 `src/application/agents/character_agent.py` — the memory_note field

```python
ATTACK_DECISION_SCHEMA: ... = {
    "properties": {
        ...,
        "party_message": {"type": "string"},
        "memory_note": {"type": "string"},   # optional — NOT in required
    },
    "required": ["action_type", "target_id", "public_message"],
}

@dataclass(frozen=True)
class AgentDecision:
    ...                                   # unchanged Plan 5 fields
    memory_note: str | None = None        # NEW
```

Mapping rules for `memory_note` (defensive, never a rejection): missing/empty/
whitespace-only → `None`; otherwise strip, collapse internal newlines to spaces,
truncate to 200 characters. The system prompt gains one line: the agent *may* include
`memory_note` — one short durable fact worth remembering for later rounds — and may
omit it. `build_user_prompt(perception, *, rejection=None, party_messages=(),
memories=())` renders a "Memories:" section when memories exist, most-relevant first,
as `- [episodic] {text}` / `- [semantic] {text}` — placed after the Party chatter block.

### 3.5 `src/application/agents/agent_turn_service.py` — memory in the loop

```python
class AgentTurnService:
    def __init__(self, ..., *, board=None, memory: MemoryService | None = None): ...

@dataclass(frozen=True)
class AgentTurnReport:
    ...                                   # unchanged Plan 5 fields
    memory_retrieved: int = 0             # NEW — §34 memory retrieval count
```

`take_turn` changes are three injections into the unchanged Plan 4/5 flow:

1. **Hoist the perception.** The view + perception build moves **out** of the retry
   loop, to the top of `take_turn`. Behavior-preserving: rejected actions never mutate
   state (§28), so every attempt previously rebuilt an identical perception. Retrieval
   then happens once per turn, not once per attempt (one embed call per turn, not per
   retry).
2. **Read:** `memory.retrieve(perception)` → memories pass into every `build_user_prompt`
   call of the loop. Failure (only `ModelError` / `PersistenceError`) → empty tuple;
   a failed embed's invocation, if any, still appends to the report's invocations.
3. **Write:** only after an **accepted** turn — model or fallback:
   `memory.record_turn(game_id, perception, turn_report, note=decision.memory_note)`
   (the fallback path passes `note=None`) — same swallow-policy.
   Episodic memory always records (it is derived from the executed turn's events, not
   from the model's words — a fallback attack is still the agent's experience); semantic
   records only when the accepted model decision carries a note, so rejected attempts
   and fallback turns (which have no decision) write episodic only.

`memory=None` (default) reproduces Plan 5 behavior exactly — every existing test and
call site untouched.

### 3.6 Wiring: `src/interfaces/cli/app.py`, `config/llm.toml`, migration

- **`config/llm.toml`**: `[profiles.embedding]` → `model = "openai/text-embedding-3-small"`,
  plus a `[pricing."openai/text-embedding-3-small"]` entry (`input_per_million_usd = 0.02`,
  `output_per_million_usd = 0.0`). Comment documents the sanctioned carve-out (Decision 2).
- **Migration `002_agent_memories.sql`**:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE agent_memories (
    memory_id    UUID PRIMARY KEY,
    game_id      UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    agent_key    TEXT NOT NULL,
    kind         TEXT NOT NULL,
    text         TEXT NOT NULL,
    round_number INTEGER,
    embedding    vector NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX agent_memories_agent_idx ON agent_memories (game_id, agent_key);
```

  Applied by the existing runner (`run_migrations` in `build_service("postgres")` and
  the pgserver test fixture automatically pick it up). A real PostgreSQL without the
  `vector` extension available fails the migration with the existing `PersistenceError`
  — README documents the requirement (pgserver ships the extension).
- **CLI mode matrix (orthogonal wiring: embedder by agent mode, store by db flag):**

| mode | embedder | memory store |
|---|---|---|
| `--agent llm` (any `--db`) | `OpenRouterModelGateway` (real embeddings) | by `--db` |
| `--agent fake` | `DeterministicEmbeddingGateway` (offline) | by `--db` |
| `--agent off` | none | none |

  `--db memory` → `InMemoryMemoryRepository`; `--db postgres` →
  `PgvectorMemoryRepository(connect(DATABASE_URL))` — a second connection owned by the
  memory repo (the game repos keep theirs; a CLI process needs no pooling).
  `_wire_party` constructs the `MemoryService` and passes it to `AgentTurnService`.
  The fake-mode scripted decision gains `"memory_note": "The orc hits hard; stay at range."`
  so the offline demo exercises the full record→retrieve path.

### 3.7 Data flow (per agent turn — Plan 4/5 pipeline plus memory)

```text
Observe (hoisted) → memory.retrieve → prompt (perception + chatter + memories) → LLM
  → structured decision (attack + optional say + optional note) → map/validate
  → rules engine → events → if accepted: board.post + memory.record_turn
                                        (embed → append episodic/semantic)
```

## 4. Failure-mode table

| Failure | Where | Behavior |
|---|---|---|
| Embed down/429/timeout during retrieval | `MemoryService.retrieve` → service | turn proceeds with **no memories**; failed invocation still in telemetry |
| Embed/repo failure during recording | `MemoryService.record_turn` → service | accepted action stands; write dropped; telemetry only |
| `memory_note` wrong type | gateway schema | `ModelInvalidResponseError` → transport retry (existing path) |
| `memory_note` empty/whitespace | decision mapping | silently `None` — no retry |
| `memory_note` > 200 chars or multi-line | decision mapping | truncated/collapsed — no retry |
| Identical memory re-written | repository append | suppressed (exact-duplicate no-op) |
| Agent without `MemoryService` (`memory=None`) | service | Plan 5 behavior exactly; no memory code runs |
| Real postgres lacks `vector` extension | migration | `PersistenceError` at startup with a clear message; README documents the requirement |
| Dimension change (future model swap) | storage | untyped `vector` column accepts any dimension; no migration needed |
| Memory contents in logs/CLI | prohibited | only counts (`memory_retrieved`) leave the owning agent's prompt (§20, §34) |

## 5. Testing

No real LLM in CI (§46); `asyncio.run` bridging; stdlib-only; no domain changes.
New/updated tests:

- `tests/ai/memory/test_embedding_types.py` — request/response/record invariants
  (frozen, parallel vectors/texts, `MemoryKind` values).
- `tests/ai/memory/test_deterministic_embedding.py` — deterministic across calls;
  fixed 256 dims; L2-normalized (unit length); identical texts → identical vectors;
  lexically-overlapping texts rank closer than unrelated ones.
- `tests/ai/memory/test_purity.py` — `src/ai/memory/` imports nothing from
  application/domain/infrastructure (extends the `src/ai/agents` purity guarantee).
- `tests/application/memory/test_memory_service.py` — episodic derivation (hit / miss /
  critical / defeat / no-attack-event); semantic note verbatim; batch embed (one call for
  both texts); retrieval limit; retrieval embeds the perception-derived query; duplicate
  suppression end-to-end.
- `tests/infrastructure/memory/test_in_memory_repository.py` — append/search ordering by
  cosine; (game, agent) scoping; `limit <= 0` → `()`; duplicate no-op.
- `tests/infrastructure/memory/test_pgvector_repository.py` — same contract against
  pgserver (offline, extension verified present): insert + cosine-ordered search across
  rows, scoping, duplicate no-op, persistence semantics.
- `tests/infrastructure/llm/test_openrouter_embed.py` — httpx MockTransport: happy path
  (parallel vectors, usage, `operation="embed"` invocation), 429 with retry-after,
  5xx, invalid body, count-mismatched `data`, non-float embeddings.
- `tests/application/agents/test_character_agent.py` — schema: `memory_note` optional
  (absent passes, present passes, wrong type fails); mapping: empty→None, truncate 200,
  newline collapse; prompt: Memories section renders kind + text, most-relevant first,
  omitted when empty.
- `tests/application/agents/test_agent_turn_service.py` — memories appear in the agent's
  prompt; accepted model turn records episodic (+ semantic when a note is present);
  accepted fallback turn records episodic only; rejected attempts record nothing; embed
  failure → turn still completes with zero memories; `memory_retrieved` populated;
  perception hoisting preserves all Plan 5 retry/fallback behavior (existing tests must
  pass unchanged in spirit).
- `tests/integration/test_openrouter_live.py` — one live embed smoke (skips without
  `OPENROUTER_API_KEY`): real round-trip returns one non-empty float vector.

## 6. Non-goals (deferred)

- Decay, forgetting, and consolidation (episodic→semantic summarization via LLM).
- Cross-game semantic memory ("I distrust orcs" surviving the session).
- WORKING-memory persistence; memory writes for enemy turns / GM turns.
- ANN indexing (HNSW/IVFFlat) — tens of rows per game need a sequential scan only (§51).
- Memory contents in CLI output, debug views, or logs.
- GM agent, new actions, FastAPI (Phases 7/11 per CLAUDE.md order).
- Any change to `src/domain/`, dice, combat math, or event types.

## 7. Global constraints

- Domain layer untouched (`git log master..HEAD -- src/domain` stays empty);
  `src/ai/memory/` game-free (new purity test).
- Provider names and model ids only under `src/infrastructure/llm/` and as config values
  in `config/*.toml`. The single config carve-out is `[profiles.embedding]` =
  `openai/text-embedding-3-small` (explicit user decision 2026-09-06); every chat profile
  stays `z-ai/glm-5.3-flash`.
- stdlib-only implementation (hashlib, math, asyncio, dataclasses, enum); pgvector usage
  is plain SQL over the existing psycopg connection — **no new runtime dependencies**.
- Secrets from environment only (`OPENROUTER_API_KEY`, `DATABASE_URL`); never committed
  or logged. No private chain-of-thought requested, displayed, or persisted (§33); agent
  memories are private context and never leave the owning agent's prompt (§20, §34).
- Offline suite green without `OPENROUTER_API_KEY` or `DATABASE_URL`; pgvector tests run
  against pgserver (no external database). Memory failures never fail a turn or mutate
  state.
- mypy strict, ruff clean, pytest green at every task boundary; conventional commits
  scoped by layer with the Co-Authored-By trailer.

## 8. Completion checklist

- [ ] `src/domain/` has zero diff vs `master`; `src/ai/memory/` purity test passes.
- [ ] `EmbeddingGateway` and `MemoryRepository` are the only memory seams; no consumer
      imports psycopg, httpx, or provider names outside infrastructure.
- [ ] Memories enter prompts only through `build_user_prompt(memories=...)`; writes
      happen only after accepted model turns; memory failures never fail a turn.
- [ ] `--agent fake` remains fully offline (deterministic embedder, no network).
- [ ] pgvector repository proven against pgserver offline, including the migration.
- [ ] Duplicate memories suppressed; every stored row is embedded (NOT NULL policy).
- [ ] `memory_retrieved` observable; no memory text in logs, CLI output, or telemetry.
- [ ] Full suite green offline without `OPENROUTER_API_KEY` or `DATABASE_URL`.
- [ ] No new runtime dependencies; no provider SDK outside infrastructure.
