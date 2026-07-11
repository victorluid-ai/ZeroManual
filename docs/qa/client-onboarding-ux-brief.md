# Brief: 3-click subscribe→activate→connect-Google onboarding (autonomous build+test loop)

This file is the full spec for a recurring cloud agent (fires hourly, up to 30 attempts).
The routine's own prompt is short and just points here. Read this whole file before doing anything.

## State file protocol

Check `docs/qa/client-onboarding-ux-status.md`.

- Missing -> this is attempt 1. Create it.
- Exists with `Status: DONE` or `Status: BLOCKED_AFTER_30` -> a previous run already finished or
  permanently gave up. Make no code changes, do not push. Exit immediately.
- Otherwise -> read the attempt count, findings, and next steps left by the previous run and
  continue from there instead of starting over. Increment the attempt counter before starting.

At the END of every run (success, partial progress, or new failure), rewrite the status file with:
attempt number, UTC timestamp, what you tried, what worked/broke, and precise next steps for the
next run. Then `git add`, commit, and `git push origin master`. This status file is the only memory
across firings — nothing else persists between runs of this routine.

## Goal (from the human, verbatim intent)

Right now, going from "I saw an automation on the homepage" to "it's running for me" is too many
steps: select automation -> added to cart -> checkout -> register/login -> go to `/client` ->
activation silently fails because Google isn't connected -> go to "Conectar Google" tab -> click
connect -> OAuth consent -> go back to "Mis automatizaciones" -> click Activar again. That's 7-9
clicks plus the OAuth consent screen, and about half of it is friction the app should handle for
the user, not friction the user should have to route around by hand.

Target: **3 user clicks total** to go from "browsing the homepage, not logged in" to "automation
running and Google connected" — (1) click "Suscribirme" on a product card, (2) submit the
login/register form, (3) click "Allow" on Google's own OAuth consent screen (that one is Google's
UI, not ours, and cannot be removed). Everything else — creating the account, connecting Google,
and activating the automation — must happen automatically in between, with the user landing on a
success state at the end without any further clicks. For a returning user who is already logged in
and already has Google connected, subscribing to a *new* automation should be **1 click** (an
immediate activate, no modal, no redirect).

Additionally: the **homepage** (`apps/web/zeroman/app.jsx`, served at `/`) currently has zero
awareness of whether the visitor is logged in or what they've already contracted — it must show,
for a returning logged-in user, which automations are already active/contracted directly on the
product grid (a badge/state on `ProductCard`, not just inside `/client`).

## Current flow, as verified by a research pass before this brief was written (verify against
current code before relying on it — it may have moved since)

- `GET /` serves `apps/web/zeroman/index.html`, mounting `apps/web/zeroman/app.jsx`. Products are a
  hardcoded `PRODUCTS` array (`app.jsx:108-127`); only 4 of 6 map to a real backend
  `automation_type` via `AUTOMATION_TYPE_MAP` (`app.jsx:12-17`): `reviews→google_reviews`,
  `reels→instagram_posts`, `newsletter→newsletter`, `dms→dms`.
- "Suscribirme" -> `toggleCart` (`app.jsx:264-305`, handler `app.jsx:461`) — client-side cart state
  only, nothing persisted.
- Cart "Checkout" -> `handleCheckout` (`app.jsx:474-480`) — there is no payment step. It writes cart
  automation types to `localStorage["zm_pending_activations"]` (`CART_HANDOFF_KEY`, `app.jsx:7`) and
  opens `LoginModal` in register mode.
- `LoginModal` (`app.jsx:158-262`) calls `POST /client/register` then `POST /client/login`
  (register) or `POST /client/login` (login), stores `mz_client_token` in localStorage, redirects to
  `/client`.
- `/client` (`apps/interface/client.html`) on load calls `applyPendingActivations()`
  (`client.html:332-343`), which reads `zm_pending_activations` from localStorage and calls
  `POST /client/automations/{type}/activate` for each — **silently swallows failures**, e.g. when
  Google isn't connected yet, which is always true for a brand-new signup.
- Backend `activate_client_automation` (`apps/interface/api.py:480-505`) requires
  `runtime.store.get_google_creds` to already exist; otherwise `400 "Conecta primero tu cuenta de
  Google Business"`.
