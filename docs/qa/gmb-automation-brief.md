# Brief: GMB review-automation, client-side management (autonomous build+test loop)

This file is the full spec for a recurring cloud agent (fires hourly, up to 48 attempts).
The routine's own prompt is short and just points here. Read this whole file before doing anything.

## State file protocol

Check `docs/qa/gmb-automation-status.md`.

- Missing -> this is attempt 1. Create it.
- Exists with `Status: DONE` or `Status: BLOCKED_AFTER_48` -> a previous run already finished or
  permanently gave up. Make no code changes, touch no n8n workflow, do not push. Exit immediately.
- Otherwise -> read the attempt count, findings, and next steps left by the previous run and
  continue from there instead of starting over. Increment the attempt counter before starting.

At the END of every run (success, partial progress, or new failure), rewrite the status file with:
attempt number, UTC timestamp, what you tried, what worked/broke, and precise next steps for the
next run. Then `git add`, commit, and `git push origin master`. This status file is the only memory
across firings — nothing else persists between runs of this routine.

## Goal

When a client activates the `google_reviews` automation from their client area
(`apps/interface/client.html`), the platform should:

1. Duplicate the n8n review-reply template workflow for that client (already implemented:
   `apps/integrations/n8n_client.py::N8nClient.duplicate_template`).
2. Let the client view and manage the AI-suggested review replies **from inside the client area**
   — this does not exist yet and is the core of what you're building.

## What already exists (verified by a human reviewer before this routine was created — don't
assume it's wrong, but do verify it still matches the current code before relying on it)

- `apps/integrations/n8n_client.py`: `N8nClient` with `get_workflow`, `create_workflow`,
  `activate_workflow`, `delete_workflow`, `duplicate_template(template_id, client_id, client_name,
  refresh_token, location_id)`. `duplicate_template` clones the template workflow, stores
  `refresh_token`/`location_id`/`client_name` in `settings.staticData`, creates it, and activates it.
- `apps/interface/api.py`: endpoints `GET /client/automations`, `POST
  /client/automations/{automation_type}/activate`, `DELETE /client/automations/{automation_type}`.
  Activation reads `N8N_TEMPLATE_IDS` env (JSON map, e.g. `{"google_reviews": "<workflow_id>"}`),
  calls `duplicate_template`, and records the result via `runtime.store.activate_automation`.
- `apps/orchestrator/store.py`: SQLite table `client_automations` (client_id, automation_type,
  n8n_workflow_id, status, activated_at) with `activate_automation` / `deactivate_automation` /
  `get_automation` / `list_client_automations`.
- `apps/interface/client.html`: tab "Mis automatizaciones" — lists automations, calls the
  activate/deactivate endpoints above. `AUTOMATION_LABELS` includes `google_reviews`.
- `apps/integrations/google_oauth.py`: real Google OAuth helper (`get_authorization_url`,
  `exchange_code`, `get_user_email`) used by `/client/google/callback` in `api.py`.
- The real n8n template workflow already exists and was verified working end-to-end with a local
  Ollama LLM (qwen3:8b) in a prior session: workflow id is whatever `N8N_TEMPLATE_IDS.google_reviews`
  should point at — check the n8n instance (via the n8n-mcp connector attached to this routine) for a
  workflow named `GMB Review Responder (Draft)`. Its AI node (`Generate AI Draft`) already calls a
  working local LLM; you should not need to touch that node.

## What's missing — this is the actual build task

1. **`N8N_TEMPLATE_IDS` is empty** in `.env.example` / probably in the real runtime env too. You
   need the real workflow ID for the `GMB Review Responder (Draft)` template (look it up via the
   n8n-mcp connector) and make sure the code path that reads `N8N_TEMPLATE_IDS` can find it for your
   test run (e.g. set it in the environment your test process runs with — do not hardcode it into
   application source, and do not commit real IDs/secrets into `.env` files).
2. **No storage or API for AI-suggested draft replies.** The n8n template currently emails a draft
   for approval (`Build Approval Email` -> `Send Approval Email` -> `Approval Webhook`) instead of
   exposing it to the ZeroManual app. You need to design and build:
   - A new table (e.g. `automation_drafts`) keyed by client_id/automation_type/review_id, storing
     the AI-suggested reply text, status (pending/approved/rejected/edited), and timestamps.
   - A new endpoint the n8n workflow calls to push a generated draft into ZeroManual (e.g.
     `POST /internal/automations/{automation_type}/drafts`), authenticated with the existing
     `ZEROMANUAL_WEBHOOK_SECRET` pattern used elsewhere in the codebase (check
     `apps/triggers`/`apps/interface/api.py` for the existing convention before inventing a new one).
   - Client-facing endpoints: list pending drafts, edit+approve a draft, reject a draft.
   - A section/tab in `client.html` to view pending drafts per automation, edit the suggested text,
     and approve/reject.
   - A modification to the **duplicated per-client copy** of the n8n workflow (not necessarily the
     shared template) so that after `Generate AI Draft`, it also (or instead) POSTs the draft to the
     new ZeroManual endpoint. Decide whether to keep the email-approval path or replace it — prefer
     the smallest change that satisfies "the client can manage it from the app".

