# Onboarding a tenant to gate.atla.in

This guide takes a new application ("tenant") from nothing to production traffic through the gateway. It is written from two real onboardings, **gita.atla.in** (a RAG app on EKS) and the **atla.in chatbot** (a public Lambda), and every "lesson" box below is something that actually went wrong once.

It has two audiences:

- **Tenant teams** (the people building an app): sections 1, 4, 5, 6 and 7.
- **Platform admins** (the people running the gateway): everything, especially sections 2, 3 and 8.

---

## 1. What the gateway gives you

One API in front of four providers, with governance applied to every call:

| You get | What it means for your app |
|---|---|
| **One API, four providers** | Anthropic, OpenAI, Google Gemini and Amazon Bedrock behind the same request and response shape |
| **No provider keys in your app** | You hold one gateway key. Provider keys never leave the gateway |
| **Rate limits and budgets** | Your spend can't run away, and one tenant can't starve another |
| **Failover** | If your model's provider fails, the gateway can try an approved fallback |
| **Policy** | Model allow-lists, PII redaction or blocking, size caps and enforced instructions, applied before anything reaches a provider |
| **Audit** | Every call is recorded (model, tokens, cost, latency, which rules fired), never the message content |
| **Semantic cache** (optional) | Repeated questions answered from cache in milliseconds, at almost no cost |

---

## 2. Before onboarding: the checklist

Answer these **before** creating anything. Most onboarding problems come from guessing one of them.

| Question | Why it matters |
|---|---|
| Which model does the app **actually** run in production? | Check the **running configuration** (environment variables, deployment manifests), not just the code |
| How many model calls does **one user action** make? | A RAG app often makes several (query rewriting, reranking, answering). Limits must be sized per action |
| Roughly how many tokens per call, input and output? | Drives the tokens-per-minute limit and the budget |
| Does the app need **strict output** (for example JSON)? | Decides whether a cheaper fallback or downgrade model is safe |
| Does it send a **long system text** (instructions, facts, documents)? | It counts toward size limits and is scanned by policy |
| Can user input contain **personal data**? | Decides the PII mode: `redact` or `block` |
| Is the app **public** (anyone can call it) or internal? | Public apps get tighter limits, allow-lists and a hard budget |
| Does it use **tools / agents**? | Needs an agent identity, not a plain tenant key (section 7) |

> **Lesson (gita):** the code's default model was `us.anthropic.claude-sonnet-4-6`, but the live deployment overrode it to `global.amazon.nova-2-lite-v1:0`. A catalogue and budget built from the code would have been wrong by roughly ten times. Always read the running config: `kubectl get deploy <name> -o jsonpath='{...env...}'`, the Lambda's environment, or the ECS task definition.

---

## 3. Sizing limits and budget (the worksheet)

Every tenant has three numbers. Size them from **user actions**, not individual calls.

| Setting | Formula | Headroom |
|---|---|---|
| **Requests per minute** (`rpm_limit`) | peak actions per minute × calls per action | × 1.5 |
| **Tokens per minute** (`tpm_limit`) | peak actions per minute × calls per action × (input + output tokens per call) | × 1.5 |
| **Monthly budget** (`monthly_budget_usd`) | actions per month × cost per action | × 1.2 |

Cost per call = input tokens × input price + output tokens × output price (prices per million tokens, from the catalogue).

**Worked examples from production:**

| | gita.atla.in | atla.in chatbot |
|---|---|---|
| Calls per user action | 3 (query generation, reranking, answer) | 1 |
| Tokens per action | about 6,000 input + 1,400 output | about 740 input + 100 output |
| Model | `bedrock/global.amazon.nova-2-lite-v1:0` | same, with Gemini fallback |
| Cost per action | about $0.006 | about $0.0004 (about $0.0000002 on a cache hit) |
| Limits set | 120 RPM, 150,000 TPM | 10 RPM, 20,000 TPM |
| Budget | $5 / month, **no downgrade** | $1 / month, hard stop |

> **Lesson (gita):** the first TPM limit (20,000) was sized per *call*. Gita's 25-question evaluation hit `429 tokens per minute` at question 6, because each question makes three calls. Sized per *action*, the full evaluation passed 25/25 with no 429s.

**Budget behaviour:** at `soft_limit_pct` (default 80%) of the monthly budget, the gateway switches the tenant to its `downgrade_model`, if one is set. At 100% it returns **402**.

> **Lesson (gita):** a downgrade model is only safe if the app tolerates a weaker model. Gita's pipeline requires strict JSON, and a smaller model might not follow the schema, so answers would *fail* rather than get cheaper. Gita has **no downgrade**: a clean stop is safer than a silent quality drop.

