-- Add assist_player_id to match_events for tracking goal assists
ALTER TABLE match_events
  ADD COLUMN IF NOT EXISTS assist_player_id UUID REFERENCES players(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_events_assist ON match_events(assist_player_id);
