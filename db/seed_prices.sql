INSERT INTO model_prices (provider, model, input_per_mtok, output_per_mtok) VALUES
    ('anthropic', 'claude-haiku-4-5-20251001', 1.00, 5.00),
    ('openai',    'gpt-4.1-nano',              0.10, 0.40),
    ('gemini',    'gemini-3.5-flash-lite',     0.30, 2.50);
cat >> db/seed_prices.sql << 'EOF'

INSERT INTO model_prices (provider, model, input_per_mtok, output_per_mtok)
VALUES ('openai', 'text-embedding-3-small', 0.02, 0);
