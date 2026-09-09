-- 003_llm_invocations.sql — per-call LLM telemetry (Phase 17, spec §3.4).
-- Id columns are TEXT, not UUID: fake gateways use ids like uuid4().hex and
-- scripted ids like req-0001, which a UUID PRIMARY KEY can neither be NULL
-- for nor hold. Telemetry must never fail the game (spec §4).
CREATE TABLE llm_invocations (
    request_id         TEXT PRIMARY KEY,
    game_id            TEXT,
    agent_id           TEXT,
    correlation_id     TEXT,
    provider           TEXT NOT NULL,
    model              TEXT NOT NULL,
    operation          TEXT NOT NULL,
    status             TEXT NOT NULL,
    error_kind         TEXT,
    latency_ms         INTEGER,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    estimated_cost_usd NUMERIC(12, 6),
    attempt            INTEGER NOT NULL DEFAULT 1,
    retrieval_count    INTEGER NOT NULL DEFAULT 0,
    tools_called       INTEGER NOT NULL DEFAULT 0,
    timestamp          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX llm_invocations_game_idx ON llm_invocations (game_id);
CREATE INDEX llm_invocations_correlation_idx ON llm_invocations (correlation_id);
