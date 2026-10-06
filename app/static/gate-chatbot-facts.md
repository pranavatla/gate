# Approved facts for the gate.atla.in page chatbot

These are the only facts the chatbot may use. They follow the page from top to bottom. Numbers marked "live" change every 30 seconds on the page; the chatbot cannot see the current values and should point the visitor to the live dashboard for them.

## Scope
- The chatbot answers questions about the gate.atla.in page, the LLM gateway it describes, the words used on the page, and how this chatbot itself is governed.
- It does not answer unrelated questions (general coding, trading, medical, legal, financial, personal or career advice). It says politely that it only explains this page.
- If the facts below do not cover a question, it says the page does not cover that, instead of guessing.
- It can explain anything at different depths: in one sentence, step by step, or "like you are five" using the everyday analogies at the end of these facts.

## What the page is
- gate.atla.in is the home of "Gateway", an enterprise LLM gateway built and run by Pranav as a portfolio project. It is live in production on AWS.
- Headline: "One API. Every AI model." Your AI calls, governed in one place: keys, budgets, failover, privacy and audit across four providers.
- The four providers are Anthropic (Claude), OpenAI (GPT), Google Gemini and Amazon Bedrock.
- The problem it solves: without a gateway, every app holds its own provider keys, picks models freely, has no shared spend limit and leaves no common audit trail. The gateway puts one controlled API in front of all providers so a platform team can govern every AI call in one place.
- The page has two parts. Part 1, "The gateway": architecture, the real tenant applications and the request controls. Part 2, "The live dashboard": real numbers from production and how quality is kept honest.
- The hero has two buttons: "Explore the pipeline" (scrolls to the request simulation) and "View source" (the code on GitHub). It also has a one-minute explainer video, "What this gateway does", for first-time visitors.

## Headline numbers in the hero
- Gateway overhead: the median time the gateway adds to a call (p50), a few milliseconds. This number is live.
- 4: AI providers behind one API.
- 9: governance layers per request.
- 25/25: quality checks passed after migrating a real app (gita.atla.in) onto the gateway, the same score as before the migration.
- About $15 per month: the cost to run the whole thing on AWS.
- The page says the numbers were measured on the production deployment in September 2026.

## Architecture ("How the pieces fit")
- Tenants call the gateway with a virtual key. The gateway holds the real provider credentials, keeps state in Postgres and Redis, and reports to Grafana.
- The diagram has tenants on the left, the gateway in the middle, the four providers on the right and three data services underneath.
- Left side, tenants: gita.atla.in (RAG app on EKS, Bedrock), the atla.in chatbot (Lambda, grounded, public), the gate.atla.in chatbot (page explainer, internal tenant) and a dashed box "your app" that points to the onboarding guide.
- The dashed "your app" box is a placeholder for any new application that follows the onboarding guide. It is not a real tenant.
- Middle, gate.atla.in: Caddy handles TLS and passes requests to a FastAPI gateway. Inside are eight control boxes: keys and contract, rate limits, PII and policy, semantic cache, budgets, breakers and failover, agent governance, and the audit log.
- The gateway runs on an EC2 Graviton server with Docker Compose, built with Terraform. There is no SSH; secrets are in AWS SSM; the database is backed up nightly.
- Right side, providers: Anthropic, OpenAI, Google Gemini and Amazon Bedrock. Under Bedrock the diagram names Amazon Nova 2 Lite, the main model used by the tenants.
- Underneath: Postgres with pgvector (tenants, policies, the audit log, the semantic cache, prompts and eval records), Redis (rate limits and circuit breakers) and Grafana (read-only views for dashboards).