- User must manually open the "Conectar Google" tab (`client.html:514-559`), click "Conectar Google
  Business →", which hits `GET /client/google/connect` (`api.py:431-434`) ->
  `GoogleOAuthHelper.get_authorization_url` (`apps/integrations/google_oauth.py:22`) -> real Google
  consent screen -> `GET /client/google/callback` (`api.py:437-457`) exchanges the code, saves creds
  via `runtime.store.save_google_creds` (`store.py:800-816`), redirects to `/client?connected=1`.
- Nothing after that automatically retries the queued activation — the user has to go back to "Mis
  automatizaciones" and click Activar again.
- Data model: `clients`, `client_sessions`, `client_google_creds` (1:1 with client, `store.py:180-189`),
  `client_automations` (the subscription/activation record, `store.py:191-200`, unique on
  `(client_id, automation_type)`, CRUD at `store.py:831-874`). No product/catalog table exists —
  products only live as the hardcoded `PRODUCTS` array in `app.jsx` and the `N8N_TEMPLATE_IDS` env map.

## What to build

1. **Carry a "pending automation" through the whole signup+OAuth round trip server-side**, not via
   localStorage (localStorage doesn't survive the OAuth redirect to Google and back reliably across
   all browsers/flows, and silent-failure is exactly the current bug). Concretely:
   - Add a way to associate a pending activation with a client server-side across the OAuth
     round-trip — e.g. a `pending_automation_type` column on `clients` (or a small ephemeral table
     keyed by `client_id`), set when the user starts the streamlined subscribe flow, cleared once
     consumed.
   - `GET /client/google/connect` should accept the current authenticated client's pending
     automation (already known server-side, no need to trust a client-supplied param) and pass an
     opaque `state` value through `GoogleOAuthHelper.get_authorization_url` if the underlying OAuth
     library supports it cleanly; otherwise it's fine to look the pending type up by `client_id`
     inside the callback instead of round-tripping it through Google's `state`.
   - `GET /client/google/callback`, after saving creds successfully, checks for a pending automation
     type for that client and — if present — calls the same activation logic
     `activate_client_automation` already uses internally, then clears the pending flag, then
     redirects to `/client?activated=<type>` (success) instead of just `?connected=1`.
2. **Homepage "Suscribirme" click must do the right thing depending on session state** (all in
   `apps/web/zeroman/app.jsx`):
   - On mount, if `mz_client_token` exists in localStorage, call `GET /client/me` then
     `GET /client/automations` to learn `active`/`available` automations for this client.
   - `ProductCard` for any id present in `AUTOMATION_TYPE_MAP` gets a visible state: **Activa** (in
     `active`), or default **Suscribirme** button. (No real "pending" state needs modeling — activation
     is synchronous once Google is connected.)
   - Clicking **Suscribirme**:
     - Not logged in -> open a single combined modal (replace the current
       add-to-cart-then-separate-checkout-then-separate-login sequence for the single-item case;
       the multi-item cart can stay as a secondary/advanced path if you want, but it must not be the
       only way to reach the fast path) that collects register-or-login credentials for *this*
       automation. On submit success, set the pending-automation server-side (see point 1) and, if
       Google isn't connected yet, redirect straight to `GET /client/google/connect` (skip any
       intermediate tab/page); if Google is already connected (e.g. returning user picking a second
       automation while this modal path is used), call the activate endpoint directly and show a
       success state without any redirect.
     - Logged in, Google connected, automation not yet active -> call
       `POST /client/automations/{type}/activate` directly from the homepage, no modal, no redirect;
       flip the card to **Activa** on success (1-click path).
     - Logged in, Google not connected yet -> set pending automation server-side and redirect
       straight to `GET /client/google/connect` (skip the modal's credential step since the user is
       already authenticated).
3. **`client.html` should handle `?activated=<type>`** on load (success toast / highlight, e.g.
   "Automatización activada ✓") and can drop (or keep as a harmless no-op fallback)
   `applyPendingActivations()`'s localStorage-based retry now that the server-side path handles it.
