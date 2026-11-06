# Dossier: Abstract and Phase-wise Build Guide

Built for the Cominty "agent-native application" challenge. Deadline: **7 November 2026**.
Each phase below has a self-contained prompt you can paste into a different LLM. Finish one phase, pass its checks, then move on.

---

## 0. How to use this guide

1. Open a **new chat** with an LLM for each phase.
2. Paste the **Context Pack** (section 2) first, then paste that phase's prompt.
3. Run the phase's **acceptance checks** yourself. Do not start the next phase until they pass.
4. Commit after every phase (`git commit -m "phase N: ..."`).

**Two rules that save you hours**

- LLMs invent SDK methods. Always paste the "Verified SDK facts" from the Context Pack, and tell the LLM to put every SDK call behind one adapter file (`cominty_gateway.py`). If the real SDK differs, you fix one file.
- Never let any LLM call another AI provider from your app. All agent functionality must run on Cominty, or you risk disqualification.

**Suggested LLM assignment** (use whatever you have; this is a guide, not a rule)

| Phase | Work | Best fit |
|---|---|---|
| 0 | Platform recon script | any coding LLM |
| 1 | Synthetic data generator | any coding LLM |
| 2 | Agent instructions + skill | strongest reasoning LLM |
| 3 | Backend and pipeline | strongest coding LLM |
| 4 | Frontend | LLM good at UI/CSS |
| 5 | Eval harness | strongest reasoning LLM |
| 6 | Deploy and hardening | any coding LLM |
| 7 | Video script, email, README | strongest writing LLM |

---

## 1. Abstract

**Dossier** is an agent-native case processor for teams that handle messy administrative files. The demo scenario is a university international office preparing French housing-aid (APL) applications for students. Staff upload four documents per student (lease, bank RIB, enrollment certificate, residence permit). Three Cominty Managed Agents then do the work:

1. **Intake** extracts structured, source-cited facts from the uploaded PDFs.
2. **Verifier** cross-checks facts across documents and flags contradictions, expiries and missing items, citing the exact evidence.
3. **Action** drafts the application form and a French email to the student, only after a staff member approves.

The system is built around the controls regulated teams ask for: least-privilege capabilities per agent, a human approval gate before any outbound action, and a full audit trail of every agent step and human decision.

A **Reliability panel** measures the pipeline on synthetic test cases with planted errors. It reports per-field extraction accuracy, planted-error recall, false positives, runs used, latency and cost per dossier, and compares two models behind the same agents. This shows how a multi-step agent system can be evaluated and how model choice trades accuracy against cost.

**Design choices worth stating**

- **Hybrid verification.** Fuzzy checks (name and address matching) are done by the Verifier agent. Deterministic checks (IBAN checksum, date logic) are plain Python. This is cheaper, more reliable and easier to test than asking an LLM to do arithmetic.
- **Adapter isolation.** All Cominty SDK calls live in one gateway module, so SDK changes affect one file.
- **Budget guard.** A hard cap on runs and a result cache protect the limited trial credits.

**Honest limits.** Documents are synthetic and marked SPECIMEN. CAF submission is mocked. The eval uses a handful of cases, so results are indicative, not statistically significant.

**Keywords:** agentic systems, multi-agent orchestration, document intelligence, human-in-the-loop, evaluation, governance, model-agnostic.

---

## 2. Context Pack (paste at the start of EVERY LLM session)

