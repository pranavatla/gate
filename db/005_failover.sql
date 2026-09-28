CREATE TABLE IF NOT EXISTS fallback_routes (
    primary_model   TEXT NOT NULL,
    priority        INTEGER NOT NULL,
    fallback_model  TEXT NOT NULL,
    PRIMARY KEY (primary_model, priority)
);

ALTER TABLE usage_events
    ADD COLUMN IF NOT EXISTS attempted_models TEXT[];

INSERT INTO fallback_routes (primary_model, priority, fallback_model) VALUES
    ('anthropic/claude-haiku-4-5-20251001', 1, 'openai/gpt-4.1-nano'),
    ('anthropic/claude-haiku-4-5-20251001', 2, 'gemini/gemini-3.5-flash-lite'),
    ('openai/gpt-4.1-nano',                 1, 'gemini/gemini-3.5-flash-lite'),
    ('openai/gpt-4.1-nano',                 2, 'anthropic/claude-haiku-4-5-20251001'),
    ('gemini/gemini-3.5-flash-lite',        1, 'openai/gpt-4.1-nano'),
    ('gemini/gemini-3.5-flash-lite',        2, 'anthropic/claude-haiku-4-5-20251001')
ON CONFLICT DO NOTHING;