## The three real tenants ("Three real tenants, three different trust levels")
- The same gateway applies different rules to each tenant, written as a JSON policy document, like an IAM policy for AI traffic.
- gita.atla.in: a retrieval-augmented (RAG) app on Amazon EKS that answers life questions with grounded Bhagavad Gita verses. It makes 3 model calls per question on Bedrock (Nova 2 Lite) with strict JSON output. Personal data is redacted, not refused. It was migrated onto the gateway by changing one function behind a switch. Its own 25-case evaluation scored 25/25 before and after the migration. Because it needs strict JSON, it has no cheaper downgrade model: at the end of its budget it simply stops.
- atla.in chatbot: a public assistant on Pranav's portfolio site. The browser never holds a key; a small AWS Lambda adds it and calls the gateway. Personal data is blocked; it may use two cheap models only. It is grounded in approved facts and refuses to invent. It has a $1 per month hard stop and 10 requests per minute. Its semantic cache answers repeat questions in about 0.4 s instead of about 3.5 s.
- gate.atla.in chatbot: the explainer on this page, which is this chatbot. Details are in the next section.

## This chatbot (the gate.atla.in chatbot)
- It is the third tenant, called gate-chatbot. It answers questions about this page.
- The browser calls POST /v1/landing-chat on the same website. That endpoint runs inside the gateway itself as an internal tenant, so there is no gateway key at all: nothing to leak, steal or rotate. The browser never sees a provider key or a gateway key.
- Every question still goes through the full gateway pipeline as the gate-chatbot tenant: rate limits, policy, cache, budget, failover and audit.
- The visitor cannot choose the model and cannot add their own instructions. The gateway picks the route.
- Routing: Amazon Nova 2 Lite on Bedrock first. If a provider fails, the gateway tries Gemini (gemini-3.5-flash-lite), then OpenAI (gpt-4.1-nano), then Anthropic (Claude Haiku 4.5), in that order, skipping any provider whose circuit breaker is open, for example one that has run out of credits.
- Limits: 10 requests per minute and a $1 per month hard stop for the whole tenant. At 80 percent of the budget it switches to the cheaper OpenAI gpt-4.1-nano; at 100 percent the gateway refuses with HTTP 402 and no model is called.
- Each visitor also has a personal limit of 6 questions per minute and 60 per day, so one person cannot use up everyone's allowance. A visitor over the limit gets HTTP 429 with a time to wait. Visitors are counted by a short hash of their address; the raw address is not stored.
- Personal data (email, card number, Aadhaar, phone number, PAN) in a question is blocked, and so are phrases that try to override its instructions.
- Questions are limited to 1,200 characters and answers to a few hundred words.
- Answers are cached by meaning for 24 hours, so a repeated question can be answered almost free.
- Under each answer the chat shows an audit line: the model that answered, the cache status, the budget used so far and the request ID. The request ID finds the exact call in the audit log.
- The panel at the top of the chat shows calls in the last 24 hours, the budget used and the last route. These come from the audit log and never include anyone's question or answer.
- Why not call /v1/chat straight from the browser: that would put a gateway key in public web code, where anyone could copy it. Running the endpoint inside the gateway avoids any key while keeping every gateway control.
- Every night a fixed set of page questions is asked again and graded, so wrong or invented answers are caught.

## Infrastructure pills under the tenants
- AWS Mumbai region on EC2 Graviton.
- Terraform with locked remote state.
- Docker Compose with 5 containers: the gateway, Postgres, Redis, Grafana and Caddy.
- Caddy with automatic TLS and HSTS.
- SSM for secrets, no SSH.
- ECR with immutable, scanned images.
- S3 nightly backups that have been restore-tested.
- IAM with least privilege.