## Decisions already made with the human (do not re-litigate these)

- **Google Business OAuth is mocked for this test.** Do not attempt a real Google OAuth consent
  flow (it requires a human clicking through Google's UI and cannot be automated). Instead, for your
  test client, insert a fake `refresh_token` / `location_id` directly into the local test database
  (bypass `google_oauth.py`'s real exchange). This is intentionally out of scope: real GMB review
  fetching/posting will not work in your test, and that's expected — you're validating the
  duplication + draft-management plumbing, not live Google connectivity.
- **Use a fixed, reusable test client id** across attempts (e.g. `qa-hourly-test`) so you're not
  piling up throwaway client records — reuse/update the same one each run.
- **You must also validate creating a brand-new test user/client** as part of the success criteria
  (the human explicitly wants proof the flow works for a fresh signup, not just a pre-existing
  fixture) — check the codebase for however clients are currently provisioned (look at `admin.html`,
  `api.py`, `apps/orchestrator` for a client-creation path) and use that mechanism; don't invent a
  new one if one already exists.
- **n8n workflow hygiene**: every workflow you create in n8n as part of a test attempt must be named
  with a `TEST-QA-` prefix. At the end of each attempt (success or failure), delete any `TEST-QA-`
  workflows you created during that attempt except the one you're keeping as the final validated
  result (if you reach success). Never touch, modify, or delete any n8n workflow that does NOT have
  the `TEST-QA-` prefix — those may be real client automations already running in production.
- **Attempt budget: 48 hourly firings.** If you reach attempt 48 without meeting the success
  criteria below, set `Status: BLOCKED_AFTER_48` in the status file with a clear explanation of what
  remains, call `PushNotification` once (see below), and stop — do not keep making changes on
  attempt 48 beyond writing the final report.

## Secrets (do not write these to any file, do not commit them, do not print them in logs you
persist — use them only as env vars / in-memory for the duration of a single command)

- `N8N_API_URL=https://n8n.srv1255804.hstgr.cloud/api/v1`
- `N8N_API_KEY` — a real n8n API key was provided out-of-band for this routine; it should be
  available to you as an environment variable at runtime. If it is not present in your environment,
  note that clearly in the status file as a blocker rather than guessing or fabricating one.

## Success criteria (all of these, verified by you, evidence recorded in the status file)

1. A test client (fixed id `qa-hourly-test`, plus at least one freshly-created client/user) exists
   in a locally-run instance of `apps.interface.api`.
2. Activating `google_reviews` for that client creates and activates a real workflow in the actual
   n8n instance (via the real `duplicate_template` code path hitting the real n8n API — not just
   the n8n-mcp connector standing in for it), named `TEST-QA-<something>`.
3. A simulated review draft (you can invoke the relevant n8n workflow/webhook with sample data, the
   same way a prior session validated the AI node) results in a draft being stored and visible via
   the new ZeroManual API/UI for that client.
4. From the client app (UI or direct API call simulating it), the draft can be edited and
   approved, and that state change is reflected in storage.
5. Cleanup: only the one kept `TEST-QA-` workflow remains in n8n; no other stray test workflows.

When all 5 are true, set `Status: DONE` in the status file with a summary of what was built and how
it was verified, commit, push, call `PushNotification` once with a short success message, and stop
making further changes on any subsequent firing (just verify `Status: DONE` and exit).

## Notification etiquette

Call `PushNotification` **only** in exactly two situations: when you set `Status: DONE`, or when you
set `Status: BLOCKED_AFTER_48`. Never call it for routine per-attempt progress. Keep the message
under 200 characters, one line, no markdown, and lead with the outcome (e.g. "ZeroManual GMB
automation: DONE, client can manage drafts in-app" or "ZeroManual GMB automation: blocked after 48
attempts, see docs/qa/gmb-automation-status.md").

## General rules

- Verify claims in this brief against the current code before relying on them — it was written by a
  human reviewer at a point in time and the code may have moved on (including from your own prior
  attempts).
- Prefer the smallest change that satisfies the success criteria; don't refactor unrelated code.
- Keep files under 500 lines; don't create documentation beyond the status file and what's strictly
  needed to explain a non-obvious decision.
- Never commit secrets, credentials, `.env` files, or real API keys.
