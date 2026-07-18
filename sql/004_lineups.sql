-- Formation lineups (per fixture, per club)
-- Hybrid model: named formation slots + soft offset_x/offset_y within each slot

CREATE TABLE IF NOT EXISTS fixture_lineups (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    fixture_id  UUID        NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    club_id     UUID        NOT NULL REFERENCES clubs(id)    ON DELETE CASCADE,
    formation   VARCHAR(20) NOT NULL,
    updated_by  UUID        REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (fixture_id, club_id)
);

CREATE TABLE IF NOT EXISTS fixture_lineup_players (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    lineup_id   UUID        NOT NULL REFERENCES fixture_lineups(id) ON DELETE CASCADE,
    player_id   UUID        NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    slot_key    VARCHAR(20) NOT NULL,
    is_starter  BOOLEAN     NOT NULL DEFAULT TRUE,
    offset_x    REAL        NOT NULL DEFAULT 0
                CHECK (offset_x BETWEEN -12 AND 12),
    offset_y    REAL        NOT NULL DEFAULT 0
                CHECK (offset_y BETWEEN -12 AND 12),
    UNIQUE (lineup_id, slot_key),
    UNIQUE (lineup_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_lineups_fixture ON fixture_lineups(fixture_id);
CREATE INDEX IF NOT EXISTS idx_lineups_club    ON fixture_lineups(club_id);
CREATE INDEX IF NOT EXISTS idx_lineup_players  ON fixture_lineup_players(lineup_id);

CREATE OR REPLACE TRIGGER trg_fixture_lineups_updated_at
    BEFORE UPDATE ON fixture_lineups
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
