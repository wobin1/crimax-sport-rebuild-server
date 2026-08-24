-- Append-only operational audit trail.
-- Application code intentionally exposes INSERT only.

CREATE TABLE IF NOT EXISTS audit_log (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id  UUID         REFERENCES users(id) ON DELETE SET NULL,
    actor_role     VARCHAR(20),
    action         VARCHAR(50)  NOT NULL,
    entity_type    VARCHAR(30)  NOT NULL,
    entity_id      UUID,
    fixture_id     UUID         REFERENCES fixtures(id) ON DELETE SET NULL,
    club_id        UUID         REFERENCES clubs(id) ON DELETE SET NULL,
    before_data    JSONB,
    after_data     JSONB,
    reason         TEXT,
    ruleset        JSONB,
    request_id     TEXT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_fixture_created
    ON audit_log (fixture_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor_created
    ON audit_log (actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_entity
    ON audit_log (entity_type, entity_id);
