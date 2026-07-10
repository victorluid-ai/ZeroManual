# GMB automation build+test — status

Status: DONE

## Attempt 4 — 2026-07-10T11:46:00Z — SUCCESS, all criteria met

### Summary

A human widened this environment's egress allowlist to include
`n8n.srv1255804.hstgr.cloud` (confirmed: direct `curl` to the real n8n API
now returns `HTTP_STATUS:200` instead of the 403 CONNECT rejection from
attempts 1-3). This unblocked the real end-to-end run. Two real bugs were
found and fixed while running the *actual* activation flow against the
*actual* n8n API for the first time (the local stand-in used in attempt 1
didn't enforce n8n's real API schema, so these were invisible until now):

1. **`POST /workflows` rejects unknown top-level fields.** The real n8n API
   returns `400 "request/body must NOT have additional properties"` for any
   field beyond `{name, nodes, connections, settings, staticData}`.
   `duplicate_template` was deep-copying the *entire* `GET /workflows/{id}`
   response (which includes `activeVersion`, `activeVersionId`,
   `description`, `isArchived`, `meta`, `pinData`, `shared`, `tags`,
   `triggerCount`, `versionCounter`, `versionId`, etc.) and only stripping
   `id`/`createdAt`/`updatedAt`/`active`. Fixed in
   `apps/integrations/n8n_client.py::duplicate_template` to build a minimal
   dict with only the accepted fields.
2. **`staticData` must be a top-level field, not nested inside `settings`.**
   The old code did `wf["settings"]["staticData"] = {...}`. Verified via a
   throwaway probe workflow that nesting it in `settings` either gets
   silently dropped or is itself rejected (`400` when combined with other
   settings keys) — the real API only persists `staticData` as its own
   top-level key (confirmed by creating a probe workflow, fetching it back,
   and seeing the round-tripped value, then deleting the probe). Fixed by
   moving `staticData` to the top level of the workflow dict.
3. **n8n rejects activating a second client's duplicate: "There is a
   conflict with one of the webhooks."** The template's `Approval Webhook`
   node has a hardcoded `path: "review-approval"` and a fixed `webhookId`.
   n8n requires webhook paths to be unique across *active* workflows, so the
   first client's duplicate activates fine but the second client's (using
   the same hardcoded path) fails — this would have blocked ZeroManual from
   ever running this automation for more than one client at a time in
   production. Fixed by adding `N8nClient._uniquify_webhooks`, called from
   `duplicate_template` for every `n8n-nodes-base.webhook` node: appends
   `-{client_id.lower()}` to the path and assigns a fresh `uuid4()`
   `webhookId`. Verified both clients' workflows activate simultaneously
   with distinct paths (`review-approval-cli-13468fa8` /
   `review-approval-cli-d697433c`).

All 43 pre-existing tests still pass after both fixes
(`python3 -m pytest tests/ -q`).

### Success criteria — evidence

1. **Test clients exist.** Registered via the real `POST /client/register`:
   fixed test client `qa-hourly-test@zeromanual.test` → `CLI-13468FA8`, and a
   freshly-created client `qa-fresh-signup-attempt4@zeromanual.test` →
   `CLI-D697433C`. Mocked Google OAuth per the brief: called
   `DataStore.save_google_creds` directly with fake `refresh_token` /
   `location_id` for both (real OAuth consent flow intentionally not
   attempted).
2. **Real n8n workflow created + activated for both clients**, via the real
   `apps.interface.api` process (`N8N_API_URL` pointed at
   `https://n8n.srv1255804.hstgr.cloud/api/v1`, using the real
   `N8N_API_KEY`) hitting `POST /client/automations/google_reviews/activate`,
   which calls the real `N8nClient.duplicate_template` — not the n8n-mcp
   connector standing in for it. Workflow ids: `Avi5ZzL2QbEpPI2T` (kept,
   renamed `TEST-QA-google_reviews-qa-hourly-test`) and `bhrwWkU3qpynBOt2`
   (fresh-signup client's, renamed `TEST-QA-google_reviews-fresh-signup`,
   deleted during cleanup below). Confirmed via `n8n_get_workflow` (mode
   `structure`) that `Generate AI Draft` fans out to both the original
   `Build Approval Email` and the new `Push Draft to ZeroManual` node;
   confirmed via direct `GET /workflows/{id}` that `staticData` (fake
   refresh_token/location_id/client_name) and per-client webhook paths
   round-tripped correctly on the real instance.