```text
PROJECT: Dossier. An agent-native case processor on the Cominty Managed Agents platform.
Scenario: a university international office prepares French housing-aid (APL) files.
Pipeline: upload docs -> Intake agent -> Verifier agent -> human approval -> Action agent.
Hard constraints:
- ALL AI functionality runs on Cominty agents via the cominty-sdk. No other LLM/API calls.
- Synthetic data only, every document marked SPECIMEN. CAF submission is mocked.
- Budget: ~EUR 15 credits. Managed-agent runs may cost ~EUR 0.30 each (UNVERIFIED for trial credits) plus tokens.
  So: cache results, cap runs, test with a FakeGateway.
- Deadline: 7 Nov 2026. Prefer one flow that works end to end over many half-built features.
- Stack: Python 3.11+, FastAPI (async), SQLite (aiosqlite), pydantic v2, pytest, vanilla JS frontend
  served by FastAPI (no build step), Server-Sent Events for live updates. Deploy on Render free tier.
- Code quality: clean, modular, typed, async, structured logging, small functions, comments only
  where they add value, readability over cleverness. Production mindset: failure modes, timeouts,
  retries, idempotency, observability.

VERIFIED SDK FACTS (package `cominty-sdk`, import `cominty_sdk`, async-only, need >=1.2.0 for agents/skills):
- Auth: env COMINTY_API_KEY (sk-cmt-...) and COMINTY_USER_ID (user_...). `AsyncCominty()` reads both.
- Start a run: `run = await client.chat.start(agent_id=..., message=..., file_ids=[...])`
  agent ids look like `__cominty_agents::agent.chat` (built-in) or `agent::my-agent` (custom).
- Final text: `await run.text()`. Iterating `run` yields progress events (tool calls, LLM steps, result).
  `await run.result()` returns a reply object; `reply.files` lists files the agent produced.
- Continue a thread: `await client.chat.send(run.thread.id, agent_id=..., message=...)`
- Files: `f = await client.chat.upload_file(Path(...))` or `upload_file(bytes, filename=...)`;
  use `f.id` in `file_ids` (max 5 files per message). Download: `await client.chat.download_file(file.id)`.
- Memory: `await client.memory.create(path=..., namespace=..., purpose=..., content=...)`,
  `await client.memory.get(path, namespace=...)`, `client.memory.list_namespaces()`.
- Capabilities (what an agent may use): web, indexed_documents, mcp, skills, memory, media generation.
  Per-message scoping via `message_scope`; per-thread via `thread_capabilities` on chat.start.
- `max_steps` caps tool rounds per message.
- Config resources (SDK >=1.2.0): client.mcp, client.agents, client.skills, client.sources, client.documents.
- Errors: all subclass ComintyError (AuthError, PermissionError, NotFoundError, APIError ...).

UNVERIFIED (design for uncertainty, put behind the gateway, report what you assumed):
- Native human-approval API (run.approve / run.resume). Marketing page shows it; SDK docs may not.
  DEFAULT: implement approval in OUR app (action agent is simply not started until a human approves).
- Whether run events expose token usage or cost. DEFAULT: measure wall-clock latency ourselves, count runs,
  and let the human paste token/cost totals from the Cominty usage dashboard into eval results.
- Whether JSON-only output is guaranteed. DEFAULT: validate with pydantic, one repair retry, then fail loudly.
- How to switch an agent's model per run. DEFAULT: two agent variants (`-small`, `-strong`) configured in the dashboard.
- Older SDK snippets (0.x, `client.files.upload`, `HumanMessage`, `disabled_tools`) are OUTDATED. Do not use them.

REPO LAYOUT
dossier/
  app/
    main.py            FastAPI app factory, routers, static mount
    config.py          pydantic-settings, env vars
    models.py          pydantic schemas (Facts, Findings, ActionOutput, API models)
    db.py              aiosqlite helpers, migrations, tables
    cominty_gateway.py ONLY place that imports cominty_sdk. Protocol + real impl + FakeGateway
    pipeline.py        orchestration: intake -> verify -> approval -> action
    rules.py           deterministic checks (IBAN mod-97, date logic)
    audit.py           append-only event log
    budget.py          run counter, cache, hard cap
    routes/            cases.py, events.py, evals.py, audit.py
    evals/             dataset.py, metrics.py, runner.py
  agents/              intake.md, verifier.md, action.md, skills/dossier-check/SKILL.md
  data/synthetic/      generate.py, cases/<case_id>/*.pdf, ground_truth/<case_id>.json
  web/                 index.html, app.js, styles.css, replay/demo_run.json
  tests/
  docs/                recon.md, assets/
  README.md  requirements.txt  Dockerfile  render.yaml  .env.example

DATA CONTRACTS (JSON, validated by pydantic)
Facts = {
  "case_id": str,
  "documents": [{
    "doc_id": "lease|rib|enrollment|permit",
    "fields": { "<field_name>": {"value": str|null, "confidence": 0..1,
                                  "source": {"page": int, "quote": str} } }
  }]
}
Field names per document:
  lease:      tenant_name, landlord_name, property_address, monthly_rent_eur, charges_eur, lease_start, lease_end
  rib:        account_holder, holder_address, iban, bic, bank_name
  enrollment: student_name, date_of_birth, university, program, academic_year, enrollment_status
  permit:     holder_name, nationality, permit_type, valid_from, valid_until
Dates are ISO (YYYY-MM-DD). Money is a plain decimal string. Missing field -> value null.

Findings = {
  "findings": [{
    "id": "F1", "severity": "error|warning|info",
    "rule": "NAME_MISMATCH|ADDRESS_MISMATCH|PERMIT_EXPIRED|PERMIT_EXPIRES_DURING_LEASE|LEASE_PERIOD_INVALID|
             ENROLLMENT_YEAR_MISMATCH|IBAN_INVALID|MISSING_DOCUMENT|MISSING_FIELD|LOW_CONFIDENCE",
    "message": str,
    "evidence": [{"doc_id": str, "field": str, "value": str|null, "quote": str|null}],
    "suggested_action": str
  }],
  "missing_documents": [str],
  "ready_to_submit": bool
}

ActionOutput = {
  "form": {"<form_field>": str, ...},          // CAF-style APL draft (mocked)
  "email": {"to_role": "student", "subject": str, "body_fr": str},
  "notes_for_staff": [str]
}

API
POST /api/cases                      -> {case_id}
POST /api/cases/{id}/documents       multipart, 4 PDFs
POST /api/cases/{id}/run             starts intake+verify (async), returns {run_id}
GET  /api/cases/{id}/events          SSE stream of pipeline + audit events
GET  /api/cases/{id}                 full case state
POST /api/cases/{id}/approve         human approval -> starts action agent
GET  /api/cases/{id}/artifacts/{n}   form.json | email.md | findings.json
GET  /api/audit?case_id=             audit log
POST /api/evals/run                  body: {variants:["small","strong"], case_ids:[...]}
GET  /api/evals/latest               last eval results
GET  /healthz

CASE STATE MACHINE
CREATED -> INTAKE_RUNNING -> INTAKE_DONE -> VERIFY_RUNNING -> AWAITING_APPROVAL
        -> ACTION_RUNNING -> DONE        (any state -> FAILED with reason)

UI DESIGN TOKENS
Fonts (Google Fonts): Space Grotesk (headings), Inter (body), JetBrains Mono (code/ids).
Colors: bg #0B1020, surface #121A33, border #243055, text #E6EAF7, muted #8B95B7,
        indigo #6366F1 (primary), cyan #22D3EE (info), emerald #10B981 (success),
        amber #F59E0B (warning), rose #F43F5E (error), violet #A855F7 (agent activity).
```

