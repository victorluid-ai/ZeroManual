from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from apps.integrations.google_oauth import GOOGLE_TOKEN_URL

ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
LOCATIONS_URL = "https://mybusinessbusinessinformation.googleapis.com/v1/{account}/locations"
ACCOUNTS_V4_URL = "https://mybusiness.googleapis.com/v4/accounts"
LOCATIONS_V4_URL = "https://mybusiness.googleapis.com/v4/{account}/locations"
REVIEWS_URL = "https://mybusiness.googleapis.com/v4/{location}/reviews"

# APIs that must be enabled once on the ZeroManual Google Cloud project
# (not by each end customer). Project owners enable them in Cloud Console.
REQUIRED_GMB_APIS = (
    "mybusinessaccountmanagement.googleapis.com",
    "mybusinessbusinessinformation.googleapis.com",
    "mybusiness.googleapis.com",
)

_STAR = {
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
}


def is_valid_gbp_location_id(location_id: str | None) -> bool:
    """True when ``location_id`` is a full Google Business Profile resource name."""
    return bool(
        location_id
        and location_id.startswith("accounts/")
        and "/locations/" in location_id
    )


class GoogleBusinessError(RuntimeError):
    """Raised when Google Business Profile calls fail."""


def friendly_google_error(raw: str, *, context: str = "Google Business") -> str:
    """Turn Google API JSON/HTML errors into short Spanish messages for clients."""
    text = (raw or "").strip()
    try:
        data = json.loads(text)
        err = data.get("error") or {}
        message = str(err.get("message") or "")
        status = str(err.get("status") or "")
        details = err.get("details") or []
        reason = ""
        for d in details:
            for r in d.get("reason") and [d.get("reason")] or []:
                reason = str(r)
            for meta in d.get("metadata") or []:
                pass
            if isinstance(d.get("metadata"), dict):
                reason = reason or str(d["metadata"].get("serviceTitle") or "")
            for nested in d.get("errors") or []:
                reason = reason or str(nested.get("reason") or "")
        joined = f"{status} {reason} {message}".upper()
        if "SERVICE_DISABLED" in joined or "HAS NOT BEEN USED" in joined or "DISABLED" in joined:
            return (
                "Google Business aún no está listo en ZeroManual "
                "(falta activar las APIs en el proyecto de la plataforma). "
                "El equipo lo está configurando; no tienes que hacer nada en Google Cloud."
            )
        if "PERMISSION_DENIED" in joined or status == "PERMISSION_DENIED":
            return (
                "No hay permiso para leer tu ficha de Google Business. "
                "Vuelve a conectar la cuenta y acepta todos los permisos."
            )
        if "UNAUTHENTICATED" in joined or "invalid_grant" in text.lower():
            return "La sesión de Google ha caducado. Desconecta y vuelve a conectar la cuenta."
        if message:
            return f"{context}: {message[:180]}"
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    if len(text) > 200:
        return f"{context}: error al hablar con Google. Inténtalo de nuevo en unos minutos."
    return f"{context}: {text or 'error desconocido'}"