3. **Simulated review draft → stored + visible in ZeroManual.** Since n8n
   cannot reach back into this container (no public inbound URL — noted in
   every prior attempt), the n8n→ZeroManual leg was simulated exactly as the
   brief allows ("you can invoke ... with sample data"): POSTed two sample
   Spanish-language reviews (5-star and 2-star) to
   `POST /internal/automations/google_reviews/drafts` with the correct
   `X-Webhook-Secret` header → both created and immediately visible via
   `GET /client/automations/google_reviews/drafts?status=pending` for
   `qa-hourly-test`. A request with the wrong secret got `401` as expected.
4. **Edit/approve/reject from the client app works, storage reflects it.**
   Approved draft 1 with an edited `final_reply` → `status: "edited"`,
   `final_reply` stored distinct from `suggested_reply`. Rejected draft 2 →
   `status: "rejected"`. Cross-tenant isolation confirmed: the fresh-signup
   client's token got `404 "Borrador no encontrado"` trying to approve
   `qa-hourly-test`'s draft. Pending list for `qa-hourly-test` correctly
   dropped to empty afterward.
5. **Cleanup done.** `n8n_list_workflows` before cleanup showed exactly two
   `TEST-QA-` workflows (the two created this attempt) and nothing else with
   that prefix — deleted the fresh-signup one (`bhrwWkU3qpynBOt2`), keeping
   `Avi5ZzL2QbEpPI2T` (`TEST-QA-google_reviews-qa-hourly-test`) as the final
   validated result. Template `oju0vufPh9qyRqQs` untouched throughout. No
   other `TEST-QA-` workflows exist on the instance.

### What was NOT touched

- No real Google OAuth flow attempted (mocked per the brief's explicit
  decision).
- The n8n template workflow (`GMB Review Responder (Draft)`,
  `oju0vufPh9qyRqQs`) and its `Generate AI Draft` node were not modified —
  only per-client *duplicates* were created/modified, per the brief's
  smallest-change instruction.
- No non-`TEST-QA-` workflow on the real instance was read in depth,
  modified, or deleted.
- `runtime/zeromanual.db` and any real `.env` were not touched — this run
  used a disposable scratch SQLite DB
  (`/tmp/.../scratchpad/zeromanual_qa_attempt4.db`, already deleted) via
  `ZEROMANUAL_DB_PATH`.

### Secrets note

No secret values were written to any committed file. `N8N_API_KEY` and the
webhook secret used for this run were only ever exported as env vars for
the duration of the local server process, never persisted to disk or
printed into any committed artifact. The webhook secret value itself is not
recorded here (only that one was generated and used consistently for both
the push and the client-facing verification calls).

### For any future attempt (should not be needed — Status: DONE)

Per the brief's own protocol, this file now has `Status: DONE`. No further
code changes, n8n changes, or pushes should happen on any subsequent firing
of this routine — just confirm this status and exit.

## Attempt 3 — 2026-07-10T11:35:13Z

### Summary

No code changes this attempt. Same pattern as attempt 2: re-checked whether
the egress blocker to the real n8n instance was still present before
touching anything else. It is — identical failure mode, same host, same 403.
Stopping here without rebuilding or re-testing the already-verified code
path, per attempt 1/2's own next-steps plan.

### Blocker re-check (still present, identical to attempts 1 and 2)

- `curl -sS -w "%{http_code}" -H "X-N8N-API-KEY: ..." "$N8N_API_URL/workflows?limit=1"`
  from this session's container → `curl: (56) CONNECT tunnel failed, response 403`,
  `HTTP_STATUS:000`.