---

## 3. Time plan (3 days, today is 4 Nov)

| Day | Phases | Exit criterion |
|---|---|---|
| **Wed 4 Nov** | 0, 1, 2, start 3 | One real intake run on a synthetic PDF returns valid Facts |
| **Thu 5 Nov** | finish 3, 4, start 5 | Full pipeline works in the browser with the approval gate |
| **Fri 6 Nov** | 5, 6, 7 | Deployed, eval table filled, video recorded, email drafted |
| **Sat 7 Nov** | buffer and submit | Submit **before** the deadline, with time to spare |

**If you fall behind, cut in this order:** (1) the third model or third eval case, (2) memory namespace per case, (3) the governance tab's filters, (4) Skill upload (keep the rules inside the agent instructions). **Never cut:** the verifier catch, the approval gate, the audit log, the eval table, the recorded fallback run.

---

## 4. Phases

### Phase 0: Platform recon (60 to 90 minutes, do this first)

**Goal:** replace every assumption with a fact before writing the real code.

**You do manually:** sign up at platform.cominty.ai, create an API key, copy your user id, build one test agent in the dashboard, and note your credit balance and how it is metered after your first run.

**Prompt to paste (after the Context Pack):**

```text
Write `scripts/recon.py` using cominty-sdk (async). It must run these probes in order, print a clear
PASS/FAIL line for each, catch and print every exception type and message, and write a summary to docs/recon.md:
1. Auth: create AsyncCominty(), call the cheapest possible chat.start on `__cominty_agents::agent.chat` with "ping".
2. Event shape: iterate the run and print the type name and attributes of every event; also print dir(run) and dir(reply).
3. File upload: upload a small PDF from data/sample.pdf with chat.upload_file, then start a run with file_ids asking
   for the document title. Print reply text.
4. Structured output: ask an agent to return ONLY JSON {"ok": true}; try json.loads on run.text(). Report if it was wrapped in prose or code fences.
5. Memory: memory.create then memory.get in namespace "dossier-recon".
6. Approval API: check with hasattr whether run/reply objects expose approve, resume, status, or similar. Print what exists.
7. Usage data: search events and reply for any token, cost or usage attributes and print them.
8. Latency: time probes 1 and 3 with time.perf_counter.
Do not invent SDK methods. If an attribute is missing, report it as MISSING and move on. Keep it under 150 lines.
```

**Acceptance checks**

- [ ] You can answer: do file uploads work, is JSON output clean, is there a native approval API, are usage numbers exposed?
- [ ] You know what one run costs on the usage dashboard.
- [ ] `docs/recon.md` exists. **Paste its contents into the Context Pack under UNVERIFIED** before every later phase, and delete assumptions that turned out wrong.

---

### Phase 1: Synthetic data and ground truth (about 60 minutes)

**Goal:** 3 test cases, 4 documents each, with known ground truth and planted errors.

| Case | Purpose | Planted situation |
|---|---|---|
| `case_a` | Cross-document catch | Lease address differs from the address on the RIB |
| `case_b` | Expiry catch | Residence permit expired before the lease starts |
| `case_c` | Control | Clean file, plus a name written with and without accents (`Éloïse` vs `Eloise`) that must **not** be flagged |

**Prompt to paste (after the Context Pack):**

