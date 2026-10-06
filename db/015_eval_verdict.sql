ALTER TABLE eval_runs
    ADD COLUMN IF NOT EXISTS verdict         TEXT,
    ADD COLUMN IF NOT EXISTS verdict_detail  JSONB,
    ADD COLUMN IF NOT EXISTS baseline_score  NUMERIC(5,4),
    ADD COLUMN IF NOT EXISTS checked_at      TIMESTAMPTZ;