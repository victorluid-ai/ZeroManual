"""Playwright click-count verification for the 3-click subscribe/activate/connect
onboarding flow (see docs/qa/client-onboarding-ux-brief.md). Standalone script,
not part of the pytest suite -- it boots its own disposable server + browser.

Run manually:
    python3 scripts/qa/onboarding_playwright_check.py

Real Google OAuth consent cannot be automated (per the brief), so this mocks
GoogleOAuthHelper.exchange_code the same way tests/test_api.py does, and mocks
N8nClient.duplicate_template instead of hitting a real n8n instance.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PORT = 8099
BASE = f"http://127.0.0.1:{PORT}"

# unpkg.com is policy-blocked by this environment's outbound proxy (403 on
# CONNECT), so index.html's CDN <script> tags for React/ReactDOM/Babel can't
# load in a real browser here. registry.npmjs.org IS allow-listed, so vendor
# the same pinned versions locally once and serve them as unpkg stand-ins via
# page.route below -- production index.html is untouched, real users still
# get the CDN.
VENDOR_DIR = Path(__file__).parent / "vendor"
VENDOR_FILES = {
    "unpkg.com/react@18.3.1/umd/react.development.js": VENDOR_DIR / "node_modules/react/umd/react.development.js",
    "unpkg.com/react-dom@18.3.1/umd/react-dom.development.js": VENDOR_DIR / "node_modules/react-dom/umd/react-dom.development.js",
    "unpkg.com/@babel/standalone@7.29.0/babel.min.js": VENDOR_DIR / "node_modules/@babel/standalone/babel.min.js",
}


def ensure_vendor_packages() -> None:
    if all(p.is_file() for p in VENDOR_FILES.values()):
        return
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    if not (VENDOR_DIR / "package.json").is_file():
        subprocess.run(["npm", "init", "-y"], cwd=VENDOR_DIR, check=True, capture_output=True)
    subprocess.run(
        ["npm", "install", "react@18.3.1", "react-dom@18.3.1", "@babel/standalone@7.29.0", "--no-save"],
        cwd=VENDOR_DIR, check=True, capture_output=True,
    )


def setup_env(db_path: Path) -> None:
    os.environ["ZEROMANUAL_DB_PATH"] = str(db_path)
    os.environ["ZEROMANUAL_API_KEY"] = ""
    os.environ["ZEROMANUAL_AI_MODE"] = "off"
    os.environ["N8N_TEMPLATE_IDS"] = json.dumps({"google_reviews": "tpl-1", "instagram_posts": "tpl-2"})
    os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
    os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"
    os.environ["GOOGLE_REDIRECT_URI"] = f"{BASE}/client/google/callback"


def start_server():
    import importlib

    import apps.interface.api as api_module

    importlib.reload(api_module)
    api_module._n8n.duplicate_template = lambda **kwargs: "wf-fake-playwright"

    import uvicorn

    config = uvicorn.Config(api_module.app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    return api_module, server


def build_route_handler(intercepted: dict | None = None):
    def handle_route(route):
        url = route.request.url
        for frag, local_path in VENDOR_FILES.items():
            if frag in url:
                route.fulfill(status=200, content_type="application/javascript", path=str(local_path))
                return
        if intercepted is not None and url.startswith("https://accounts.google.com/"):
            intercepted["url"] = url
            route.fulfill(status=200, body="stand-in for Google consent screen")
            return
        if url.startswith("https://fonts."):
            route.abort()
            return
        route.continue_()

    return handle_route


def main() -> None:
    ensure_vendor_packages()
    tmp_dir = Path(tempfile.mkdtemp(prefix="zm-onboarding-qa-"))
    setup_env(tmp_dir / "qa.db")
    api_module, server = start_server()

    from playwright.sync_api import sync_playwright

    clicks = {"scenario_1": [], "scenario_2": []}
    failures = []

    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    launch_kwargs = {"executable_path": "/opt/pw-browsers/chromium", "headless": True}
    if proxy_url:
        launch_kwargs["proxy"] = {"server": proxy_url, "bypass": "127.0.0.1,localhost"}

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)

        # ---- Scenario 1: brand-new visitor, 3 clicks: subscribe -> submit -> (Allow) ----
        page = browser.new_page(ignore_https_errors=True)
        intercepted = {}

        page.route("**/*", build_route_handler(intercepted))
        page.goto(BASE + "/")
        page.wait_for_selector("text=ZeroManual")

        card = page.locator(".zm2-card", has_text="Responder reseñas de Google").first
        card.locator("button").first.click()  # click 1: Suscribirme
        clicks["scenario_1"].append("suscribirme")
        page.wait_for_selector("input[autocomplete='email']", timeout=5000)

        page.fill("input[autocomplete='name']", "Playwright QA")
        page.fill("input[autocomplete='email']", "pw-scenario1@example.com")
        page.fill("input[type='password']", "s3cretpw!!")
        page.locator("button", has_text="continuar").click()  # click 2: submit register form
        clicks["scenario_1"].append("submit_register")

        page.wait_for_timeout(1500)
        if "url" not in intercepted:
            failures.append("scenario 1: browser never navigated toward accounts.google.com")
        else:
            qs = parse_qs(urlparse(intercepted["url"]).query)
            if qs.get("client_id") != ["test-client-id"] or qs.get("redirect_uri") != [os.environ["GOOGLE_REDIRECT_URI"]]:
                failures.append(f"scenario 1: Google auth URL params wrong: {intercepted['url']}")

        state = next(iter(api_module._google_oauth._pending.keys()), None)
        if not state:
            failures.append("scenario 1: no pending OAuth state found on the server")
        else:
            client_row = api_module.runtime.store.authenticate_client("pw-scenario1@example.com", "s3cretpw!!")
            client_id = client_row["client_id"] if client_row else None
            api_module._google_oauth.exchange_code = lambda code, st, _cid=client_id: (
                _cid,
                {"access_token": "tok", "refresh_token": "reftok", "expires_in": 3600},
            )
            api_module._google_oauth.get_user_email = lambda access_token: "biz@example.com"
            resp = page.request.get(f"{BASE}/client/google/callback?code=fake&state={state}", max_redirects=0)
            clicks["scenario_1"].append("simulated_google_allow")
            location = resp.headers.get("location", "")
            if location != "/client?activated=google_reviews":
                failures.append(f"scenario 1: callback redirected to '{location}', expected /client?activated=google_reviews")
            active = api_module.runtime.store.list_client_automations(client_id)
            if not any(a["automation_type"] == "google_reviews" and a["status"] == "active" for a in active):
                failures.append("scenario 1: google_reviews not active after simulated Allow")
        page.close()

        # ---- Scenario 2: already logged-in + Google-connected client subscribes to a 2nd automation in 1 click ----
        client2 = api_module.runtime.store.create_client("QA Two", "pw-scenario2@example.com", "s3cretpw!!")
        token2 = api_module.runtime.store.create_client_session(client2["client_id"])
        api_module.runtime.store.save_google_creds(
            client_id=client2["client_id"], refresh_token="reftok2", access_token="tok2",
            token_expiry=None, google_email="biz2@example.com", location_id=None,
        )

        page2 = browser.new_page(ignore_https_errors=True)
        page2.route("**/*", build_route_handler())
        page2.goto(BASE + "/")
        page2.evaluate("(t) => localStorage.setItem('mz_client_token', t)", token2)
        page2.reload()
        page2.wait_for_timeout(1500)

        card2 = page2.locator(".zm2-card", has_text="Publicar reels en redes").first
        card2.locator("button").first.click()  # click 1 (and only click)
        clicks["scenario_2"].append("suscribirme")
        page2.wait_for_timeout(1000)

        if page2.locator("input[autocomplete='email']").count() > 0:
            failures.append("scenario 2: a modal appeared -- should have been a direct 1-click activation")
        active2 = api_module.runtime.store.list_client_automations(client2["client_id"])
        if not any(a["automation_type"] == "instagram_posts" and a["status"] == "active" for a in active2):
            failures.append("scenario 2: instagram_posts not active after the single click")
        if card2.locator("text=Activa").count() == 0:
            failures.append("scenario 2: card did not flip to 'Activa' in the UI")
        page2.close()

        # ---- Scenario 3: homepage page-load state for a returning client with a
        # pre-existing active automation (criterion 3: no click needed) ----
        client3 = api_module.runtime.store.create_client("QA Three", "pw-scenario3@example.com", "s3cretpw!!")
        token3 = api_module.runtime.store.create_client_session(client3["client_id"])
        api_module.runtime.store.save_google_creds(
            client_id=client3["client_id"], refresh_token="reftok3", access_token="tok3",
            token_expiry=None, google_email="biz3@example.com", location_id=None,
        )
        api_module.runtime.store.activate_automation(client3["client_id"], "google_reviews", "wf-preexisting")

        page3 = browser.new_page(ignore_https_errors=True)
        page3.route("**/*", build_route_handler())
        page3.goto(BASE + "/")
        page3.evaluate("(t) => localStorage.setItem('mz_client_token', t)", token3)
        page3.reload()
        page3.wait_for_timeout(1500)

        active_card = page3.locator(".zm2-card", has_text="Responder reseñas de Google").first
        inactive_card = page3.locator(".zm2-card", has_text="Publicar reels en redes").first
        if active_card.locator("text=Activa").count() == 0:
            failures.append("scenario 3: pre-existing active automation didn't show 'Activa' on page load")
        if inactive_card.locator("text=Suscribirse").count() == 0:
            failures.append("scenario 3: not-yet-contracted automation didn't show default 'Suscribirse' state")
        page3.close()

        browser.close()

    server.should_exit = True
    time.sleep(0.3)

    print("Clicks recorded:", clicks)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("All onboarding UX Playwright checks passed.")


if __name__ == "__main__":
    main()
