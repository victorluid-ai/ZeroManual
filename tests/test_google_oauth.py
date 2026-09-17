from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from apps.integrations.google_oauth import (
    PURPOSE_BUSINESS,
    SCOPE_BUSINESS_MANAGE,
    SCOPE_USERINFO_EMAIL,
    SCOPES_BY_PURPOSE,
    GoogleOAuthHelper,
)


def test_business_purpose_scopes_include_email_identity() -> None:
    scopes = SCOPES_BY_PURPOSE[PURPOSE_BUSINESS].split()
    assert SCOPE_BUSINESS_MANAGE in scopes
    assert SCOPE_USERINFO_EMAIL in scopes
    assert "openid" in scopes


def test_business_auth_url_includes_userinfo_email_and_business_manage() -> None:
    helper = GoogleOAuthHelper()
    url = helper.get_authorization_url("CLI-TEST")
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    scopes = (qs.get("scope") or [""])[0].split()
    assert SCOPE_BUSINESS_MANAGE in scopes
    assert SCOPE_USERINFO_EMAIL in scopes
    assert "openid" in scopes
    assert qs.get("access_type") == ["offline"]
    assert qs.get("prompt") == ["consent"]
    assert qs.get("response_type") == ["code"]
    assert (qs.get("state") or [""])[0]