```text
Write `data/synthetic/generate.py` that creates, for each case in the table below, four PDFs
(lease.pdf, rib.pdf, enrollment.pdf, permit.pdf) and a ground-truth JSON file at
data/synthetic/ground_truth/<case_id>.json.

Rules:
- Use reportlab and Pillow. Documents are in FRENCH, realistic in content but with GENERIC layouts.
  Do NOT copy any official layout, logo, stamp or security feature. Every page carries a large diagonal
  watermark "SPECIMEN - DONNEES FICTIVES" and a footer "Synthetic test data".
- All people, addresses, banks and numbers are fictional. IBANs must be fictional but pass the mod-97
  checksum (write a helper that builds one). Use a seeded Faker('fr_FR') or hand-written fixtures so output is reproducible.
- Make them "messy": slightly rotated pages, a two-column lease page, a table on the RIB, light noise and blur
  on one document per case (render to image then back to PDF), mixed date formats (12/09/2026, 12 septembre 2026).
- Ground truth JSON follows the Facts contract (field values only) plus `expected_findings`:
  a list of {rule, severity} that a correct verifier must produce, and `must_not_flag`: list of rules that must NOT appear.
- Cases: case_a (ADDRESS_MISMATCH between lease and rib), case_b (PERMIT_EXPIRED relative to lease_start),
  case_c (clean; student_name has accents on the enrollment certificate but not on the RIB; expected_findings empty,
  must_not_flag contains NAME_MISMATCH).
- Add a CLI: `python data/synthetic/generate.py --out data/synthetic --seed 7`.
- Add a pytest that checks the generated IBANs pass mod-97 and that the ground-truth files validate against the Facts schema.
Keep it modular: one function per document type, one per case.
```

**Acceptance checks**

- [ ] 12 PDFs open correctly and look believable but clearly marked SPECIMEN.
- [ ] Ground-truth files exist and `pytest` passes for IBAN and schema.
- [ ] `case_c` is clean and contains the accent trap.

---

### Phase 2: Agents and skill on Cominty (about 90 minutes)

**Goal:** three working agents (plus two model variants) created in the dashboard, each called successfully from a script.

The ready-to-paste agent instructions are in **Appendix A**. The Skill is in **Appendix B**.

**Create in the dashboard** (platform.cominty.ai/agents, five-step builder):

| Agent id (suggested) | Model | Capabilities |
|---|---|---|
| `dossier-intake-small` | small, cheap model | document reading only, no web |
| `dossier-intake-strong` | stronger model | same |
| `dossier-verifier-small` / `-strong` | same pair | skills (dossier-check), no web, no files |
| `dossier-action` | stronger model | no web, no files |

**Prompt to paste (after the Context Pack):**

```text
Review and harden the three agent instruction sets in Appendix A and the SKILL.md in Appendix B (pasted below).
Do this in three steps:
1. Attack them. For each agent, list the 8 most likely failure modes (e.g. invents a value for a missing field,
   wraps JSON in prose, flags accent differences as name mismatches, treats a null as a mismatch, writes the email in
   the wrong register, claims the application was submitted). Be specific.
2. Rewrite the instructions to prevent each failure mode. Keep each under 350 words. Keep the output contracts exactly as defined
   in the Context Pack. Output ONLY valid JSON for Intake, Verifier and Action, no prose, no code fences.
3. Write 6 adversarial test inputs per agent (as plain text/JSON snippets) with the expected output, so I can paste them in
   the Cominty playground and check behavior.
Then write `scripts/smoke_agents.py` that calls each agent through `app/cominty_gateway.py` (assume the interface
`async def run_agent(agent_id: str, message: str, file_paths: list[Path] | None = None, max_steps: int = 4) -> AgentResult`)
and validates outputs against the pydantic models. Do not invent SDK methods.
[PASTE APPENDIX A AND B HERE]
```

**Acceptance checks**

- [ ] Intake on `case_a` returns Facts JSON that validates, with every field either filled or `null`.
- [ ] Verifier on the extracted `case_a` Facts returns an `ADDRESS_MISMATCH` finding that cites both documents.
- [ ] Verifier on `case_c` returns **no** `NAME_MISMATCH`.
- [ ] Action output is French, formal ("vous"), and never says "submitted".
- [ ] You wrote down runs used and credit left after this phase.

---

### Phase 3: Backend and pipeline (about 4 to 5 hours)

**Goal:** the full pipeline works through an API with state, audit log, budget guard and tests, **without spending credits in tests**.

**Prompt to paste (after the Context Pack and recon results):**

