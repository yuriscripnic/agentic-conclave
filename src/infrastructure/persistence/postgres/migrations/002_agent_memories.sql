-- 002_agent_memories.sql — agent memory store for the Plan 6 memory platform.
-- Untyped vector column (no typmod): switching embedding models never
-- requires a migration; dimension mismatches surface at query time.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE agent_memories (
    memory_id    UUID PRIMARY KEY,
    game_id      UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    agent_key    TEXT NOT NULL,
    kind         TEXT NOT NULL,
    text         TEXT NOT NULL,
    round_number INTEGER,
    embedding    VECTOR NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX agent_memories_scope_idx ON agent_memories (game_id, agent_key);

-- Append-only by construction: no code path issues UPDATE or DELETE here.