---

## 4. Policy: the rules applied to your requests

Each tenant has a JSON policy. Rules run in this order, cheapest and most decisive first:

| Order | Key | Effect | Error |
|---|---|---|---|
| 1 | `allowed_models` | Only these models (including as fallbacks) | 403 |
| 2 | `max_input_chars` | Caps the total size of system text **plus** all messages | 413 |
| 3 | `blocked_terms` | Rejects requests containing listed phrases | 400 (doesn't say which) |
| 4 | `pii_mode` | `off`, `redact` (replace with `[EMAIL]`, `[PHONE]`…) or `block` | 400 in block mode |
| 5 | `max_tokens_cap` | Lowers `max_tokens` to the cap (the request still succeeds) | none |
| 6 | `system_prompt` | Gateway instructions placed **before** the tenant's own system text | none |
| - | `cache` | `{"enabled": true, "threshold": 0.95, "ttl_s": 86400}` | none |

PII detection covers email addresses, card numbers (Luhn-checked), Aadhaar, Indian mobile numbers and PAN. It matches **formats**, not meaning: it won't catch "my neighbour Ravi on MG Road".

> **Lesson (chatbot):** policy scans the **whole request, including your system text**. The chatbot's facts file once contained an email address, which would have made *every* request fail PII blocking. Keep contact details out of system text, and avoid phrases on the blocked list (for example "system prompt").

> **Lesson (chatbot):** `max_input_chars` counts your system text too. The chatbot's 2,800-character facts file exceeded the original 1,500 limit on its own, which would have returned 413 for every question. If you send long instructions or documents, the limit must include them; cap the *user's* part in your own code.

**Caching:** only single-question requests without tools are cached. The cache key includes the tenant, model, `max_tokens` and the full system text, so **changing your system text automatically invalidates old answers**. Only enable caching for **grounded** answers: caching an ungrounded model just replays its mistakes faster.

---

## 5. The API

**Base URL:** `https://gate.atla.in`

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness: `{"status": "ok"}` |
| `POST /v1/chat` | Every model call |

**Request:**

```json
{
  "model": "bedrock/global.amazon.nova-2-lite-v1:0",
  "system": "Optional instructions or grounding facts",
  "messages": [
    {"role": "user", "content": "What does the Gita say about anxiety?"}
  ],
  "max_tokens": 300,
  "temperature": 0
}
```

| Field | Notes |
|---|---|
| `model` | Always `provider/model-id`. Must be in the catalogue and your allow-list |
| `messages` | Alternating `user` / `assistant`, ending with `user`. Plain-text `content` |
| `system` | Optional. Counts toward size limits and is scanned by policy |
| `okf_bundle` | Optional tenant-owned OKF bundle ID uploaded through `POST /v1/okf/{bundle_id}` |
| `okf_concepts` | Optional list of concept IDs (bundle-relative paths without `.md`); omit to attach every concept |
| `max_tokens` | 1 to 4,096 (then clamped by your policy's cap) |
| `temperature` | Optional, 0 to 1. Use **0** for structured output and repeatable evaluations |

**Headers:** `Authorization: Bearer <your key>` and `Content-Type: application/json`.

### OKF knowledge bundles

Gate accepts Google Open Knowledge Format v0.2 bundles as ZIP files. Upload uses the normal tenant API key; each tenant can only use its own bundle IDs. Agent keys cannot upload or replace bundles. A bundle must contain concept Markdown files with YAML frontmatter and a non-empty `type`. Optional `index.md` and `log.md` files are accepted. Unknown metadata and concept types are preserved. Uploads are limited to 1 MB compressed, 1 MB expanded, 500 files, and 100 KB per file. Chat requests can attach up to 20 selected concepts and 4,000 characters of OKF context. Existing input-size and PII policies still apply after context is attached. After publishing, apply `db/011_okf.sql` to an existing database; a fresh database applies it automatically.

```bash
curl -X POST https://gate.atla.in/v1/okf/my-knowledge \\
  -H "Authorization: Bearer $GATE_API_KEY" \\
  -H "Content-Type: application/zip" \\
  --data-binary @knowledge.zip
```

Then select concepts in a normal chat request:

```json
{
  "model": "bedrock/global.amazon.nova-2-lite-v1:0",
  "okf_bundle": "my-knowledge",
  "okf_concepts": ["runbooks/incident-response"],
  "messages": [{"role": "user", "content": "How do I triage this alert?"}]
}
```

The concept IDs are relative paths without `.md`. If `okf_concepts` is omitted, Gate tries to attach all bundle concepts and rejects the request if the attached context is too large. Gate does not execute files from a bundle; it currently uses the selected Markdown as reference context, so keep bundles small and use the normal tenant size and PII policies.

**Response:**

```json
{
  "provider": "bedrock",
  "model": "global.amazon.nova-2-lite-v1:0",
  "content": "...",
  "usage": {"input_tokens": 737, "output_tokens": 31},
  "stop_reason": "end",
  "tool_calls": []
}
```

`stop_reason` is `end`, `max_tokens` (the answer was cut off at the cap), `tool_use` or `filtered`.

**Response headers worth logging:**

| Header | Meaning |
|---|---|
| `X-Request-ID` | The ID of this call in the gateway's audit log. **Log it on every error** |
| `X-Gate-Routed-Model` | The model that actually answered |
| `X-Gate-Fallback` | `true` if failover used a different model |
| `X-Gate-Downgraded` | `true` if the budget autopilot switched models |
| `X-Gate-Budget-Used-Pct` | Your spend so far this month |
| `X-Gate-Policy` | Rules that acted, e.g. `pii_redacted:email,max_tokens_clamped:1000->300` |
| `X-Gate-Cache` | `hit`, `miss` or `skip` |

**Current catalogue** (prices per million tokens, input / output):

| Model | Price |
|---|---|
| `bedrock/global.amazon.nova-2-lite-v1:0` | $0.33 / $2.75 |
| `gemini/gemini-3.5-flash-lite` | $0.30 / $2.50 |
| `openai/gpt-4.1-nano` | $0.10 / $0.40 |
| `anthropic/claude-haiku-4-5-20251001` | $1.00 / $5.00 |

---

## 6. Errors: what each code means and what your app should do

| Code | Meaning | Your app should |
|---|---|---|
| **400** | Bad request, blocked content or personal data (block mode) | Show the user a helpful message. **Don't retry** |
| **401** | Missing, invalid or revoked key | Check key configuration. Don't retry |
| **402** | Monthly budget exhausted | Degrade gracefully (e.g. "try again next month" or a contact link). Don't retry |
| **403** | Model not allowed for this tenant, or agent rules violated | Fix the request. Don't retry |
| **413** | Input too long (gateway policy, or over 1 MB at the edge) | Shorten input. Don't retry |
| **422** | Request doesn't match the schema (e.g. `temperature` above 1) | Fix the request. Don't retry |
| **429** | Rate limit (requests or tokens per minute). The message says how long to wait | **Retry with backoff**, honouring the wait |
| **502 / 503 / 504** | Provider failure, or no healthy provider | **Retry with backoff** a small number of times |

**Recommended client behaviour** (as implemented in gita's `bedrock_client.py`):

- Retry only on **429, 502, 503, 504** and network errors: at most 3 attempts, backing off 1 s then 2 s (longer if a 429 says so).
- Never retry 4xx errors other than 429: they won't succeed on a second try.
- Include `X-Request-ID` in every error you log. It links your failure to the gateway's audit row.
- Keep a **switch** during migration (e.g. "use the gateway only if a key is configured"), so rollback is one configuration change.

---

## 7. Agents (tools)

Apps that let a model call tools need an **agent identity**, not a plain tenant key:

| Rule | Detail |
|---|---|
| Agent key | Prefix `ga_`, issued per agent (`python -m app.admin --help` lists the commands) |
| `Run-Id` header | Required on every call; groups the steps of one agent run |
| `allowed_tools` | Tools the agent may declare; undeclared or hallucinated tools are dropped |
| `approval_required_tools` | The gateway flags these (`requires_approval: true`); **your app must pause for a human** |
| `max_steps_per_run`, `max_cost_per_run_usd` | Hard limits per run |
| Tool-capable models | Anthropic and OpenAI only. Gemini and Bedrock requests with tools are skipped during failover |

A tenant key sending tools gets **403**.

---

## 8. Admin runbook: onboarding step by step

All admin commands run on the gateway host through SSM (there is no SSH):

```
aws ssm start-session --target <instance-id>
cd /opt/gate/app
```

**1. Create the tenant**

```
sudo docker compose exec gateway python -m app.admin create-tenant <tenant-name>
```

**2. Set limits, budget and policy as code.** Add the tenant to `db/seed_tenant_limits.sql` and `db/seed_policies.sql` in the repo (use `jsonb_set` for changes to existing tenants), commit, run `./deploy/publish.sh`, then apply on the host:

```
sudo aws s3 sync s3://<bucket>/deploy/ /opt/gate/ --exact-timestamps
sudo docker compose exec -T gate-postgres psql -v ON_ERROR_STOP=1 -U gate -d gate < /opt/gate/seeds/seed_tenant_limits.sql
sudo docker compose exec -T gate-postgres psql -v ON_ERROR_STOP=1 -U gate -d gate < /opt/gate/seeds/seed_policies.sql
```

> **Lesson:** make every seed and migration **safe to run twice** (`UPDATE … SET`, `jsonb_set`, `INSERT … WHERE NOT EXISTS`). They will get re-run.

> **Lesson:** `deploy/publish.sh` once matched migrations with `00*.sql`, which silently skipped `010_…sql`. Match migration files with a pattern that can't run out of digits (`[0-9][0-9][0-9]_*.sql`).

**3. Issue the key straight into the tenant's own secret store, never on screen.** From an admin workstation:

```
KEY=$(aws ssm start-session --target <instance-id> --document-name AWS-StartInteractiveCommand \
  --parameters '{"command":["cd /opt/gate/app && sudo docker compose exec -T gateway python -m app.admin issue-key <tenant-name>"]}' \
  | grep -o 'gk_[A-Za-z0-9_-]\{43\}' | head -1)
echo ${#KEY}      # must print 46
aws ssm put-parameter --name /<tenant-name>/prod/GATE_API_KEY --type SecureString --value "$KEY" && unset KEY
```

Each tenant's key lives under **its own path** (`/gita/prod/…`, `/atla-chatbot/prod/…`), and each tenant's runtime role may read **only** its own path. The gateway host can read only `/gate/prod/*`. The gateway stores only a SHA-256 hash of each key: a lost key cannot be recovered, only replaced.

**4. Wire the key into the tenant's runtime**

| Runtime | How |
|---|---|
| Kubernetes (gita) | A Secret created from the SSM value, injected with `kubectl set env deployment/<name> --from=secret/<secret>` |
| Lambda (chatbot) | The function reads SSM at cold start; its IAM role allows `ssm:GetParameter` on one parameter ARN |
| Browser apps | **Never.** A key in a web page is public. Put a small backend in between (the chatbot's Lambda pattern) |

**5. Test before switching traffic**

- One call with the tenant's real model and settings, checking `X-Gate-Routed-Model` and `X-Gate-Policy`.
- The app's own quality evaluation **before and after** the switch (gita: 25/25 on both).
- A burst at the expected peak, to confirm the limits hold without surprising 429s.
- For public tenants: oversized input, personal data, a fake `system` role, a forbidden model and a burst. Each must be refused by the right layer.

**6. Switch traffic, then watch the dashboard** (Grafana: calls by outcome, spend by tenant, budget %, governance actions).

**7. Clean up keys nobody holds.** List active keys per tenant and revoke any that no one has in a secret store:

```
sudo docker compose exec gate-postgres psql -U gate -d gate -c \
  "SELECT t.name, k.key_prefix, k.created_at FROM api_keys k JOIN tenants t ON t.id = k.tenant_id WHERE k.revoked_at IS NULL ORDER BY t.name, k.created_at;"
sudo docker compose exec gateway python -m app.admin revoke-key <key-prefix>
```

---

## 9. Lifecycle

| Task | How |
|---|---|
| **Rotate a key** | Issue a new key into the tenant's SSM path (`--overwrite`), update the runtime (re-create the Kubernetes Secret, or let the Lambda pick it up on its next cold start), confirm traffic, then revoke the old prefix |
| **Change limits or policy** | Edit the seed files, commit, publish, apply. Changes take effect on the next request, with no restart |
| **Suspend a tenant** | Revoke its keys, or set the tenant inactive. Other tenants are unaffected |
| **Offboard** | Revoke all keys, delete the tenant's SSM parameters, and keep its audit history (the audit log is append-only by design) |

---

## 10. Onboarding checklist (copy into the ticket)

- [ ] Real production model confirmed from the **running** configuration
- [ ] Calls per user action and tokens per call measured
- [ ] RPM, TPM and budget sized per action (section 3), with headroom
- [ ] Downgrade model chosen, or deliberately none (strict-output apps)
- [ ] Policy set: allow-list including fallbacks, PII mode, size cap including system text, token cap
- [ ] System text checked for personal data and blocked phrases
- [ ] Tenant created; limits and policy committed as code and applied
- [ ] Key issued straight into `/<tenant>/prod/GATE_API_KEY`; runtime can read only that path
- [ ] Client retries only 429/5xx, logs `X-Request-ID`, and has a rollback switch
- [ ] Quality evaluation passed before **and** after the switch
- [ ] Burst test at expected peak passed
- [ ] Unused keys revoked
- [ ] Dashboard shows the tenant's traffic, spend and policy actions
