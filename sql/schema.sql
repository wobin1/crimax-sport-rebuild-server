-- =============================================================================
-- Crimax Sports — Master Database Schema
-- PostgreSQL 16
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- =============================================================================
-- USERS
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),          -- null until invite accepted
    full_name     VARCHAR(255) NOT NULL,
    role          VARCHAR(20)  NOT NULL CHECK (role IN ('super_admin', 'platform_admin', 'club_manager')),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- INVITES  (pending staff invitations)
-- =============================================================================

CREATE TABLE IF NOT EXISTS invites (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email       VARCHAR(255) NOT NULL,
    full_name   VARCHAR(255) NOT NULL,
    role        VARCHAR(20)  NOT NULL
                    CHECK (role IN ('super_admin', 'platform_admin', 'club_manager')),
    club_ids    UUID[]       NOT NULL DEFAULT '{}',
    token_hash  VARCHAR(64)  NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ  NOT NULL,
    invited_by  UUID         REFERENCES users(id) ON DELETE SET NULL,
    accepted_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invites_email ON invites (email);
CREATE INDEX IF NOT EXISTS idx_invites_pending
    ON invites (accepted_at)
    WHERE accepted_at IS NULL;


-- =============================================================================
-- CLUBS
-- =============================================================================

CREATE TABLE IF NOT EXISTS clubs (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(255) UNIQUE NOT NULL,
    short_name   VARCHAR(10),
    logo_url     TEXT,
    home_ground  VARCHAR(255),
    founded_year SMALLINT,
    description  TEXT,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- CLUB MANAGERS  (user ↔ club assignment)
-- =============================================================================

CREATE TABLE IF NOT EXISTS club_managers (
    user_id  UUID NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    club_id  UUID NOT NULL REFERENCES clubs(id)  ON DELETE CASCADE,
    PRIMARY KEY (user_id, club_id)
);


-- =============================================================================
-- PLAYERS
-- =============================================================================

CREATE TABLE IF NOT EXISTS players (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    club_id        UUID        REFERENCES clubs(id) ON DELETE SET NULL,
    full_name      VARCHAR(255) NOT NULL,
    position       VARCHAR(20)  CHECK (position IN ('goalkeeper', 'defender', 'midfielder', 'forward')),
    jersey_number  SMALLINT,
    date_of_birth  DATE,
    nationality    VARCHAR(100) NOT NULL DEFAULT 'Nigerian',
    photo_url      TEXT,
    height_cm      SMALLINT,
    preferred_foot VARCHAR(10)  CHECK (preferred_foot IS NULL OR preferred_foot IN ('left', 'right', 'both')),
    bio            TEXT,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- TOURNAMENTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS tournaments (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    season      VARCHAR(50)  NOT NULL,
    description TEXT,
    start_date  DATE,
    end_date    DATE,
    status      VARCHAR(20)  NOT NULL DEFAULT 'upcoming'
                CHECK (status IN ('upcoming', 'active', 'completed')),
    logo_url    TEXT,
    is_current  BOOLEAN      NOT NULL DEFAULT FALSE,
    ruleset     JSONB        NOT NULL DEFAULT '{"preset":"grassroots"}'::jsonb,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- TOURNAMENT CLUBS  (which clubs participate in a tournament)
-- =============================================================================

CREATE TABLE IF NOT EXISTS tournament_clubs (
    tournament_id UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    club_id       UUID NOT NULL REFERENCES clubs(id)       ON DELETE CASCADE,
    PRIMARY KEY (tournament_id, club_id)
);


-- =============================================================================
-- FIXTURES
-- =============================================================================

CREATE TABLE IF NOT EXISTS fixtures (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id UUID        NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    home_club_id  UUID        NOT NULL REFERENCES clubs(id),
    away_club_id  UUID        NOT NULL REFERENCES clubs(id),
    match_date    DATE        NOT NULL,
    match_time    TIME,
    venue         VARCHAR(255),
    round         VARCHAR(100),
    status        VARCHAR(20)  NOT NULL DEFAULT 'scheduled'
                  CHECK (status IN ('scheduled', 'live', 'completed', 'postponed', 'cancelled')),
    home_score    SMALLINT     NOT NULL DEFAULT 0,
    away_score    SMALLINT     NOT NULL DEFAULT 0,
    -- Match clock (international period model)
    period              VARCHAR(20)
                        CHECK (period IS NULL OR period IN (
                            'first_half', 'half_time', 'second_half', 'full_time'
                        )),
    period_started_at   TIMESTAMPTZ,
    period_base_minute  SMALLINT     NOT NULL DEFAULT 0,
    stoppage_minutes    SMALLINT,
    ruleset_snapshot    JSONB,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT no_self_match CHECK (home_club_id != away_club_id)
);


-- =============================================================================
-- MATCH EVENTS  (goals, cards, subs — source of truth for live scores)
-- =============================================================================

CREATE TABLE IF NOT EXISTS match_events (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    fixture_id        UUID        NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    client_event_id   VARCHAR(64),
    source_event_id   UUID        REFERENCES match_events(id) ON DELETE CASCADE,
    player_id         UUID        REFERENCES players(id) ON DELETE SET NULL,
    assist_player_id  UUID        REFERENCES players(id) ON DELETE SET NULL,
    club_id           UUID        REFERENCES clubs(id)   ON DELETE SET NULL,
    event_type        VARCHAR(30)  NOT NULL
                      CHECK (event_type IN (
                          'goal', 'own_goal',
                          'yellow_card', 'red_card',
                          'substitution_in', 'substitution_out',
                          'penalty_scored', 'penalty_missed'
                      )),
    minute            SMALLINT     NOT NULL,
    extra_time_minute SMALLINT,
    description       TEXT,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_match_events_client_event
    ON match_events (fixture_id, client_event_id)
    WHERE client_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_match_events_source
    ON match_events (source_event_id);


-- =============================================================================
-- AUDIT LOG  (append-only operational history)
-- =============================================================================

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


-- =============================================================================
-- FIXTURE LINEUPS  (formation + starting XI per club per match)
-- =============================================================================

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


-- =============================================================================
-- NEWS
-- =============================================================================

CREATE TABLE IF NOT EXISTS news (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    title        VARCHAR(500) NOT NULL,
    slug         VARCHAR(500) UNIQUE NOT NULL,
    content      TEXT         NOT NULL,
    excerpt      TEXT,
    image_url    TEXT,
    author_id    UUID        REFERENCES users(id) ON DELETE SET NULL,
    is_published BOOLEAN      NOT NULL DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- EXTERNAL IDS  (provider identity map; internal UUIDs stay primary)
-- =============================================================================

CREATE TABLE IF NOT EXISTS external_ids (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type  VARCHAR(30)  NOT NULL
                   CHECK (entity_type IN (
                       'club', 'player', 'fixture', 'tournament', 'user'
                   )),
    entity_id    UUID         NOT NULL,
    provider     VARCHAR(50)  NOT NULL,
    external_id  VARCHAR(255) NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (provider, entity_type, external_id),
    UNIQUE (provider, entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_external_ids_entity
    ON external_ids (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_external_ids_lookup
    ON external_ids (provider, entity_type, external_id);


-- =============================================================================
-- REFRESH TOKENS  (rotation / revocation store)
-- =============================================================================

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash   VARCHAR(64)  NOT NULL UNIQUE,
    expires_at   TIMESTAMPTZ  NOT NULL,
    revoked_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user
    ON refresh_tokens (user_id)
    WHERE revoked_at IS NULL;


-- =============================================================================
-- AUTH TOKENS  (password reset)
-- =============================================================================

CREATE TABLE IF NOT EXISTS auth_tokens (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose     VARCHAR(32)  NOT NULL,
    token_hash  VARCHAR(64)  NOT NULL,
    expires_at  TIMESTAMPTZ  NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_tokens_hash ON auth_tokens (token_hash);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_purpose ON auth_tokens (user_id, purpose);


-- =============================================================================
-- INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_players_club         ON players(club_id);
CREATE INDEX IF NOT EXISTS idx_players_active        ON players(is_active);

CREATE INDEX IF NOT EXISTS idx_fixtures_tournament   ON fixtures(tournament_id);
CREATE INDEX IF NOT EXISTS idx_fixtures_date         ON fixtures(match_date);
CREATE INDEX IF NOT EXISTS idx_fixtures_status       ON fixtures(status);
CREATE INDEX IF NOT EXISTS idx_fixtures_round        ON fixtures(round);

CREATE INDEX IF NOT EXISTS idx_events_fixture        ON match_events(fixture_id);
CREATE INDEX IF NOT EXISTS idx_events_type           ON match_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_assist         ON match_events(assist_player_id);

CREATE INDEX IF NOT EXISTS idx_news_published        ON news(is_published, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_slug             ON news(slug);

CREATE INDEX IF NOT EXISTS idx_tournament_clubs_t    ON tournament_clubs(tournament_id);
CREATE INDEX IF NOT EXISTS idx_tournament_clubs_c    ON tournament_clubs(club_id);

CREATE INDEX IF NOT EXISTS idx_lineups_fixture       ON fixture_lineups(fixture_id);
CREATE INDEX IF NOT EXISTS idx_lineups_club          ON fixture_lineups(club_id);
CREATE INDEX IF NOT EXISTS idx_lineup_players        ON fixture_lineup_players(lineup_id);


-- =============================================================================
-- UPDATED_AT TRIGGER  (auto-update updated_at on any row change)
-- =============================================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE TRIGGER trg_clubs_updated_at
    BEFORE UPDATE ON clubs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE TRIGGER trg_players_updated_at
    BEFORE UPDATE ON players
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE TRIGGER trg_tournaments_updated_at
    BEFORE UPDATE ON tournaments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE TRIGGER trg_fixtures_updated_at
    BEFORE UPDATE ON fixtures
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE TRIGGER trg_news_updated_at
    BEFORE UPDATE ON news
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE TRIGGER trg_fixture_lineups_updated_at
    BEFORE UPDATE ON fixture_lineups
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