class GoogleBusinessClient:
    """Fetch Google Business Profile reviews using a client's OAuth refresh token.

    End customers only authorize via OAuth. The ZeroManual Google Cloud project must
    have the Business Profile APIs enabled once (see REQUIRED_GMB_APIS).
    """

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._oauth_client_id = client_id or os.getenv("GOOGLE_CLIENT_ID", "")
        self._oauth_client_secret = client_secret or os.getenv("GOOGLE_CLIENT_SECRET", "")

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        if not refresh_token:
            raise GoogleBusinessError("Falta refresh_token de Google")
        if not self._oauth_client_id or not self._oauth_client_secret:
            raise GoogleBusinessError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET no configurados")
        r = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": self._oauth_client_id,
                "client_secret": self._oauth_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        if not r.is_success:
            raise GoogleBusinessError(friendly_google_error(r.text, context="Token Google"))
        return r.json()

    def list_accounts(self, access_token: str) -> list[dict[str, Any]]:
        headers = {"Authorization": f"Bearer {access_token}"}
        errors: list[str] = []
        for url in (ACCOUNTS_URL, ACCOUNTS_V4_URL):
            r = httpx.get(url, headers=headers, timeout=20)
            if r.is_success:
                return list(r.json().get("accounts") or [])
            errors.append(r.text)
        raise GoogleBusinessError(friendly_google_error(errors[-1], context="Cuentas Google Business"))

    def list_locations(self, access_token: str, account_name: str) -> list[dict[str, Any]]:
        headers = {"Authorization": f"Bearer {access_token}"}
        errors: list[str] = []

        url_info = LOCATIONS_URL.format(account=account_name)
        locations: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "readMask": "name,title,storefrontAddress",
                "pageSize": 100,
            }
            if page_token:
                params["pageToken"] = page_token
            r = httpx.get(url_info, headers=headers, params=params, timeout=20)
            if not r.is_success:
                errors.append(r.text)
                break
            data = r.json()
            locations.extend(list(data.get("locations") or []))
            page_token = data.get("nextPageToken")
            if not page_token:
                return locations

        url_v4 = LOCATIONS_V4_URL.format(account=account_name)
        r2 = httpx.get(url_v4, headers=headers, params={"pageSize": 100}, timeout=20)
        if r2.is_success:
            return list(r2.json().get("locations") or [])
        errors.append(r2.text)

        raise GoogleBusinessError(
            friendly_google_error(errors[-1], context="Ubicaciones Google Business")
        )

    def resolve_location(
        self, access_token: str, preferred_location_id: str | None = None
    ) -> str:
        """Return a full location resource name ``accounts/.../locations/...``."""
        if preferred_location_id and preferred_location_id.startswith("accounts/"):
            return preferred_location_id

        accounts = self.list_accounts(access_token)
        if not accounts:
            raise GoogleBusinessError(
                "No hay cuentas de Google Business asociadas a esta conexión"
            )

        if preferred_location_id and "/" not in preferred_location_id:
            for acc in accounts:
                candidate = f"{acc['name']}/locations/{preferred_location_id}"
                try:
                    self.list_reviews(access_token, candidate, page_size=1)
                    return candidate
                except GoogleBusinessError:
                    continue

        for acc in accounts:
            locations = self.list_locations(access_token, acc["name"])
            if locations:
                name = locations[0].get("name")
                if name:
                    # Business Information API returns names like
                    # locations/123 — prefix with account when needed.
                    if name.startswith("accounts/"):
                        return name
                    return f"{acc['name']}/{name}" if name.startswith("locations/") else (
                        f"{acc['name']}/locations/{name}"
                    )

        raise GoogleBusinessError(
            "No se encontró ninguna ubicación verificada en Google Business"
        )

    def list_reviews(
        self,
        access_token: str,
        location_name: str,
        *,
        page_size: int = 50,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        url = REVIEWS_URL.format(location=location_name)
        params: dict[str, Any] = {
            "pageSize": min(max(page_size, 1), 50),
            "orderBy": "updateTime desc",
        }
        if page_token:
            params["pageToken"] = page_token
        r = httpx.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=30,
        )
        if not r.is_success:
            raise GoogleBusinessError(friendly_google_error(r.text, context="Reseñas Google"))
        return r.json()

    def resolve_access_token(self, creds: dict[str, Any]) -> tuple[str, dict[str, str] | None]:
        """Refresh the access token if it's missing/expiring soon.

        Returns ``(access_token, token_update_or_none)`` where ``token_update`` is
        ``{"access_token", "token_expiry"}`` when a refresh happened.
        """
        access_token = creds.get("access_token") or ""
        token_update: dict[str, str] | None = None
        expiry = creds.get("token_expiry")
        needs_refresh = True
        if access_token and expiry:
            try:
                exp = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
                needs_refresh = exp <= datetime.now(timezone.utc) + timedelta(minutes=2)
            except ValueError:
                needs_refresh = True
        if needs_refresh or not access_token:
            tokens = self.refresh_access_token(creds["refresh_token"])
            access_token = tokens["access_token"]
            expires_in = int(tokens.get("expires_in") or 3600)
            token_update = {
                "access_token": access_token,
                "token_expiry": (
                    datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                ).isoformat(),
            }
        return access_token, token_update

    def list_all_businesses(self, access_token: str) -> list[dict[str, Any]]:
        """Enumerate every business location across all Google Business accounts.

        Returns dicts with ``google_account_id``, ``location_id`` (full resource
        name ``accounts/.../locations/...``) and ``business_name``.
        """
        accounts = self.list_accounts(access_token)
        businesses: list[dict[str, Any]] = []
        for acc in accounts:
            acc_name = acc.get("name") or ""
            if not acc_name:
                continue
            try:
                locations = self.list_locations(access_token, acc_name)
            except GoogleBusinessError:
                continue
            for loc in locations:
                loc_name = loc.get("name") or ""
                if not loc_name:
                    continue
                if loc_name.startswith("accounts/"):
                    full_name = loc_name
                elif loc_name.startswith("locations/"):
                    full_name = f"{acc_name}/{loc_name}"
                else:
                    full_name = f"{acc_name}/locations/{loc_name}"
                title = (
                    loc.get("title")
                    or (loc.get("locationName") if isinstance(loc.get("locationName"), str) else None)
                    or full_name
                )
                businesses.append(
                    {
                        "google_account_id": acc_name,
                        "location_id": full_name,
                        "business_name": title,
                    }
                )
        return businesses

    def list_businesses_for_creds(
        self, creds: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
        """Refresh token if needed and enumerate businesses for a client's creds."""
        access_token, token_update = self.resolve_access_token(creds)
        return self.list_all_businesses(access_token), token_update

    def fetch_reviews_for_creds(
        self,
        creds: dict[str, Any],
        *,
        page_size: int = 50,
        page_token: str | None = None,
        location_override: str | None = None,
    ) -> tuple[dict[str, Any], str, dict[str, str] | None]:
        """Refresh token if needed, resolve location, list reviews.

        Returns ``(payload, location_name, token_update_or_none)`` where
        ``token_update`` is ``{"access_token", "token_expiry"}`` when refreshed.
        ``location_override``, when given, is used verbatim instead of resolving
        one from ``creds`` — used when a client has multiple businesses and a
        specific one was selected.
        """
        access_token, token_update = self.resolve_access_token(creds)

        location = location_override or self.resolve_location(access_token, creds.get("location_id"))
        raw = self.list_reviews(
            access_token, location, page_size=page_size, page_token=page_token
        )
        reviews = [normalize_review(item) for item in (raw.get("reviews") or [])]
        payload = {
            "location_id": location,
            "average_rating": raw.get("averageRating"),
            "total_review_count": raw.get("totalReviewCount"),
            "next_page_token": raw.get("nextPageToken"),
            "reviews": reviews,
        }
        return payload, location, token_update


def normalize_review(item: dict[str, Any]) -> dict[str, Any]:
    star = item.get("starRating")
    rating = _STAR.get(str(star), star) if star is not None else None
    reviewer = item.get("reviewer") or {}
    reply = item.get("reviewReply") or {}
    name = item.get("name") or ""
    review_id = name.rsplit("/", 1)[-1] if name else None
    return {
        "review_id": review_id,
        "name": name,
        "reviewer_name": reviewer.get("displayName") or "Anónimo",
        "rating": rating,
        "star_rating": star,
        "comment": item.get("comment") or "",
        "create_time": item.get("createTime"),
        "update_time": item.get("updateTime"),
        "reply_comment": reply.get("comment"),
        "reply_update_time": reply.get("updateTime"),
        "has_reply": bool(reply.get("comment")),
    }
