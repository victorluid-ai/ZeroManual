"""Browser origin while exmanual.com and the previous host both serve the app.

Stripe return URLs and the Google OAuth redirect must follow the host the
user is actually on. A single ``ZEROMANUAL_PUBLIC_URL`` cannot do that.
Unknown hosts fall back to that variable, so a spoofed ``Host`` cannot
choose an origin outside the allowlist.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from apps.zeromanual_env import zm_env

# Production hosts that may coexist. www is listed so a direct Host is
# accepted, then canonicalized to the apex redirect URI registered in Google.
_TRANSITION_HOSTS = frozenset(
    {
        "exmanual.com",
        "www.exmanual.com",
        "app.srv1255804.hstgr.cloud",
    }
)
_HTTPS_HOSTS = _TRANSITION_HOSTS
_CANONICAL_HOST = {"www.exmanual.com": "exmanual.com"}


def host_only(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if "://" in raw:
        return (urlparse(raw).hostname or "").lower()
    raw = raw.split("/")[0]
    if raw.startswith("["):
        return raw
    return raw.split(":", 1)[0]


def allowed_public_hosts() -> frozenset[str]:
    """Hosts whose browser requests may set Stripe and OAuth return URLs.

    ``ZEROMANUAL_PUBLIC_HOSTS`` replaces the built-in pair when it is set
    (comma-separated). Leave it unset during the transition. When retiring
    the old host, set it to ``exmanual.com,www.exmanual.com``.
    """
    configured = zm_env("PUBLIC_HOSTS", "").strip()
    if configured:
        return frozenset(host for host in (host_only(part) for part in configured.split(",")) if host)
    hosts = set(_TRANSITION_HOSTS)
    for source in (zm_env("PUBLIC_URL", ""), os.getenv("GOOGLE_REDIRECT_URI", "")):
        host = host_only(source)
        if host:
            hosts.add(host)
    return frozenset(hosts)


def origin_for_request(
    *,
    host: str | None,
    forwarded_host: str | None,
    forwarded_proto: str | None,
    fallback: str,
) -> str:
    """Allowlisted request host, otherwise ``fallback`` without a trailing slash."""
    allowed = allowed_public_hosts()
    candidates: list[str] = []
    if forwarded_host:
        candidates.append(forwarded_host.split(",")[0].strip())
    if host:
        candidates.append(host.strip())
    for candidate in candidates:
        name = host_only(candidate)
        if name and name in allowed:
            return _origin(name, candidate, forwarded_proto, fallback)
    return (fallback or "").rstrip("/")


def oauth_redirect_uri(
    *,
    host: str | None,
    forwarded_host: str | None,
    forwarded_proto: str | None,
) -> str:
    """Redirect URI for this browser request. Path stays ``/client/google/callback``."""
    configured = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    if configured:
        parsed = urlparse(configured)
        fallback = (
            f"{parsed.scheme}://{parsed.netloc}"
            if parsed.scheme and parsed.netloc
            else configured
        )
    else:
        fallback = zm_env("PUBLIC_URL", "http://localhost:8090").rstrip("/")
    origin = origin_for_request(
        host=host,
        forwarded_host=forwarded_host,
        forwarded_proto=forwarded_proto,
        fallback=fallback,
    )
    if not origin:
        return configured
    return f"{origin.rstrip('/')}/client/google/callback"


def _origin(name: str, raw: str, forwarded_proto: str | None, fallback: str) -> str:
    canonical = _CANONICAL_HOST.get(name, name)
    if canonical in _HTTPS_HOSTS or name in _HTTPS_HOSTS:
        return f"https://{canonical}"
    parsed = urlparse(fallback if "://" in (fallback or "") else f"https://{fallback}")
    if host_only(fallback) == name and parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    proto = (forwarded_proto or "https").split(",")[0].strip().lower()
    if proto not in ("http", "https"):
        proto = "https"
    port = ""
    bare = raw.split("/")[0]
    if bare.count(":") == 1:
        maybe = bare.rsplit(":", 1)[-1]
        if maybe.isdigit():
            port = f":{maybe}"
    return f"{proto}://{canonical}{port}"