```text
Implement the backend exactly per the Context Pack repo layout, data contracts, API and state machine.
Build in this order and keep each file small and typed.

1. `app/cominty_gateway.py`
   - `class AgentResult(BaseModel)`: text, files (list of name+bytes), latency_s, run_count (int, default 1), raw_events (list[dict]), usage (dict|None).
   - `class Gateway(Protocol)`: `upload(path) -> str`, `run_agent(agent_id, message, file_ids=None, max_steps=4, namespace=None) -> AgentResult`.
   - `CominityGateway`: the ONLY module importing cominty_sdk. One shared AsyncCominty client, async context managed by FastAPI lifespan.
     Timeouts, translate SDK exceptions into our own `GatewayError` (retryable vs fatal). Exponential backoff, max 2 retries on retryable errors.
     Collect every iterated event into raw_events (as dicts) and measure latency with perf_counter. Do not invent SDK methods:
     if something is not in the verified facts, isolate it behind a clearly marked TODO and a fallback.
   - `FakeGateway`: deterministic, returns canned valid outputs from tests/fixtures, can simulate invalid JSON and timeouts.
2. `app/models.py`: pydantic v2 models for Facts, Findings, ActionOutput, CaseState, API requests/responses.
3. `app/db.py` (aiosqlite): tables cases, documents, runs(stage, agent_id, status, started_at, ended_at, run_count, latency_s, usage_json),
   events (append-only audit: ts, case_id, run_id, actor agent|human|system, type, payload_json), artifacts, cache(key, value_json), eval_runs, eval_results.
   Simple versioned migrations. WAL mode.
4. `app/audit.py`: `record(case_id, actor, type, payload)`; every pipeline transition, agent call (agent id, capability scope, input hash, output hash),
   validation failure, human approval (who, when, findings acknowledged) is recorded. Also publishes to an in-memory pub/sub for SSE.
5. `app/budget.py`: hard cap `DOSSIER_MAX_RUNS` from env, counter persisted in DB, cache keyed by sha256(agent_id + message + file hashes).
   If cap reached raise `BudgetExceeded` and return HTTP 429 with a clear message. Cache hits do not count as runs.
6. `app/rules.py`: deterministic checks, pure functions: IBAN mod-97, permit_valid_until < lease_start, lease_end <= lease_start,
   enrollment academic_year vs lease dates. Return Findings in the same schema. Unit-tested.
7. `app/pipeline.py`: orchestrates upload -> intake (file_ids, max_steps 4) -> parse+validate Facts (one repair retry: send the validation error back
   to the same agent) -> deterministic rules -> verifier (Facts JSON as text, no files) -> merge findings (dedupe by rule+evidence) ->
   AWAITING_APPROVAL. `approve()` -> action agent (Facts+Findings as text) -> artifacts saved -> DONE.
   If errors exist, Action must produce the corrective email; if none, the full form. Idempotent: re-running a stage with the same input hits the cache.
   Optional (feature flag): write Facts to memory namespace `dossier-case-<id>` via the gateway.
8. Routes per the API list. SSE endpoint streams audit events as JSON lines with heartbeat. Max upload 5 MB per PDF, PDF only (check magic bytes).
9. `app/config.py` via pydantic-settings; `.env.example` with COMINTY_API_KEY, COMINTY_USER_ID, DOSSIER_MAX_RUNS, AGENT_ID_* variables.
10. Tests with pytest + FakeGateway: happy path, invalid JSON then repair, repair fails -> FAILED, budget exceeded, cache hit, approval required
    before action, SSE emits ordered events, deterministic rules. Target: tests run offline in under 10 seconds.
Use structured logging (json) with case_id and run_id on every line. Explain trade-offs you made in a short docs/ARCHITECTURE.md.
```

**Acceptance checks**

- [ ] `pytest` passes offline with `FakeGateway`.
- [ ] With the real gateway and `case_a`, `POST /run` reaches `AWAITING_APPROVAL` and the findings contain the planted error.
- [ ] `POST /approve` is rejected if the case is not in `AWAITING_APPROVAL`.
- [ ] Calling `/run` twice on the same case does not spend a second run (cache hit shows in the audit log).
- [ ] Credits used so far are written down.

---

### Phase 4: Frontend (about 3 to 4 hours)

**Goal:** a live task board, a governance view and a reliability view, with a recorded-run replay for safe demos.

**Prompt to paste (after the Context Pack):**

```text
Build the frontend in `web/` (index.html, app.js, styles.css) with NO build step: vanilla JS (ES modules), CSS variables,
served by FastAPI at "/". Use the design tokens and fonts from the Context Pack (Google Fonts: Space Grotesk, Inter, JetBrains Mono).
Dark theme, polished, responsive down to 900px, keyboard accessible, color is never the only signal (icons + text for severity).

Three tabs:
1. CASE BOARD
   - Left: drag-and-drop upload for 4 PDFs with a document-type label each, plus a "Load demo case" dropdown (case_a, case_b, case_c) that uploads
     the bundled synthetic files. A visible banner: "Synthetic data only. CAF submission is mocked."
   - Center: a task board with columns Intake -> Verify -> Approve -> Action -> Done. Each agent run is a card showing agent name,
     model variant, live status (queued, running with animated violet pulse, done, failed), elapsed seconds, and a collapsible live step log fed by SSE.
   - Findings panel: cards sorted by severity (rose error, amber warning, cyan info), each showing the rule code, message, and evidence chips
     (doc + field + value + quote). Clicking evidence highlights it in a small "extracted facts" side table.
   - Approval gate: a prominent card "Staff approval required" listing findings; buttons "Approve and generate" and "Reject". Approve is disabled until
     the reviewer ticks "I reviewed the findings". After approval show the French email and form draft with copy and download buttons.
2. GOVERNANCE
   - Table of audit events (time, actor badge agent/human/system, type, agent id, capability scope, input/output hash short, case),
     filter by case and actor, CSV export. A small summary: runs used, cache hits, budget remaining.
3. RELIABILITY
   - Run-eval form (choose variants small/strong, choose cases), a results table (rows: variant; columns: field accuracy, planted-error recall,
     false positives, runs, avg latency, cost per dossier), per-case drill-down, and a short plain-language "conclusion" box.
   - Show a clear "Measured on N synthetic cases, indicative only" note.

Extras: a "Replay recorded run" button that plays web/replay/demo_run.json through the same UI code path (fallback if the live demo breaks),
toast notifications, skeleton loaders, empty states, and a favicon. Generate a sample demo_run.json matching the SSE event format.
Provide the API client in a separate module with typed JSDoc, handle SSE reconnect with backoff, and escape all rendered text (no innerHTML with untrusted data).
```

