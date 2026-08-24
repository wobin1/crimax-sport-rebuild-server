-- Client-generated event IDs make live-entry retries safe.

ALTER TABLE match_events
    ADD COLUMN IF NOT EXISTS client_event_id VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_match_events_client_event
    ON match_events (fixture_id, client_event_id)
    WHERE client_event_id IS NOT NULL;
