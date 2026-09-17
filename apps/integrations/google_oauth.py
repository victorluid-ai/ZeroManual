from __future__ import annotations

import os
import secrets
import time
from urllib.parse import urlencode

import httpx

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

PURPOSE_BUSINESS = "business"
SCOPE_BUSINESS_MANAGE = "https://www.googleapis.com/auth/business.manage"
SCOPE_USERINFO_EMAIL = "https://www.googleapis.com/auth/userinfo.email"
SCOPE_OPENID = "openid"
# userinfo.email + openid are required so get_user_email (oauth2/v3/userinfo) does
# not 401 after a business-only consent. business.manage alone cannot read email.
SCOPES_BY_PURPOSE = {
    PURPOSE_BUSINESS: f"{SCOPE_BUSINESS_MANAGE} {SCOPE_USERINFO_EMAIL} {SCOPE_OPENID}",
}
SCOPES = SCOPES_BY_PURPOSE[PURPOSE_BUSINESS]


class GoogleOAuthHelper:
    def __init__(self) -> None:
        self._client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self._client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self._redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "")
        # state → (client_id, expires_at)
        self._pending: dict[str, tuple[str, float]] = {}

    def get_authorization_url(self, client_id: str) -> str:
        """Generate a Google OAuth URL and track the state token."""
        state = secrets.token_urlsafe(16)
        self._pending[state] = (client_id, time.time() + 600)
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, state: str) -> tuple[str, dict]:
        """Exchange an authorization code for tokens. Returns (client_id, token_dict)."""
        entry = self._pending.pop(state, None)
        if not entry or time.time() > entry[1]:
            raise ValueError("Invalid or expired OAuth state")
        client_id, _ = entry
        r = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        if not r.is_success:
            raise RuntimeError(f"Token exchange failed: {r.text}")
        return client_id, r.json()

    def get_user_email(self, access_token: str) -> str | None:
        """Fetch the Google account email for the given access token."""
        r = httpx.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if r.is_success:
            return r.json().get("email")
        return None
