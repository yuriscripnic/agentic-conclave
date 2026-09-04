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