**Acceptance checks**

- [ ] You can complete the whole flow in the browser without touching the terminal.
- [ ] The replay button works with the network cable "unplugged" (backend only).
- [ ] The approval button is disabled until the checkbox is ticked.
- [ ] The page is readable on a 1366px laptop screen, as you will record there.

---

### Phase 5: Evaluation harness (about 3 hours)

**Goal:** a repeatable eval that compares two model variants and produces the numbers for your video and README.

**Metric definitions (use exactly these so results are comparable):**

| Metric | Definition |
|---|---|
| Field accuracy | Correct fields / total ground-truth fields, after normalization (trim, case-fold, strip accents, ISO dates, decimal money) |
| Planted-error recall | Expected findings produced / expected findings |
| False positives | Findings with a rule in `must_not_flag` or not in `expected_findings` |
| Runs | Billable agent runs used (cache hits excluded) |
| Latency | Wall-clock seconds from first upload to `AWAITING_APPROVAL` |
| Cost per dossier | (runs x run fee, **if** your platform check confirmed it) + tokens cost read from the usage dashboard. Mark as "manual entry" if not exposed by the SDK |

**Prompt to paste (after the Context Pack):**

```text
Implement the evaluation harness in `app/evals/` and the `/api/evals/*` routes.

- `dataset.py`: load cases from data/synthetic (PDF paths + ground_truth JSON), validate with pydantic.
- `metrics.py`: pure, unit-tested functions implementing the metric definitions below (paste the table). Include normalization:
  strip accents (unicodedata), casefold, collapse whitespace, parse FR/ISO dates to ISO, money to Decimal.
  Return per-field results so the UI can show exactly what was wrong.
- `runner.py`: for each variant in [small, strong] and each case: run the pipeline up to AWAITING_APPROVAL via the SAME pipeline code
  (agent ids come from config per variant), collect metrics, store in eval_results, and write `data/eval/results-<timestamp>.json`.
  Sequential by default (budget safe), optional concurrency=2 via asyncio.Semaphore. Respect the budget guard; before starting,
  compute the worst-case number of runs and refuse with a clear message if it would exceed the remaining budget.
  Use the cache so re-running the report does not re-spend; add `force=true` to bypass.
- Output also a `conclusion` string generated by simple rules (not an LLM): e.g. "strong +X pts accuracy, +Y runs cost, +Z s latency;
  recommended: small for intake, strong for verifier" only if the numbers support it; otherwise say "no clear winner".
- Honesty: include N cases, date, agent ids, and a disclaimer field in the JSON. Never round up or hide failed runs: failed runs count as 0 accuracy.
- Tests with FakeGateway covering normalization edge cases (Éloïse/Eloise, 12 septembre 2026, "850,00 EUR"), perfect score, partial score, and a failed run.
Keep functions small and typed. Add a CLI: `python -m app.evals.runner --variants small strong --cases case_a case_b case_c`.
```

**Acceptance checks**

- [ ] Unit tests pass offline.
- [ ] One real eval completes and the results JSON is saved.
- [ ] The table in the Reliability tab matches the JSON.
- [ ] You copied the real numbers into a scratch file for the README and video (no invented numbers anywhere).

---

### Phase 6: Deploy and harden (about 2 hours)

**Prompt to paste (after the Context Pack):**

```text
Prepare Dossier for deployment on Render's free tier (Docker) and harden it.
1. Dockerfile (python:3.12-slim, non-root user, uvicorn with 1 worker, healthcheck on /healthz) and render.yaml.
2. Secrets only via env vars (COMINTY_API_KEY, COMINTY_USER_ID, DOSSIER_MAX_RUNS, agent ids). Never log secrets or document contents.
3. SQLite on the ephemeral disk is fine, but add a startup step that seeds the DB, plus a `/api/admin/reset` protected by a shared secret header for demo resets.
4. Protections: upload size and type checks, per-IP rate limit (simple in-memory token bucket) on POST routes, CORS locked to the app origin, security headers
   (CSP allowing only self + Google Fonts), request ID middleware, global exception handler returning typed errors.
5. A visible "demo mode" setting: when DOSSIER_MAX_RUNS is reached the UI automatically offers the recorded replay instead of failing.
6. Cold-start mitigation: a lightweight keepalive note in README (free tier sleeps), and a startup self-check that logs agent ids reachable (without spending a run).
7. Write `scripts/smoke_prod.py` that hits /healthz, loads the UI, and runs the replay path against the deployed URL (zero billable runs).
Also produce a pre-submission checklist in docs/SUBMISSION_CHECKLIST.md.
```

**Acceptance checks**

- [ ] The deployed URL loads from a phone and a laptop.
- [ ] The replay works on the deployed site without any credit use.
- [ ] One full live run works on the deployed site, then you **stop spending**.
- [ ] No secret appears in the repo (`git log -p | grep -i sk-cmt` returns nothing).

---

### Phase 7: Video, email and README (about 2 to 3 hours)

**Prompt to paste (after the Context Pack and your REAL eval numbers):**

```text
Using ONLY the real numbers I paste below, produce:
1. A 2:30 demo video script with timestamps, exact on-screen actions, and spoken lines in plain English a non-technical viewer understands.
   Structure: 0:00-0:20 the pain (messy French PDFs, 40 minutes per file is an ILLUSTRATIVE assumption: say "roughly" and label it as an assumption);
   0:20-1:30 live run, the verifier catching the planted error with its cited evidence, the approval click; 1:30-2:05 the governance/audit tab;
   2:05-2:30 the reliability table and one-sentence conclusion, plus a mention of what is mocked.
   Add a shot list, a "if the live run fails, switch to replay" fallback line, and recording tips (resolution, zoom level, cursor highlight).
2. The submission email (under 200 words): project name, one-line pitch, demo link, video link, 3 bullets on how Cominty was used
   (agents, SDK features actually used, Skill), one measured result, and 2-3 honest "builder's notes" about the SDK/docs
   (e.g. marketing snippets vs SDK reference mismatch, only if I confirmed them in Phase 0). Tone: confident, concrete, no hype.
3. A final proofreading pass on README.md (I will paste it): fix claims that are not backed by the numbers, fill placeholders, keep the colors/badges.
[PASTE REAL EVAL NUMBERS, RECON FINDINGS, AND LINKS HERE]
```

**Acceptance checks**

- [ ] Video is 2:00 to 3:00, shows the verifier catch and the approval click, and states what is mocked.
- [ ] Every number in the video, email and README comes from `data/eval/results-*.json` or the Cominty usage dashboard.
- [ ] Submitted **at least a few hours before** the deadline by replying to the Cominty email with: demo link, video link, repo link, 3 to 5 line description.

---

## 5. Final checklist

- [ ] All AI functionality runs on Cominty agents (grep your code for other AI SDKs; there should be none).
- [ ] Synthetic data only, SPECIMEN watermark visible, no real personal data anywhere.
- [ ] Verifier catch is shown with cited evidence.
- [ ] Approval gate is enforced by the backend, not only by the UI.
- [ ] Audit log shows every agent call and the human decision.
- [ ] Eval table has real numbers, N cases stated, limitations stated.
- [ ] README placeholders filled (`<...>`), banner renders, links work.
- [ ] Recorded replay works as a fallback.
- [ ] Submission sent before the deadline.

---

## Appendix A: Agent instructions (paste into the Cominty dashboard, then harden in Phase 2)

### A1. `dossier-intake`

```text
You are Dossier Intake, a document extraction agent for a university international office.
You receive 1 to 4 PDF documents (French): a lease (bail), a bank details sheet (RIB), an enrollment certificate
(certificat de scolarité) and a residence permit. All data is synthetic test data.

TASK: extract the fields listed below from each document and return ONE JSON object. Nothing else.

Fields:
lease: tenant_name, landlord_name, property_address, monthly_rent_eur, charges_eur, lease_start, lease_end
rib: account_holder, holder_address, iban, bic, bank_name
enrollment: student_name, date_of_birth, university, program, academic_year, enrollment_status
permit: holder_name, nationality, permit_type, valid_from, valid_until

RULES
- Output ONLY valid JSON, no prose, no code fences.
- Never guess. If a field is not clearly present, set value to null and confidence to 0.
- Every non-null value must include source.page and source.quote (a short exact snippet, max 12 words).
- Dates in ISO YYYY-MM-DD. Money as a plain decimal string ("850.00"). Keep names and addresses exactly as written (keep accents).
- confidence is 0 to 1; use below 0.6 when text is blurry, rotated or ambiguous.
- Identify each document by content, not by file name. If a document type is missing, omit it from "documents".
- Do not verify or compare documents. That is another agent's job.

OUTPUT SHAPE
{"case_id": "<given in the message>", "documents": [{"doc_id": "lease|rib|enrollment|permit",
 "fields": {"<field>": {"value": "...|null", "confidence": 0.0, "source": {"page": 1, "quote": "..."}}}}]}
```

### A2. `dossier-verifier` (attach the `dossier-check` skill)

```text
You are Dossier Verifier, a cross-document consistency checker. You receive a Facts JSON extracted from a student's housing-aid file.
Apply the rules from the dossier-check skill. Return ONE JSON object (Findings). Nothing else.

RULES
- Only use the Facts given. Do not use outside knowledge and do not guess missing values.
- Names match if they are the same person after ignoring case, accents, hyphen/space differences and order (SURNAME Firstname vs Firstname SURNAME).
  Do NOT flag those. Flag only different letters/words (e.g. "Martin" vs "Martins").
- Addresses match if street number, street name, postal code and city agree after ignoring case, accents and abbreviations (r. = rue, av. = avenue).
- A null value is "missing", not a mismatch. Report MISSING_FIELD with severity warning.
- Every finding must include evidence entries (doc_id, field, value, quote) copied from the Facts.
- severity: error = blocks submission; warning = needs human check; info = FYI.
- ready_to_submit is true only if there are no error findings and no missing documents.
- Output ONLY valid JSON, no prose, no code fences.

OUTPUT SHAPE
{"findings": [{"id": "F1", "severity": "error|warning|info", "rule": "...", "message": "...",
 "evidence": [{"doc_id": "...", "field": "...", "value": "...", "quote": "..."}], "suggested_action": "..."}],
 "missing_documents": ["..."], "ready_to_submit": false}
```

### A3. `dossier-action`

```text
You are Dossier Action, an assistant that drafts outputs for a staff member of a university international office.
You receive Facts JSON and Findings JSON. Return ONE JSON object (ActionOutput). Nothing else.

RULES
- Never claim anything was submitted or sent. Everything is a DRAFT for staff review. The CAF submission is mocked.
- Use only values present in Facts. Never invent values. If a form field has no source value, set it to "A COMPLETER".
- If Findings contain any severity "error": the email must politely ask the student for the corrected or missing document(s),
  naming exactly what is wrong in plain language. The form is still drafted but notes_for_staff must say it is not ready.
- If there are no errors: the email confirms that the file is complete and lists next steps for the student. 
- Email is in French, formal register ("vous"), under 180 words, clear subject line, no emojis.
- notes_for_staff: short English bullets for the reviewer (what to double-check).
- Output ONLY valid JSON, no prose, no code fences.

OUTPUT SHAPE
{"form": {"nom": "...", "prenom": "...", "date_naissance": "...", "adresse_logement": "...", "loyer_mensuel": "...",
 "charges": "...", "debut_bail": "...", "fin_bail": "...", "etablissement": "...", "iban": "..."},
 "email": {"to_role": "student", "subject": "...", "body_fr": "..."}, "notes_for_staff": ["..."]}
```

---

## Appendix B: Skill `dossier-check` (`agents/skills/dossier-check/SKILL.md`)

```markdown
---
name: dossier-check
description: Cross-document consistency rules for housing-aid (APL) student files. Use when verifying extracted Facts across lease, RIB, enrollment certificate and residence permit.
---

# Dossier check rules

Apply every rule below to the Facts JSON. Report each violation as one finding using the rule code.

| Rule | Severity | Condition |
|---|---|---|
| NAME_MISMATCH | error | Person names on lease (tenant), rib (holder), enrollment (student), permit (holder) differ after normalization (ignore case, accents, order, hyphens) |
| ADDRESS_MISMATCH | error | lease.property_address and rib.holder_address differ in number, street, postal code or city after normalization |
| PERMIT_EXPIRED | error | permit.valid_until is earlier than lease.lease_start |
| PERMIT_EXPIRES_DURING_LEASE | warning | permit.valid_until is after lease_start but before lease_end |
| LEASE_PERIOD_INVALID | error | lease_end is not after lease_start |
| ENROLLMENT_YEAR_MISMATCH | warning | lease_start does not fall within the enrollment academic_year (Sept to Aug window) |
| MISSING_DOCUMENT | error | one of lease, rib, enrollment, permit is absent |
| MISSING_FIELD | warning | a field is null |
| LOW_CONFIDENCE | info | a value used in a finding has confidence below 0.6 |

IBAN checksum and pure date arithmetic are verified by the application in code. Do not compute IBAN checksums yourself.

## Output

Return only the Findings JSON defined in the instructions. Quote evidence exactly from the Facts.
```

---

## Appendix C: Common pitfalls (read before debugging for hours)

| Symptom | Likely cause | Fix |
|---|---|---|
| JSON parse errors | Model wrapped JSON in prose or code fences | Strip fences, validate with pydantic, one repair retry that sends the validation error back |
| Credits vanish fast | Retries, repeated eval runs, per-run fee | Cache by input hash, run cap, test with `FakeGateway`, run the eval once |
| Verifier flags `Eloise` vs `Éloïse` | Normalization not stated | Keep the accent rule in the instructions and the skill; keep the `case_c` trap in the eval |
| Hallucinated SDK methods in LLM code | LLM relies on memory | Paste Verified SDK facts, keep all SDK use in `cominty_gateway.py` |
| Live demo fails while recording | Cold start, rate limit, budget cap | Use the replay and have a pre-recorded clean run |
| SSE drops on free hosting | Idle timeout | Heartbeat every 15 seconds, client reconnect with backoff |