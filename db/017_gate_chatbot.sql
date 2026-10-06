-- The gate.atla.in page chatbot is an internal tenant. This only makes sure its row exists;
-- limits, policy and the failover chain are applied at every gateway startup from app/chatbot_tenant.py.
INSERT INTO tenants (name)
VALUES ('gate-chatbot')
ON CONFLICT (name) DO NOTHING;