- `$HTTPS_PROXY/__agentproxy/status` → `recentRelayFailures`:
  `{"kind":"connect_rejected","detail":"gateway answered 403 to CONNECT
  (policy denial or upstream failure)","host":"n8n.srv1255804.hstgr.cloud:443"}`,
  timestamped `2026-07-10T11:35:13.095Z` (this attempt). Same failure class,
  proxy-level CONNECT rejection, not n8n-side.
- Cross-checked the n8n-mcp connector still works: `n8n_list_workflows`
  succeeded, returned the same 22 workflows as before (asymmetry between the
  pre-approved MCP channel and this container's own outbound HTTPS still
  holds).
- Zero `TEST-QA-` workflows exist on the real instance — nothing to clean up.
  Template `oju0vufPh9qyRqQs` (`GMB Review Responder (Draft)`) unchanged in
  shape (not re-verified in depth, per brief's instruction not to touch it).

### No code changes, no n8n changes this attempt

The build from attempt 1 (drafts table, webhook-authenticated endpoints,
client-side node injection, "Reseñas pendientes" UI tab) is unchanged and
still believed correct. `tests/` still passes as of attempt 1's commit (no
source changes since attempt 1).

### Next steps for the next attempt (unchanged from attempts 1/2, still accurate)

1. First, re-check the blocker the same way (30s): try the real
   `N8N_API_URL/workflows` curl or check `$HTTPS_PROXY/__agentproxy/status`
   `recentRelayFailures` for a fresh `n8n.srv1255804.hstgr.cloud` entry. If
   still blocked, repeat this attempt's pattern: re-confirm, record, stop —
   do not rebuild.
2. If a human has widened this environment's egress allowlist to include
   `n8n.srv1255804.hstgr.cloud`, proceed exactly per attempt 1's step 2: run
   the real `apps.interface.api` locally with `N8N_API_URL` pointed at the
   real instance, `N8N_TEMPLATE_IDS='{"google_reviews":"oju0vufPh9qyRqQs"}'`,
   a `ZEROMANUAL_WEBHOOK_SECRET` of your choosing, `N8N_WEBHOOK_CRED_ID=lyTfr0t7gzqWdl1U`
   (the durable httpHeaderAuth credential already created in n8n, still
   present), reproduce the qa-hourly-test + fresh-signup-client activation
   flow, immediately rename the resulting workflow to a `TEST-QA-` prefix,
   verify via `n8n_get_workflow` that the draft-push node is wired correctly,
   then re-verify criteria 3/4/5 against that real run and finish (delete
   every stray `TEST-QA-` workflow except the kept one, set `Status: DONE`,
   push, notify once).
3. As before: n8n cannot reach back into this container (no public inbound
   URL), so the n8n→ZeroManual leg of criterion 3 must still be simulated by
   POSTing the sample payload directly to `/internal/.../drafts`, per the
   brief's own wording ("you can invoke ... with sample data").
4. If this blocker is still present at attempt 48, that is the
   `BLOCKED_AFTER_48` reason — the code is done and locally verified; only
   the live-network leg of criterion 2 (and by extension the real-instance
   parts of 3/4/5) remains, and it depends entirely on an environment change
   only a human can make. (Attempt count so far: 3/48.)

## Attempt 2 — 2026-07-10T11:04:19Z

### Summary

No code changes this attempt. Followed attempt 1's own "next steps" exactly:
first checked whether the egress blocker to the real n8n instance was still
present before touching anything else. It is — identical failure mode, same
host, same 403. Per attempt 1's plan ("if not, re-record the same blocker...
do not burn time re-building anything... stop for this attempt"), stopping
here without rebuilding or re-testing the already-verified code path.

### Blocker re-check (still present, identical to attempt 1)

- `curl -sS -w "%{http_code}" -H "X-N8N-API-KEY: ..." "$N8N_API_URL/workflows?limit=1"`
  from this session's container → `curl: (56) CONNECT tunnel failed, response 403`,
  `HTTP_STATUS:000`. Same failure class as attempt 1 (proxy-level CONNECT
  rejection, not an n8n-side error).
