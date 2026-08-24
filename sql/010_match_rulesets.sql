-- Tournament-configurable match rules, frozen per fixture at kickoff.

ALTER TABLE tournaments
    ADD COLUMN IF NOT EXISTS ruleset JSONB NOT NULL
        DEFAULT '{"preset":"grassroots"}'::jsonb;

ALTER TABLE fixtures
    ADD COLUMN IF NOT EXISTS ruleset_snapshot JSONB;

ALTER TABLE match_events
    ADD COLUMN IF NOT EXISTS source_event_id UUID
        REFERENCES match_events(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_match_events_source
    ON match_events (source_event_id);