## The request pipeline ("Every request walks the same nine-layer corridor")
- The page has a simulation of the real pipeline. A visitor picks a scenario and presses "Send request"; each layer lights up as passed, acted on, answered from cache, blocked or skipped. Clicking a layer explains it. Every refusal happens before a model is called.
- Below the simulation the page states how many real calls walked this corridor in production over the last 7 days, and how many were rate-limited or blocked. These numbers are live.
- Layer 1, Key (who is calling): each app is a tenant with its own virtual key starting gk_. Only a SHA-256 hash of the key is stored, so a database leak reveals no usable key. Keys are 46 characters from a secure random source. A wrong key and a revoked key both get the same 401, so there is nothing to probe. Tool-using agents get agent keys starting ga_. Revoking one tenant never touches another.
- Layer 2, Contract (shape check): every request is checked against one written contract (Pydantic). Wrong roles, max_tokens outside 1 to 4096 or a temperature outside 0 to 1 are rejected with 422 before anything is spent. One request and response shape works for all four providers.
- Requests refused at layers 1 and 2 (401 and 422) are answered before the pipeline, so they carry no request ID and no audit row.
- Layer 3, Rate limit (how fast): a token bucket per tenant for requests per minute (RPM) and tokens per minute (TPM), run atomically inside Redis so several gateway copies share one truth. A noisy tenant cannot starve a quiet one. Limits are sized per user action. A Retry-After header tells clients when to come back. If Redis is down it fails open, and budgets still protect spend. Refusal code: 429.
- Layer 4, Policy (what is sent): a JSON policy per tenant: model allow-list, size caps, blocked phrases, PII redaction or blocking, and instructions the gateway enforces. PII covers email, card numbers (checked with the Luhn rule), Aadhaar, phone numbers and PAN. In redact mode the provider only ever sees a placeholder such as [EMAIL]. The allow-list holds even during failover. Every rule that fires is recorded by name, never the data. Refusal codes: 403 (model not allowed), 413 (input too large) and 400 (blocked content or personal data).
- Layer 5, Cache (seen before?): a semantic cache in Postgres with pgvector matches questions by meaning, not exact words. A repeated question is answered in about 0.4 s for a fraction of a cent. It is isolated per tenant and scoped by model and instructions, so editing a tenant's instructions invalidates old answers. It skips conversations and tool calls, and if it fails the request continues without it.
- Layer 6, Budget (how much): each tenant has a monthly dollar budget with exact costs from a versioned price catalogue. At the soft limit (80 percent) it can switch to a cheaper model; at 100 percent it stops with 402. Downgrade is opt-in: strict-JSON apps just stop. Cache hits still work when the budget is gone. Answered calls report budget use and any downgrade in headers. Other tenants are unaffected.
- Layer 7, Failover (is it healthy): if a provider fails, the gateway tries the next model in that model's fallback chain. A circuit breaker stops calling a provider after 3 failures in 60 seconds and keeps it closed off for 30 seconds, then lets a single probe request through before trusting it again. Errors that mean the account itself is unusable, such as bad credentials or no credits left, close the provider off for about five minutes. Bad requests are never failed over. Fault injection ("chaos" switches) lets failures be tested on demand. If no healthy provider is left the answer is 503.
- Layer 8, Provider (the model): four adapters translate the one contract into the Anthropic, OpenAI, Gemini and Amazon Bedrock formats and back, including tool calls where supported. Provider keys live only here, loaded from AWS SSM. A shared HTTP client has per-phase timeouts. Token counts and stop reasons are normalised. Adding a fifth provider means writing one adapter.
- Layer 9, Audit (the record): every call that passes the key and contract checks, including blocks and failures, becomes an append-only row: tenant, models tried, tokens, cost, latency, cache status and policy actions, never the message text. A database trigger blocks UPDATE and DELETE. The request ID is returned to the caller, so support can find the exact call. It feeds Grafana through read-only views.

## The seven simulation scenarios
- Normal request: every layer passes, Nova 2 Lite answers, the result is 200 with the routed model and a cache miss in the headers.
- Contains an email: the policy layer replaces the address with [EMAIL]; the provider never sees it; the answer is 200 and the header says pii_redacted:email.
- Forbidden model: the policy layer blocks it with 403; no provider is called and nothing is spent.
- Too many requests: the rate limit layer refuses after 10 requests a minute with 429 and a Retry-After of a few seconds.
- Repeated question: the cache finds a match with similarity of at least 0.95 and answers in about 0.4 s instead of about 3.5 s.
- Budget used up: the budget layer refuses with 402; retrying will not help until the budget changes.
- Provider outage: the primary provider fails, the failover layer moves along the fallback chain, gpt-4.1-nano answers with 200 and the user never notices. The audit row lists every model tried.

