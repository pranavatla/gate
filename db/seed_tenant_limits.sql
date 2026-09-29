UPDATE tenants
SET rpm_limit = 60, tpm_limit = 20000,
    monthly_budget_usd = 5, downgrade_model = NULL
WHERE name = 'gita';

UPDATE tenants
SET rpm_limit = 10, tpm_limit = 5000,
    monthly_budget_usd = 1, downgrade_model = NULL
WHERE name = 'atla-chatbot';
