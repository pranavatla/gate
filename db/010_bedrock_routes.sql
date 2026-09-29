INSERT INTO fallback_routes (primary_model, priority, fallback_model)
SELECT 'bedrock/global.amazon.nova-2-lite-v1:0', 1, 'gemini/gemini-3.5-flash-lite'
WHERE NOT EXISTS (
    SELECT 1 FROM fallback_routes
    WHERE primary_model = 'bedrock/global.amazon.nova-2-lite-v1:0'
      AND fallback_model = 'gemini/gemini-3.5-flash-lite'
);