## Twelve services ("Twelve services, one control plane")
- One unified API: Anthropic, OpenAI, Gemini and Bedrock behind one request and response shape; switch provider by changing one string. Proof: 4 adapters, tool calls and stop reasons.
- Virtual keys and tenants: every app gets its own hashed, revocable key; provider credentials never leave the gateway. Proof: revoke one tenant, others unaffected.
- Rate limiting: token-bucket RPM and TPM per tenant, atomic in Redis, with Retry-After. Proof: 10 answered and 5 refused with 429 in a 15-call burst.
- Budgets and cost autopilot: monthly dollar budgets, exact costs, automatic downgrade or hard stop. Proof: 402 when spent, with the amount in the error.
- Failover and circuit breakers: per-model fallback chains, breakers shared across gateway copies, half-open probing and on-demand fault injection. Proof: one failing provider, answers keep coming.
- PII redaction and policy: model allow-lists, size caps, blocked phrases, PII redact or block, and enforced instructions per tenant. Proof: rule names reach the audit log, never the data.
- Semantic cache: answers repeated questions by meaning using pgvector; isolated per tenant, self-invalidating, fails open. Proof: 3.5 s to 0.4 s, about 3,700 times cheaper.
- Agent governance: agent identities, tool allow-lists, human-approval flags, and per-run step and cost limits that fail closed. Proof: a looping agent is stopped after 5 steps.
- Append-only audit log: every call past the key and contract checks is recorded with a request ID; never message text. Proof: UPDATE and DELETE are blocked by a trigger.
- Live dashboards: Grafana provisioned from Git over least-privilege views: spend, errors, blocks, p50 and p95 latency, budgets and agent runs. Proof: gateway overhead p50 of about 4 ms.
- Infrastructure as code: VPC, IAM, ECR, EC2, DNS and a budget alarm in Terraform with locked remote state; no SSH, admin through AWS Session Manager. Proof: about $15 a month all-in.
- Backups you have restored: nightly database dumps to S3 that the server can write but not delete, plus a scripted restore test. Proof: the restored copy matched row for row.

## The API ("One call, whichever model")
- Tenants send their virtual key and a provider/model name to POST /v1/chat. Switching providers is changing one string, for example bedrock/global.amazon.nova-2-lite-v1:0.
- The page shows a curl example with an Authorization: Bearer header, a JSON body with model, messages, max_tokens and temperature, and a Copy button.
- Status codes: 200 answered; 400 blocked content, personal data or unknown model; 401 bad or revoked key; 402 budget used up; 403 model or tool not allowed; 413 input too large; 422 malformed request; 429 slow down and retry later; 503 no healthy provider. Pressing 200, 402, 403 or 429 on the page replays that scenario in the pipeline simulation.
- The page cannot send real requests to /v1/chat because calls need a tenant key. Every call that passes the key and contract checks returns an X-Request-ID that maps to a row in the audit log.
- Useful response headers: X-Request-ID, X-Gate-Routed-Model (the model that actually answered), X-Gate-Fallback (true if a different model was used), X-Gate-Cache (hit or miss), X-Gate-Downgraded and X-Gate-Budget-Used-Pct.
- The root URL also answers in JSON with ?format=json. There is a public aggregate endpoint GET /v1/stats and a quality endpoint GET /v1/stats/evals.

## The live dashboard ("What the gateway is doing right now")
- The numbers are not typed in: the page asks the production gateway every 30 seconds, straight from its append-only audit log. Nothing includes message text, keys or tenant names.
- Tiles (all live): calls in the last 7 days and 24 hours; success rate with answered calls and server errors; gateway overhead (median time the gateway adds, p50); answer time p90 (9 in 10 successful calls finish faster); cache hit rate; failovers (calls that needed a second provider); turned away (rate-limited, blocked, over budget); and model spend with tokens in and out.
- Charts: calls per hour over the last 24 whole hours in UTC, and which models answered successful calls in the last 7 days, with spend per model.
- Honest context on the page: the counts include Pranav's own tests and the nightly eval runs. They show the machinery working, not a busy product.

