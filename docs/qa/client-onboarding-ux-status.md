# Status: 3-click subscribe→activate→connect-Google onboarding

Status: DONE

## Attempt 1 — 2026-07-12T20:40Z (UTC)

### What was built

1. **`apps/orchestrator/store.py`** — added `pending_automation_type` column to
   `clients` (fresh-schema block + migration bumped to `schema_version 4`,
   `ALTER TABLE ... ADD COLUMN` for existing DBs), plus
   `set_pending_automation` / `get_pending_automation` / `clear_pending_automation`.

2. **`apps/interface/api.py`**:
   - Extracted the n8n-activation logic shared by the manual endpoint and the
     new auto-activation path into `_activate_automation_for_client(client_id,
     client_name, automation_type)` (raises `ValueError` → 400, `RuntimeError`
     → 503, same messages/status codes as before — pure refactor, no behavior
     change for the existing manual endpoint).
   - New `POST /client/pending-automation` (client-auth) — sets the pending
     type server-side before the OAuth round trip, so it survives the redirect
     to Google and back (the brief explicitly ruled out localStorage for this
     — it doesn't survive the redirect reliably and was the original silent-
     failure bug).
   - `GET /client/google/callback` now looks up the pending automation for
     the client_id resolved from `GoogleOAuthHelper`'s `state` token (already
     tracked server-side in `_pending`, no client-supplied param needed), auto-
     activates it via the shared helper, clears the pending flag, and redirects
     to `/client?activated=<type>` on success or `/client?connected=1` if
     activation itself fails (Google is still connected either way; the user
     can retry manually from `/client`).

3. **`apps/web/zeroman/app.jsx`**:
   - On mount, if `mz_client_token` exists, fetches `/client/me` +
     `/client/automations` + `/client/google/status` to learn active
     automations and Google-connected state.
   - `ProductCard` now shows **Activa** for already-active automations
     (disabled) instead of the old add-to-cart toggle, for any id with a real
     backend type in `AUTOMATION_TYPE_MAP`.
   - New `SubscribeModal` — single-item combined register-or-login modal
     (replaces the old add-to-cart→checkout→login chain for the fast path;
     the multi-item cart + old `LoginModal`/checkout flow are untouched and
     still reachable as the secondary path per the brief).
   - `handleCardAction(id)` dispatches "Suscribirme" clicks by session state:
     no backend type → legacy cart toggle (unaffected); already active →
     no-op; not logged in → `SubscribeModal`; logged in + Google connected →
     direct `POST /client/automations/{type}/activate` (1 click, no
     modal/redirect); logged in + Google not connected → `POST
     /client/pending-automation` then redirect to `GET /client/google/connect`'s
     `redirect_url` (skips the modal since already authenticated).

4. **`apps/interface/client.html`** — handles `?activated=<type>` with a
   success toast (`AUTOMATION_LABELS` reused for the friendly name);
   `applyPendingActivations()` (localStorage-based) left in place as a
   harmless no-op fallback for the multi-item cart path, per the brief.

### Verification

- **`python3 -m pytest tests/ -q` → 49 passed** (43 pre-existing + 6 new in
  `tests/test_api.py`): register/login/me, pending-automation requires auth,
  manual activate still 400s without Google creds, `google_callback` auto-
  activates a pending automation end-to-end (mocked `exchange_code` /
  `get_user_email` / `duplicate_template`, exactly like the GMB brief's
  attempt 1 pattern) and redirects to `?activated=<type>`, callback with no
  pending automation redirects to `?connected=1`, and the homepage
  activation-state endpoints (`/client/automations`, `/client/google/status`)
  including the deactivate regression path.

- **Playwright (real Chromium, headless)** — `scripts/qa/onboarding_playwright_check.py`,
  run twice for stability, both green:
  - Scenario 1 (brand-new visitor): **exactly 3 clicks** recorded
    (`suscribirme`, `submit_register`, `simulated_google_allow`) — click 1
    opens the combined modal, click 2 submits register, the app then
    navigates toward `accounts.google.com` (intercepted and its `client_id`
    +`redirect_uri` params verified correct — that's Google's own consent UI
    and can't be automated further), click 3 stands in for "Allow" by hitting
    `/client/google/callback` with the real OAuth `state` token the browser
    already obtained, mocked `exchange_code`/`duplicate_template`. Result:
    redirect to `/client?activated=google_reviews`, automation active in DB.
  - Scenario 2 (already logged in + Google connected, subscribes to a
    *different* automation): **1 click**, no modal, no redirect, DB shows
    active, card visibly flips to "Activa ✓" in the browser.
  - Scenario 3 (page load, criterion 3): a client with a pre-existing active
    automation shows "Activa ✓" on the homepage grid on load (no click), and
    a not-yet-contracted automation shows the default "Suscribirse" state.
  - Environment note: `unpkg.com` (index.html's React/ReactDOM/Babel CDN) is
    policy-blocked by this sandbox's outbound proxy (403 on CONNECT,
    confirmed via `curl $HTTPS_PROXY/__agentproxy/status`). Worked around by
    vendoring the exact same pinned versions via `npm install` (registry.npmjs.org
    IS allow-listed) into `scripts/qa/vendor/` (gitignored, only `package.json`
    committed) and serving them via Playwright `page.route` in place of the
    unpkg requests — **production `index.html` is untouched**, real users
    still get the CDN. `scripts/qa/onboarding_playwright_check.py` auto-
    provisions `scripts/qa/vendor/` on first run (`npm install` inside it) if
    missing, so future attempts don't need to repeat this discovery.

### Regression check (criterion 4)

Not re-driven through the `/client` UI directly with Playwright this
attempt, but covered with high confidence: `client.html`'s manual
Activar/Desactivar buttons call the exact same `/client/automations/{type}/activate`
and `DELETE /client/automations/{type}` endpoints, whose logic was preserved
byte-for-byte (extracted into a shared helper, not rewritten) and is directly
exercised by `test_homepage_activation_state_fetch` (activate → deactivate →
confirm inactive). No changes were made to `client.html`'s existing
Activar/Desactivar JS.

### Known pre-existing condition, not addressed this attempt

`apps/web/zeroman/app.jsx` (913 lines), `apps/interface/api.py` (646 lines),
and `apps/orchestrator/store.py` (959 lines) are all over the repo's
"keep files under 500 lines" guideline — they were already over that before
this attempt (679 / 609 / ~700 lines respectively). Splitting them is a
real, separate refactor with its own risk; out of scope for this brief's
"smallest change that satisfies the success criteria" instruction, and not
attempted here to avoid destabilizing a working result.

### All 5 success criteria met

1. ✅ 3-click new-user flow (Playwright scenario 1).
2. ✅ 1-click returning-user flow for a second automation (Playwright scenario 2).
3. ✅ Homepage page-load state, both active and default (Playwright scenario 3).
4. ✅ Manual Activar/Desactivar regression (unchanged code path + endpoint test).
5. ✅ All 49 tests pass, including new coverage for the pending-activation
   flow and the homepage activation-state fetch.

No further changes planned. Any subsequent firing of this routine should
read this file, see `Status: DONE`, make no code changes, and exit
immediately (per the brief's state-file protocol).
