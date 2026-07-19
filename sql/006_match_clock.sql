-- Match period clock for live fixtures (international 1H / HT / 2H / FT model)

ALTER TABLE fixtures
    ADD COLUMN IF NOT EXISTS period VARCHAR(20)
        CHECK (period IS NULL OR period IN (
            'first_half', 'half_time', 'second_half', 'full_time'
        )),
    ADD COLUMN IF NOT EXISTS period_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS period_base_minute SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS stoppage_minutes SMALLINT;

COMMENT ON COLUMN fixtures.period IS 'Match period: first_half, half_time, second_half, full_time';
COMMENT ON COLUMN fixtures.period_started_at IS 'When the current ticking period started (null when paused)';
COMMENT ON COLUMN fixtures.period_base_minute IS 'Displayed minute at period_started_at (0 for 1H, 45 for 2H, or admin nudge)';
COMMENT ON COLUMN fixtures.stoppage_minutes IS 'Announced stoppage for the current half (optional)';