## Quality ("Is the chatbot still answering correctly?")
- Every night the same questions are asked again and graded. The page shows the latest result of each question set, read live from the eval tables. A score of 1.00 means every answer was graded correct.
- Tiles: eval runs, graded answers (each scored by rules and a judge model), test questions and question sets, and prompt versions in the registry.
- A table lists recent runs with the time, set, prompt version, score and verdict.
- Two alarms: "Eval regression" fires if the latest run of any set is a regression, a noisy baseline or unreliable; it was tested on purpose and seen going from Normal to Firing. "Eval job silent" fires if no run has happened for 36 hours, or if data is missing, because a check that stops running must be loud, not quiet.
- The same data feeds a Grafana dashboard used day to day.

## The nightly eval pipeline ("An eval pipeline that runs while I sleep")
- It only speaks up when something truly changed, or when the check itself breaks. The page lets a visitor pick a night (healthy night, quality drops, run breaks halfway, jumpy history, silent night) and press "Run the night".
- Step 1, Eval set: a set is a list of cases. Each case has a question, a reference answer and optional rule checks (must contain, must not contain, word limit). Cases never change once saved, so tonight is comparable with last week.
- Step 2, Ask: the runner calls the gateway like any customer would, as its own tenant called evals, so the whole real path is tested. The cache is bypassed with a feature flag so every run measures the model. Latency, cost and request ID are stored per answer. Rate limits apply, which is how a past run broke halfway.
- Step 3, Grade: hard rules run first, then a judge model scores meaning from 0 to 1. The judge sees only the question, the answer and the reference, never the instructions given to the chatbot, so it cannot be talked into agreeing. A case passes when its score is high enough (0.7 or more) and its rules hold. The judge writes a reason, and reading those reasons is how real defects were found.
- Step 4, Compare: the new score is compared with the last five clean runs of the same set and route. At least three clean runs are needed. The allowed drop is the larger of 0.10 or twice the spread of the history, so a naturally noisy test does not cry wolf and a stable one is held tight. Experiments are excluded so they do not shift normal.
- Step 5, Verdict: one label and an exit code. OK, IMPROVED and BUILDING_BASELINE exit 0 with no alert. REGRESSION exits 3, NOISY_BASELINE exits 4 and UNRELIABLE (the run did not finish properly) exits 5, and these raise the alert. Two manual commands: ACCEPTED ("this lower score is the new normal", which resets the baseline) and EXCLUDED ("throw this run out", for experiments).
- Step 6, Alert: a failed exit makes the nightly job fail, and Grafana separately watches the latest verdict of every set. Good nights stay quiet on purpose.
- A timer runs the sets every night at 22:00 UTC.
- Engineer's view: the tables are eval_sets, eval_cases (immutable), eval_runs and eval_results. Each result keeps the answer, score, judge reason, latency, cost and the request ID that links to the audit log. The baseline is by set and route, not by prompt version, on purpose: a new prompt must beat the normal. The eval key lives in a secrets store and is fetched at run time.

## Prompt releases ("Prompts as versioned, rollback-able releases")
- Before this, a prompt was a text file inside someone's code: changing it meant redeploying, with no record and no quick way back. Now a prompt is a released artifact. The page lets a visitor pick a good or a bad release and press "Ship it".
- Step 1, Publish: the new text is saved as the next version number. It does not change what anyone sees yet. Versions are immutable. The command is audited.
- Step 2, Roll out: choose a percentage, for example 5. Only that slice of visitors gets the candidate. A hash of the visitor decides, so the choice is sticky; everyone else stays on the stable version.
- Step 3, Observe: every response names the version that produced it in the x-gate-prompt header, and the eval pipeline can score the candidate before it reaches many people.
- Step 4, Promote: if the numbers look right, the candidate becomes stable for everyone with one command and no redeploy. The old version stays stored.
- Step 5, Roll back: if something looks wrong, one command removes the candidate and everyone is back on stable for the next request. The bad version stays stored for the post-mortem.
- Immutable: version 3 is always exactly version 3, so any answer can be traced to the exact text that produced it.
- Sticky: the same visitor always gets the same version, so a conversation never changes behaviour halfway.
- Flags: named on/off switches for one tenant or for everyone. If the lookup fails, the gateway uses the safe default instead of failing the request. Example: the evals tenant has cache_bypass switched on.
- Version 1 of a prompt goes live immediately; later versions are not live until rolled out. Commands: publish, rollout, promote, rollback and show; for flags: set, clear and show. Every command writes to the audit log.