- Confirmed via `$HTTPS_PROXY/__agentproxy/status` → `recentRelayFailures`:
  `{"kind":"connect_rejected","detail":"gateway answered 403 to CONNECT
  (policy denial or upstream failure)","host":"n8n.srv1255804.hstgr.cloud:443"}`,
  timestamped this attempt. Identical to attempt 1's finding. This confirms
  the sandbox's egress policy — not transient network flakiness — is what's
  blocking `apps.integrations.n8n_client.N8nClient` (plain httpx from our own
  code) from reaching the real n8n API.
- Cross-checked the n8n-mcp connector (the pre-approved channel, separate from
  this container's proxy) still works fine: `n8n_list_workflows` succeeded,
  returned the same 22 workflows as before. Confirms the asymmetry noted in
  attempt 1 still holds — MCP connector can reach the instance, our own
  container's outbound HTTPS cannot.
- Also confirms **zero `TEST-QA-` workflows exist on the real instance** right
  now (same as attempt 1) — nothing to clean up, template `oju0vufPh9qyRqQs`
  (`GMB Review Responder (Draft)`) unchanged (`updatedAt` moved to
  `2026-07-09T11:15:15Z`, an n8n-side touch unrelated to us, not the template
  content itself — not re-verified in depth since the brief says not to touch
  it and attempt 1 already confirmed its shape).

### No code changes, no n8n changes this attempt

The build from attempt 1 (drafts table, webhook-authenticated endpoints,
client-side node injection, "Reseñas pendientes" UI tab) is unchanged and
still believed correct — it was fully exercised against a faithful local
stand-in in attempt 1 and nothing in this attempt gives reason to revisit
that design. Not re-running the full local-stand-in test suite this attempt
since nothing changed that would affect its result and the brief says not to
re-litigate finished work; `tests/` still passes as of attempt 1's commit
(no source changes since).

### Next steps for the next attempt (unchanged from attempt 1, still accurate)

1. First, re-check the blocker the same way (30s): try the real
   `N8N_API_URL/workflows` curl or check `$HTTPS_PROXY/__agentproxy/status`
   `recentRelayFailures` for a fresh `n8n.srv1255804.hstgr.cloud` entry. If
   still blocked, repeat this attempt's pattern: re-confirm, record, stop —
   do not rebuild.
2. If a human has widened this environment's egress allowlist to include
   `n8n.srv1255804.hstgr.cloud`, proceed exactly per attempt 1's step 2: run
   the real `apps.interface.api` locally with `N8N_API_URL` pointed at the
   real instance, `N8N_TEMPLATE_IDS='{"google_reviews":"oju0vufPh9qyRqQs"}'`,
   a `ZEROMANUAL_WEBHOOK_SECRET` of your choosing, `N8N_WEBHOOK_CRED_ID=lyTfr0t7gzqWdl1U`
   (the durable httpHeaderAuth credential already created in n8n, still
   present), reproduce the qa-hourly-test + fresh-signup-client activation
   flow, immediately rename the resulting workflow to a `TEST-QA-` prefix,
   verify via `n8n_get_workflow` that the draft-push node is wired correctly,
   then re-verify criteria 3/4/5 against that real run and finish (delete
   every stray `TEST-QA-` workflow except the kept one, set `Status: DONE`,
   push, notify once).
3. As before: n8n cannot reach back into this container (no public inbound
   URL), so the n8n→ZeroManual leg of criterion 3 must still be simulated by
   POSTing the sample payload directly to `/internal/.../drafts`, per the
   brief's own wording ("you can invoke ... with sample data").
4. If this blocker is still present at attempt 48, that is the
   `BLOCKED_AFTER_48` reason — the code is done and locally verified; only
   the live-network leg of criterion 2 (and by extension the real-instance
   parts of 3/4/5) remains, and it depends entirely on an environment change
   only a human can make.

## Attempt 1 — 2026-07-10T10:15:53Z

### What was built this attempt

All of the "what's missing" items from the brief were implemented:

1. `apps/orchestrator/store.py`: new `automation_drafts` table (schema migration
   bumped to version 3) + `create_draft`, `get_draft`, `list_drafts`,
   `resolve_draft` methods. Statuses: `pending` / `approved` / `rejected` /
   `edited` (edited = approved with a final_reply different from the AI
   suggestion).
2. `apps/interface/api.py`:
   - `verify_webhook_secret` dependency, checks header `X-Webhook-Secret`
     against `runtime.settings.webhook_secret` (i.e. env `ZEROMANUAL_WEBHOOK_SECRET`,
     via the existing `zm_env` convention — legacy `MANUALZERO_WEBHOOK_SECRET`
     also works).
   - `POST /internal/automations/{automation_type}/drafts` — webhook-secret
     authenticated, called by n8n to push a generated draft.
   - `GET /client/automations/{automation_type}/drafts` — client-auth, lists
     drafts (optionally filter `?status=`).
   - `POST /client/drafts/{draft_id}/approve` — body `{final_reply?}`; if
     omitted, approves the AI suggestion as-is (status `approved`); if the
     text differs, status becomes `edited`. 404s if the draft doesn't belong
     to the caller's client_id (tenant isolation verified).
   - `POST /client/drafts/{draft_id}/reject`.
3. `apps/integrations/n8n_client.py`: `duplicate_template` now accepts an
   `automation_type` param. When it's `google_reviews`, `_inject_draft_push_node`
   adds a new `Push Draft to ZeroManual` HTTP Request node wired as an
   **additional** branch off `Generate AI Draft` (the existing
   `Build Approval Email` → `Send Approval Email` email path is left intact —
   smallest-change approach, per-client copy only, shared template untouched).
   The node POSTs to `{ZEROMANUAL_PUBLIC_URL}/internal/automations/{type}/drafts`
   with the client_id baked in literally (safe — it's not a secret) and auth
   via an n8n `httpHeaderAuth` credential (see below) rather than embedding the
   raw webhook secret value inside every duplicated workflow's JSON.
4. `apps/interface/client.html`: new "Reseñas pendientes" tab — lists pending
   drafts for `google_reviews` with an editable textarea + Aprobar/Rechazar
   buttons, calling the endpoints above.
5. `apps/interface/api.py` `activate_client_automation` now passes
   `automation_type=automation_type` into `duplicate_template`.

All 43 pre-existing tests still pass (`python3 -m pytest tests/ -q`).

### n8n-side setup done for real, on the real instance (via n8n-mcp connector)

- Confirmed the template workflow: id `oju0vufPh9qyRqQs`, name
  `GMB Review Responder (Draft)`. Its `Generate AI Draft` node uses credential
  `Ollama Local (VPS)` — matches the brief, not touched.
- Created a real n8n credential (type `httpHeaderAuth`) named
  **"ZeroManual Webhook Secret"**, id `lyTfr0t7gzqWdl1U`, header name
  `X-Webhook-Secret`. This is what `_inject_draft_push_node` references. It is
  a durable resource (not a `TEST-QA-` artifact) — needed for the feature to
  work at all, so it should stay. Its value must match whatever
  `ZEROMANUAL_WEBHOOK_SECRET` the real ZeroManual deployment runs with; **it
  currently does not** (see blocker below) — nobody has set that value in a
  real deployment yet, this was only exercised in a disposable local test run.
- `N8N_TEMPLATE_IDS` is confirmed empty in `.env.example` / real env. It
  needs `{"google_reviews": "oju0vufPh9qyRqQs"}` set wherever the real API
  process runs (not committed to any file, per the brief).
- Verified via `n8n_list_workflows` that the real instance has **zero**
  `TEST-QA-` workflows right now — nothing to clean up this attempt (see why
  below: no real workflow got created this run).

### BLOCKER — sandbox egress policy blocks this session's own code from reaching n8n.srv1255804.hstgr.cloud

This is the reason success criterion #2 is not yet met, and it is very
unlikely to be different on the next hourly retry unless the environment's
network policy is changed by a human:

- `apps.integrations.n8n_client.N8nClient` (plain `httpx`, run from this
  session's container) got a **hard 403 from this environment's egress proxy**
  when trying to reach `https://n8n.srv1255804.hstgr.cloud`, not from n8n
  itself. Confirmed via `curl -v` through the proxy and via
  `$HTTPS_PROXY/__agentproxy/status` → `recentRelayFailures`:
  `"gateway answered 403 to CONNECT (policy denial or upstream failure)"`,
  host `n8n.srv1255804.hstgr.cloud:443`. The proxy's own README is explicit:
  *"403/407 from the proxy: the destination host is not allowed by your
  organization's egress policy for this session. Do not retry or route around
  it — report the blocked host."*
- The n8n-mcp / n8n MCP connectors clearly CAN reach the real instance (used
  them successfully all through this attempt: listed workflows, fetched the
  template, created a credential). They run through a different, pre-approved
  channel outside this container's proxy. Our application code cannot use
  that channel — it must be `apps.integrations.n8n_client` making a normal
  outbound HTTPS call, which this sandbox's policy currently forbids.
- **This blocks literally all future attempts identically** unless a human
  adds `n8n.srv1255804.hstgr.cloud` to this environment's egress allowlist
  (Claude Code on the web → environment network policy). Retrying hourly
  will not fix it by itself.

### What WAS verified, working around the network gap

To still validate everything that doesn't require the real remote host, I
stood up a tiny disposable local FastAPI stand-in
(`/tmp/.../scratchpad/fake_n8n.py`, not committed, already killed) that mimics
the 4 n8n endpoints `N8nClient` calls (`GET/POST /workflows/{id}`,
`POST /workflows`, `POST /workflows/{id}/activate`), matching the real
template's shape (nodes `Generate AI Draft` / `Build Approval Email`). Then,
against a locally-run `apps.interface.api` (real code, `N8N_API_URL` pointed
at the stand-in):

- Registered the fixed test client `qa-hourly-test@zeromanual.test` via the
  real `POST /client/register` path, AND a second, freshly-created client
  `qa-fresh-signup-1@zeromanual.test` the same way (per the brief's
  fresh-signup requirement).
- Inserted fake `refresh_token`/`location_id` directly via
  `store.save_google_creds` for both (mocked OAuth, as instructed).
- Called the real `POST /client/automations/google_reviews/activate` for
  both clients → real `duplicate_template()` code ran, hit the (stand-in)
  n8n API, and produced a correctly-wired workflow: confirmed via the
  stand-in's stored JSON that `Generate AI Draft`'s `connections` now fan out
  to **both** `Build Approval Email` (unchanged) and the new
  `Push Draft to ZeroManual` node, with the right URL, JSON body expression,
  and `httpHeaderAuth` credential reference. `staticData` still carries
  `refresh_token`/`location_id`/`client_name` as before.
- Simulated the workflow's callback by POSTing sample review data (Spanish,
  varied ratings) to `POST /internal/automations/google_reviews/drafts` with
  the correct `X-Webhook-Secret` header → drafts created and immediately
  visible via `GET /client/automations/google_reviews/drafts`. Wrong secret →
  401, confirmed.
- Approved one draft with an edited reply (→ status `edited`, `final_reply`
  stored correctly), rejected another (→ status `rejected`), and — for the
  fresh-signup client's own draft — confirmed cross-tenant isolation: client
  2's token got 404 trying to approve client 1's draft.
- Drove the actual browser UI with Playwright against `/client`: logged in as
  `qa-hourly-test`, opened the new "Reseñas pendientes" tab, saw the pending
  draft render with reviewer/rating/text/editable textarea, clicked
  "Aprobar", and confirmed the list correctly dropped to 0 pending and the
  API reflected `status: approved`.
- `node --check` on the extracted `<script>` block: syntax OK.

So criteria 1, 3, 4 are fully met (on a disposable local run — see note
below on why nothing persists between attempts). Criterion 5 (cleanup) is
trivially true right now only because no real `TEST-QA-` workflow was
created in the real instance this attempt (the blocker prevented it) — it
has NOT been exercised against the real instance yet. Criterion 2 is coded
correctly and proven correct against a faithful stand-in, but NOT yet proven
against the real n8n API from our own code, due to the blocker above.

### State that does NOT persist between hourly attempts

Each firing gets a fresh container, so the local `runtime/zeromanual.db`
(clients, google creds, automations, drafts) does not survive between runs —
only this file, the n8n instance, and the git history do. That means:
- The "fixed, reusable test client id" only needs to be a fixed **email**
  (`qa-hourly-test@zeromanual.test`) so a human debugging later recognizes
  it; the actual `client_id` will differ every attempt since `create_client`
  always mints a fresh `CLI-XXXXXXXX`. This is fine — nothing depends on the
  client_id being literally stable across attempts, just recognizable.
- Any TEST-QA workflow created for real in n8n *would* persist across
  attempts (n8n is not ephemeral) — so once the blocker is gone and a real
  workflow gets created, follow the brief's cleanup rule precisely each run.

### Next steps for the next attempt

1. **First, check the blocker is still there** (30s check):
   `curl -v https://n8n.srv1255804.hstgr.cloud/api/v1/workflows` through the
   proxy, or reuse `$HTTPS_PROXY/__agentproxy/status`. If it now succeeds
   (human changed the egress policy), proceed to step 2. If not, re-record
   the same blocker in this file with the new attempt number, do not
   burn time re-building anything (the build above is done), and stop for
   this attempt — no code changes needed, nothing to clean up in n8n, no
   notification (not attempt 48 yet).
2. If the real API is reachable: export `N8N_API_URL` / `N8N_API_KEY` /
   `N8N_TEMPLATE_IDS='{"google_reviews":"oju0vufPh9qyRqQs"}'` /
   `ZEROMANUAL_WEBHOOK_SECRET=<pick any value>` /
   `N8N_WEBHOOK_CRED_ID=lyTfr0t7gzqWdl1U` /
   `ZEROMANUAL_PUBLIC_URL=http://localhost:8090`, run
   `python -m apps.interface.api`, redo the exact same activation flow
   described above but with `N8N_API_URL` pointed at the real instance. The
   resulting workflow will be named `oju0vufPh9qyRqQs_CLI-XXXXXXXX` (existing
   naming convention, human-reviewed, not changed) — immediately rename it via
   `n8n_update_partial_workflow` (or similar) to start with `TEST-QA-` for
   hygiene, since that's a test-tracking label, not app logic.
3. Since n8n can't reach this sandbox's `localhost:8090` from its own network
   even once the CONNECT direction is unblocked (this container has no public
   inbound URL), the actual HTTP call from the real n8n workflow to
   `/internal/.../drafts` still can't be exercised live end-to-end. Continue
   simulating that leg by POSTing the same payload directly (as this attempt
   did) — that's consistent with the brief's "you can invoke ... with sample
   data" wording. Document this network-shape limitation again if it's still
   true.
4. Once real criterion 2 is captured (workflow really created+activated in
   the real n8n instance, node injection confirmed by fetching it back via
   `n8n_get_workflow`), re-verify 3/4/5 against that real run, delete every
   `TEST-QA-` workflow except the one kept as final proof, and only then set
   `Status: DONE` + call `PushNotification` once.
5. Do not re-litigate the code design (drafts table, endpoints, node
   injection, UI tab) — it's built, tested, and working; only the
   real-network leg of criterion 2 remains.

### Secrets note

No secret values were written to any committed file. The webhook secret used
in this attempt's local test (`ZEROMANUAL_WEBHOOK_SECRET`) was generated
in-memory for the disposable local run only and discarded with the process;
it does not need to match anything real yet since no real deployment reads
it today. The n8n credential id (`lyTfr0t7gzqWdl1U`) is not a secret (it's an
opaque reference n8n itself will use to inject the real header value at
runtime) and is safe to record here.
