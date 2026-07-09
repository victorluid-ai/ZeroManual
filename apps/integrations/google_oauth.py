from __future__ import annotations

import os
import secrets
import time

import httpx

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = "https://www.googleapis.com/auth/business.manage"


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
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{GOOGLE_AUTH_URL}?{query}"

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