## The case study ("The bug the evals helped me find")
- The atla.in chatbot sometimes told visitors that Pranav used OpenAI, Anthropic, Gemini and Bedrock at Accenture. That was false: those providers belong to his own projects. A wrong claim about experience, in front of recruiters, is the kind of defect nobody notices until it hurts.
- Found: a guard test asking whether Pranav used an LLM at Accenture got a wrong "yes" in roughly one run in six.
- After four clean runs he first thought the old prompt was immune; a later run failed. Four runs were not proof, so he fixed the decision rule before testing further.
- Candidate v5 added one explicit fact and passed the Accenture test in 3 of 3 runs, but failed the greeting test in 3 of 3: the model greeted the visitor as if the visitor were Pranav ("Hello Pranav! What would you like to know about me?"). The rule told it what to ask but not who the assistant is.
- v6 added one rule: you are an assistant that tells visitors about Pranav. It passed 3 of 3 clean runs, was deployed and was checked live on atla.in. It now greets: "Hello! I can tell you about Pranav and his work."
- The ship rule was written before looking at results: ship only if the Accenture test passes in all three runs and no other case fails in two or more.
- A grid shows nine runs (24 to 32) on the same 15 questions across v1, v5 and v6 for the Accenture and greeting cases, with average scores between 0.87 and 1.0.
- The lesson: the average score barely moved (0.93 to 1.0), yet two real defects hid inside it. The score tells you that something is off; reading the stored answer tells you why.

## Lessons ("What this build taught me")
- Practices to keep: write the pass rule before the test; read the raw answer, not just the score; make the checker fail loudly (a half-finished run once passed silently, so it now exits non-zero and alerts); keep experiments out of the baseline; ship the smallest change that fixes the cause; keep unfinished work out of a release.
- Honest limits: the eval sets are small, so they catch known failures, not unknown ones. The judge is a model and can wobble on thin references, so rule checks back it up. There are no automated unit tests yet; quality is gated by evals and a health check. It is a single server, right for this scale. Database migrations are applied by hand. The evals test prompt and model, not retrieval, so the Gita app needs its own set.
- Next on the page: an eval set for the Gita app, a migration runner, and a dashboard that tracks every set side by side.

## Onboarding a new app ("your app")
- A new app becomes a tenant. Before onboarding, the team confirms the real production model, the calls and tokens per user action, whether output must be strict JSON, whether the app is public, and whether it uses tools.
- Limits are sized per user action with headroom: requests per minute, tokens per minute and a monthly budget.
- The policy is written as code: allowed models including fallbacks, personal data handling, size caps that include the app's instruction text, and a token cap.
- The key is issued straight into the app's own secret store, never shown on screen. A browser app never gets a key: it needs a small backend in between, like the atla.in chatbot's Lambda.
- Before switching traffic, the app is tested with oversized input, personal data, a forbidden model and a burst, and each must be refused by the right layer.

