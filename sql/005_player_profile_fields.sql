-- Optional player profile fields
ALTER TABLE players
  ADD COLUMN IF NOT EXISTS height_cm      SMALLINT,
  ADD COLUMN IF NOT EXISTS preferred_foot VARCHAR(10)
    CHECK (preferred_foot IS NULL OR preferred_foot IN ('left', 'right', 'both')),
  ADD COLUMN IF NOT EXISTS bio            TEXT;
