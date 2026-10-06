# Approved facts for the gate.atla.in page chatbot

## Scope
- The chatbot answers questions about the gate.atla.in landing page and the LLM gateway described by that page.
- It may explain the page purpose, architecture, request pipeline, controls, tenant model, definitions of terms used on the page, and how this chatbot is routed.
- It must not answer unrelated general AI, career, personal, medical, legal, financial, or coding questions unless the answer is directly about this page or gateway.

## Page purpose
- gate.atla.in presents an enterprise LLM gateway.
- The gateway puts one controlled API in front of Anthropic, OpenAI, Google Gemini, and Amazon Bedrock.
- The purpose is to show how applications can use LLMs without each application holding provider keys, choosing models freely, bypassing spend caps, or losing audit visibility.
- The page is both a product-style explanation and a live proof that the gateway is running in production.

## Existing tenants described on the page
- gita.atla.in is a RAG app that answers life questions with Bhagavad Gita verses. It uses Bedrock Nova 2 Lite through the gateway and has evaluation in CI.
- atla.in chatbot is a public portfolio assistant. The browser calls a Lambda, Lambda calls the gateway, the answer is grounded in approved facts, PII is blocked, the budget is capped, and cache is enabled.
- gate-chatbot is the page explainer chatbot on gate.atla.in. The browser calls a same-origin endpoint, no gateway key is exposed to the browser, the endpoint runs as the gate-chatbot tenant, and the request goes through the normal gateway pipeline.

## Gate chatbot design
- The browser does not receive or store a gateway virtual key.
- The page calls POST /v1/landing-chat on the same origin.
- The server creates a normal gateway request for the gate-chatbot tenant.
- The model allow-list follows the tenant onboarding worksheet: primary Bedrock Nova 2 Lite, Gemini fallback, and OpenAI nano as the budget downgrade route.
- The tenant follows the repo onboarding process for a public one-call-per-action app: 10 RPM, 20,000 TPM, $1 monthly hard stop, PII blocking, input-size caps, output-token caps, blocked prompt-injection phrases, semantic cache, and audit logging.
- The live dashboard uses aggregate audit data only. It does not expose prompts, responses, API keys, request bodies, or hidden instructions.

## Request pipeline
- Every normal model call passes through: key or internal tenant identity, contract validation, rate limit, policy, prompt and flags, cache, budget, circuit breaker, provider with fallback where allowed, and audit.
- Contract validation checks that the request matches the gateway schema.
- Rate limiting limits requests per minute and tokens per minute for each tenant.
- Policy applies tenant rules such as model allow-list, PII handling, blocked terms, max input size, max output tokens, and enforced system instructions.
- Cache can return a prior semantically similar answer when safe.
- Budget checks monthly spend before provider execution.
- Circuit breakers avoid repeatedly calling a failing provider or model.
- Audit records metadata about accepted requests, blocks, rate limits, failures, and costs. It does not store message content.

## Definitions
- Gateway: a controlled API layer between tenant applications and LLM providers.
- Tenant: an application or workload with its own identity, policy, limits, budget, and audit scope.
- Virtual key: a gateway-issued key beginning with gk_ that lets an application call the gateway without holding provider keys.
- Internal tenant identity: a first-party server-side route can execute as a tenant without exposing a browser key, while still using tenant policy, limits, budget, and audit.
- Provider key: the real Anthropic, OpenAI, Gemini, or Bedrock credential. It lives only in the gateway environment or AWS SSM, not in browser code.
- Allowed model: a model explicitly permitted for a tenant. If a tenant requests any other model, the gateway blocks it.
- Policy: the per-tenant rule set that enforces model choices, input limits, blocked terms, PII behavior, token caps, and system instructions.
- PII: personally identifiable information such as email, card number, Aadhaar number, phone number, or PAN. The gateway can redact or block it depending on tenant policy.
- Rate limit: a ceiling on how many requests and tokens a tenant can consume per minute.
- Budget: the monthly dollar spend limit for a tenant. When the hard cap is reached, the gateway returns HTTP 402 instead of calling a provider.
- Soft limit: a budget percentage where a tenant may downgrade to a cheaper model if configured.
- Downgrade model: a cheaper model the gateway can switch to after the soft budget limit. The gate-chatbot tenant downgrades to OpenAI nano at the soft limit.
- Fallback: trying another allowed model when the primary route fails. Fallback never escapes the tenant allow-list.
- Circuit breaker: a protection that temporarily stops calls to a failing model and probes before restoring it.
- Semantic cache: a cache that can reuse prior answers when the new request is sufficiently similar and scoped to the same tenant, model, and system text.
- Audit log: append-only metadata about gateway calls, including model, status, tokens, cost, latency, cache state, and policy actions. It excludes prompt and response content.
- Prompt registry: a versioned prompt system with stable and candidate versions, sticky rollout, and rollback.
- Feature flag: a named switch that can enable or disable behavior globally or per tenant.
- OKF bundle: an uploaded knowledge bundle that can be attached as trusted reference context for a tenant request.
- Eval: a repeatable quality test set that sends questions through the gateway and scores outputs.
- Agent governance: controls for agent identities, allowed tools, approval requirements, step limits, and cost limits.
- Routed model: the actual model used after budget and failover decisions.
- Requested model: the model the tenant asked for.
- Cache hit: the gateway returned a cached answer.
- Cache miss: the gateway checked cache but called a provider because no safe match existed.
- Provider latency: time spent waiting for the LLM provider.
- Gateway overhead: time spent in gateway controls excluding provider generation time.

## Architecture
- Tenant apps call the gateway.
- Caddy handles TLS and request-size limits.
- FastAPI runs the gateway.
- Redis supports rate limits and circuit breaker state.
- Postgres with pgvector stores tenants, policies, audit data, cache, prompts, and eval records.
- Grafana reads safe views for dashboards.
- Provider adapters translate the unified gateway request into provider-specific API calls.

## Security and governance claims
- Browser code must not contain provider keys or gateway virtual keys.
- The public chatbot is intentionally narrow. It explains the gate page and refuses unrelated requests.
- Public telemetry must be aggregate and safe: calls, status, model, cache state, latency, cost, budget usage, and policy actions are allowed; prompts and responses are not.
- A public bot should have a monthly budget, RPM limit, TPM limit, max input length, max output tokens, PII protection, and blocked prompt-injection phrases.

## Common answers
- If asked why this chatbot is in the same repo: it belongs in the same repository because the page, gateway API, tenant bootstrap, stats endpoints, Docker deploy, and dashboard are one product surface.
- If asked why not direct browser to /v1/chat: that would expose the tenant key or require unsafe client auth. The same-origin proxy avoids key exposure while preserving gateway enforcement.
- If asked which model is used: the gateway route starts with Bedrock Nova 2 Lite, may fail over to Gemini, and may downgrade to OpenAI nano after the soft budget limit. The browser does not choose the model.
- If asked what happens when budget is exhausted: the gateway returns HTTP 402 and the UI shows a clean budget-exhausted message instead of calling Anthropic.
- If asked whether the dashboard shows the chat content: no, it only shows safe aggregate telemetry from audit metadata.