## Definitions
- Gateway: a controlled API layer between applications and LLM providers.
- LLM: large language model, the AI model that writes the answers.
- Tenant: an application with its own identity, policy, limits, budget and audit records.
- Virtual key: a gateway-issued key starting gk_ that lets an app call the gateway without holding provider keys. Agent keys start ga_.
- Internal tenant: a first-party endpoint running inside the gateway that acts as a tenant without any key, while still getting every control. This chatbot is one.
- Provider key: the real Anthropic, OpenAI, Gemini or Bedrock credential. It lives only in the gateway, loaded from AWS SSM.
- Policy: a tenant's rules for allowed models, input size, blocked phrases, personal data and token caps, plus instructions the gateway adds.
- Allow-list: the models a tenant may use. Anything else is refused with 403, even during failover.
- PII: personally identifiable information, such as an email address, card number, Aadhaar number, phone number or PAN. It can be redacted or blocked per tenant.
- Redact: replace personal data with a placeholder before the provider sees it. Block: refuse the whole request.
- RPM and TPM: requests per minute and tokens per minute, the two rate limits.
- Token: a small piece of text, roughly three quarters of a word, that models read and write and are billed by.
- Token bucket: a rate-limiting method where a bucket refills at a steady rate and each request takes from it.
- Budget, soft limit and downgrade: the monthly dollar cap; the percentage (80) where a cheaper model can take over; and that cheaper model.
- Hard stop: refusing with 402 when the budget is spent.
- Fallback chain: the ordered list of models to try if the first one fails.
- Circuit breaker: a switch that stops calling a failing provider for a while, then lets one probe request through before trusting it again. Half-open is that probing state.
- Semantic cache: a cache that matches questions by meaning, using embeddings stored in pgvector.
- Embedding: a list of numbers that represents the meaning of a text, so similar questions get similar numbers.
- pgvector: a Postgres extension for storing and comparing embeddings.
- RAG: retrieval-augmented generation, where the app first finds relevant text (for gita, verses) and gives it to the model.
- Grounded: answering only from supplied facts.
- Audit log: append-only records of every call (model, status, tokens, cost, latency, cache and rules fired), never the message text.
- Request ID: the unique ID of one call, returned in X-Request-ID, that finds its audit row.
- p50, p90, p95: the time under which 50, 90 or 95 percent of calls finish. p50 is the median.
- Gateway overhead: time the gateway itself adds, excluding the model's own time.
- Routed model: the model that actually answered after budget and failover decisions.
- Eval: a fixed set of questions asked again and graded to check quality. Judge model: the model that grades answers against a reference.
- Baseline: the recent normal score that a new eval run is compared with.
- Regression: a score that fell by more than the allowed tolerance.
- Prompt registry: versioned, immutable prompt releases with rollout, promote and rollback.
- Feature flag: a named on/off switch, for one tenant or everyone.
- Agent governance: controls for AI agents that call tools: identities, allowed tools, approval flags, and step and cost limits per run.
- OKF bundle: an uploaded knowledge bundle (Open Knowledge Format) that a tenant can attach to requests as reference material.
- Caddy: the web server in front of the gateway that handles TLS (HTTPS).
- FastAPI: the Python framework the gateway is written in.
- Terraform: infrastructure as code; the AWS setup is written as files and applied, not clicked together.
- Graviton: Amazon's ARM-based server processors.
- SSM: AWS Systems Manager, used for secrets (Parameter Store) and admin access without SSH (Session Manager).
- ECR: Amazon's container image registry. EKS: Amazon's managed Kubernetes. Lambda: Amazon's run-code-on-demand service.
- HSTS: a header that tells browsers to always use HTTPS.
- Chaos or fault injection: deliberately making a provider fail to prove failover works.

## Everyday analogies for "explain like I'm five"
- The gateway is like the front desk of a big office building. Every app is a company in the building. Instead of every company having its own keys to every supplier, they all go through the front desk, which knows the rules for each company.
- A virtual key is like a visitor badge: each company gets its own, the desk can switch off one badge without bothering anyone else, and the badge does not open the suppliers' doors directly.
- The rate limit is like a turnstile that only lets so many people through each minute, so one busy company cannot block the door for everyone.
- The policy is like the building rules: which suppliers you may use, no bags bigger than this, and no private papers leaving the building (personal data gets covered up or stopped).
- The budget is like a prepaid card with a monthly limit. Near the end it can switch to a cheaper supplier; when it is empty, the desk says "no more this month".
- The semantic cache is like a helper with a good memory: if someone asks a question that means the same as one already answered, the helper repeats the earlier answer instantly.
- Failover is like a backup generator: if one supplier stops answering, the desk quietly calls the next one, and the person asking does not notice.
- The circuit breaker is like putting a "closed for now" sign on a supplier that keeps failing, then checking with one call later before sending everyone back.
- The audit log is like the desk's logbook: it writes down who came, when, what it cost and what the rules did, but never what was said in the conversation.
- Evals are like a nightly pop quiz: the same questions every night, marked by a teacher, so you notice quickly if the answers get worse.
- Prompt releases are like trying a new recipe on a few customers first, and going back to the old recipe in one step if they do not like it.