4. Keep the existing manual Activar/Desactivar controls inside `/client` working as-is for power
   users managing automations after the fact — this brief is about collapsing the *first-time*
   path, not removing existing functionality.

## Decisions already made with the human (do not re-litigate these)

- **Real Google OAuth consent cannot be automated** (same constraint as the prior GMB automation
  brief, `docs/qa/gmb-automation-brief.md`) — a human must click "Allow" on Google's own screen. For
  your automated test runs, mock it the same way that brief did: insert a fake `refresh_token` /
  `location_id` directly via `store.save_google_creds` for a test client instead of driving the real
  consent screen. Verifying the 3-click *design* end-to-end (minus the literal Google screen) is
  what matters; you are not expected to click through Google's UI.
- **No live n8n API calls are required for this task's automated verification.** This brief does not
  come with n8n credentials — do not go looking for them or assume they're in your environment. If
  `POST /client/automations/{type}/activate` needs to reach n8n (it does, via
  `N8nClient.duplicate_template`), stand up a small local disposable stand-in server for the 3-4 n8n
  endpoints it calls (the prior GMB brief's attempt 1 already did exactly this — see
  `docs/qa/gmb-automation-status.md`'s "Attempt 1" section for the pattern) rather than hitting the
  real instance. This task is about the click-count/UX path, not n8n workflow behavior, which was
  already validated separately.
- **Use Playwright (Chromium is pre-installed in this environment)** to drive the actual browser
  through the 3-click flow for verification — click-counting must be demonstrated, not just asserted
  from reading the code.
- **Attempt budget: 30 hourly firings.** If you reach attempt 30 without meeting the success
  criteria below, set `Status: BLOCKED_AFTER_30` in the status file with a clear explanation of what
  remains, call `PushNotification` once, and stop.

## Success criteria (all of these, verified by you with Playwright + API calls, evidence recorded
in the status file)

1. Starting from a clean state (no session), on the homepage: click "Suscribirme" on a product that
   maps to a real `automation_type` (click 1) -> modal appears -> submit register form (click 2) ->
   browser is redirected to Google's OAuth consent (in your test, stand in for the actual consent
   click since it can't be automated, but confirm the redirect URL is correct and points at Google
   with the right client/redirect params) -> simulate the callback the same way `client_google_creds`
   would be populated (click 3 stands in for "Allow") -> lands back in the app with the automation
   **already active**, no further click required. Record exactly 3 (simulated) user-initiated clicks
   in your evidence.
2. A second scenario: an already-logged-in client with Google already connected clicks "Suscribirme"
   for a *different* automation directly from the homepage -> it activates in that single click, no
   modal, no redirect, card flips to "Activa".
3. Homepage correctly shows "Activa" on the product card(s) for a logged-in client's already-active
   automations on page load (not just inside `/client`), and shows the default subscribe state for
   automations not yet contracted.
4. Existing manual Activar/Desactivar flow inside `/client` still works unmodified for
   already-onboarded clients (regression check).
5. All pre-existing tests still pass (`python3 -m pytest tests/ -q`), and add test coverage for the
   new pending-activation-through-OAuth-callback logic and the homepage activation-state fetch.

When all 5 are true, set `Status: DONE` in the status file with a summary of what was built and how
it was verified, commit, push, call `PushNotification` once with a short success message, and stop
making further changes on any subsequent firing (just verify `Status: DONE` and exit).

## Notification etiquette

Call `PushNotification` **only** in exactly two situations: when you set `Status: DONE`, or when you
set `Status: BLOCKED_AFTER_30`. Never call it for routine per-attempt progress. Keep the message
under 200 characters, one line, no markdown, and lead with the outcome.

## General rules

- Verify claims in this brief against the current code before relying on them.
- Prefer the smallest change that satisfies the success criteria; don't refactor unrelated code
  (e.g. don't rewrite the cart/multi-item flow unless it's genuinely in the way of the 3-click
  single-item path).
- Keep files under 500 lines; don't create documentation beyond the status file and what's strictly
  needed to explain a non-obvious decision.
- Never commit secrets, credentials, `.env` files, or real API keys. No real n8n or Google
  credentials should ever be needed for this task — if you find yourself wanting them, you've
  misread the brief; go back to the mocking approach above.
