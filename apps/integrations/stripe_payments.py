"""Stripe Checkout subscriptions for the ZeroManual commercial web."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from apps.zeromanual_env import zm_env

logger = logging.getLogger(__name__)

# Server-side catalog — never trust client-sent prices.
# Keys are automation_type values used by /client/automations.
CATALOG: dict[str, dict[str, Any]] = {
    "google_reviews": {
        "product_key": "reviews",
        "name": "Reply to Google Reviews",
        "monthly_cents": 2900,
        "currency": "usd",
    },
    "instagram_posts": {
        "product_key": "reels",
        "name": "Post Social Reels",
        "monthly_cents": 3900,
        "currency": "usd",
    },
    "newsletter": {
        "product_key": "newsletter",
        "name": "Send Newsletters",
        "monthly_cents": 2400,
        "currency": "usd",
    },
    "dms": {
        "product_key": "dms",
        "name": "Reply to DMs & Comments",
        "monthly_cents": 3400,
        "currency": "usd",
    },
}

DEFAULT_TRIAL_DAYS = 14

# Clients with more than one Google Business location get this discount on
# every business beyond the first, per automation type, in the same checkout.
MULTI_BUSINESS_DISCOUNT_PCT = 20


@dataclass(frozen=True)
class StripeSettings:
    secret_key: str
    webhook_secret: str
    publishable_key: str
    public_url: str
    trial_days: int
    price_ids: dict[str, str]  # "{automation_type}:{monthly|yearly}" -> price_id


def load_stripe_settings() -> StripeSettings:
    raw_prices = zm_env("STRIPE_PRICE_IDS", "{}")
    try:
        price_ids = json.loads(raw_prices) if raw_prices else {}
    except json.JSONDecodeError:
        price_ids = {}
    if not isinstance(price_ids, dict):
        price_ids = {}
    return StripeSettings(
        secret_key=zm_env("STRIPE_SECRET_KEY", ""),
        webhook_secret=zm_env("STRIPE_WEBHOOK_SECRET", ""),
        publishable_key=zm_env("STRIPE_PUBLISHABLE_KEY", ""),
        public_url=zm_env("PUBLIC_URL", "http://localhost:8090").rstrip("/"),
        trial_days=int(zm_env("STRIPE_TRIAL_DAYS", str(DEFAULT_TRIAL_DAYS))),
        price_ids={str(k): str(v) for k, v in price_ids.items() if v},
    )


def stripe_enabled(settings: StripeSettings | None = None) -> bool:
    cfg = settings or load_stripe_settings()
    return bool(cfg.secret_key)


def validate_automation_types(types: list[str]) -> list[str]:
    cleaned: list[str] = []
    for t in types:
        key = (t or "").strip()
        if not key:
            continue
        if key not in CATALOG:
            raise ValueError(f"Automatización no disponible para cobro: {key}")
        if key not in cleaned:
            cleaned.append(key)
    if not cleaned:
        raise ValueError("Selecciona al menos una automatización")
    return cleaned


def validate_checkout_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Validate (automation_type, business_id) pairs for checkout, deduping exact repeats."""
    cleaned: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for automation_type, business_id in pairs:
        key_type = (automation_type or "").strip()
        key_biz = (business_id or "").strip()
        if not key_type or not key_biz:
            continue
        if key_type not in CATALOG:
            raise ValueError(f"Automatización no disponible para cobro: {key_type}")
        pair = (key_type, key_biz)
        if pair not in seen:
            seen.add(pair)
            cleaned.append(pair)
    if not cleaned:
        raise ValueError("Selecciona al menos una automatización")
    return cleaned


def _line_items(
    settings: StripeSettings, automation_types: list[str], interval: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for automation_type in automation_types:
        product = CATALOG[automation_type]
        price_key = f"{automation_type}:{interval}"
        price_id = settings.price_ids.get(price_key) or settings.price_ids.get(automation_type)
        if price_id:
            items.append({"price": price_id, "quantity": 1})
            continue
        unit = int(product["monthly_cents"])
        if interval == "yearly":
            # Match web marketing: annual = 10× monthly (2 months free).
            unit = unit * 10
        items.append(
            {
                "quantity": 1,
                "price_data": {
                    "currency": product["currency"],
                    "unit_amount": unit,
                    "recurring": {"interval": "year" if interval == "yearly" else "month"},
                    "product_data": {
                        "name": f"ZeroManual — {product['name']}",
                        "metadata": {
                            "automation_type": automation_type,
                            "product_key": product["product_key"],
                        },
                    },
                },
            }
        )
    return items


def _line_items_for_pairs(
    settings: StripeSettings, pairs: list[tuple[str, str]], interval: str
) -> list[dict[str, Any]]:
    """Build line items grouping by automation_type, one line item per type with
    quantity = number of businesses selected for that type. When a client buys the
    same automation for more than one business in the same checkout, every business
    beyond the first is discounted MULTI_BUSINESS_DISCOUNT_PCT% — encoded as a blended
    per-unit price since Stripe price_data doesn't support tiered discounts directly.
    """
    counts: dict[str, int] = {}
    for automation_type, _business_id in pairs:
        counts[automation_type] = counts.get(automation_type, 0) + 1

    items: list[dict[str, Any]] = []
    for automation_type, count in counts.items():
        product = CATALOG[automation_type]
        price_key = f"{automation_type}:{interval}"
        price_id = settings.price_ids.get(price_key) or settings.price_ids.get(automation_type)
        if price_id:
            # Pre-configured Stripe Price: no ad-hoc discount math available, just
            # multiply quantity across the client's businesses at full price.
            items.append({"price": price_id, "quantity": count})
            continue
        unit = int(product["monthly_cents"])
        if interval == "yearly":
            unit = unit * 10
        if count > 1:
            discounted_unit = round(unit * (1 - MULTI_BUSINESS_DISCOUNT_PCT / 100))
            total = unit + (count - 1) * discounted_unit
            blended_unit = round(total / count)
        else:
            blended_unit = unit
        items.append(
            {
                "quantity": count,
                "price_data": {
                    "currency": product["currency"],
                    "unit_amount": blended_unit,
                    "recurring": {"interval": "year" if interval == "yearly" else "month"},
                    "product_data": {
                        "name": f"ZeroManual — {product['name']}"
                        + (f" ({count} negocios)" if count > 1 else ""),
                        "metadata": {
                            "automation_type": automation_type,
                            "product_key": product["product_key"],
                            "business_count": str(count),
                        },
                    },
                },
            }
        )
    return items


def is_missing_customer_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "no such customer" in msg


def ensure_stripe_customer(
    *,
    client_id: str,
    client_email: str,
    client_name: str = "",
    stripe_customer_id: str | None = None,
    settings: StripeSettings | None = None,
) -> str:
    """Return a durable Stripe Customer id for this ZeroManual client.

    Production model: one Stripe Customer per client account, reused forever.
    We never delete Customers from the app — only cancel Subscriptions.
    """
    import stripe

    cfg = settings or load_stripe_settings()
    if not cfg.secret_key:
        raise RuntimeError("Stripe no está configurado (ZEROMANUAL_STRIPE_SECRET_KEY)")
    stripe.api_key = cfg.secret_key

    if stripe_customer_id:
        try:
            existing = stripe.Customer.retrieve(stripe_customer_id)
            data = stripe_object_to_dict(existing)
            if data.get("id") and not data.get("deleted"):
                return str(data["id"])
        except Exception as exc:
            if not is_missing_customer_error(exc):
                raise

    # Prefer reusing an existing Stripe customer with the same email + our metadata.
    try:
        found = stripe.Customer.search(
            query=f"email:'{client_email.replace(chr(39), '')}' AND metadata['zeromanual_client_id']:'{client_id}'",
            limit=1,
        )
        data = stripe_object_to_dict(found)
        rows = data.get("data") or []
        if rows:
            sid = stripe_id(rows[0])
            if sid:
                return sid
    except Exception:
        # Search may be unavailable on some accounts; fall through to create.
        pass

    created = stripe.Customer.create(
        **{
            "email": client_email,
            "metadata": {
                "zeromanual_client_id": client_id,
                "client_id": client_id,
            },
            **({"name": client_name} if client_name else {}),
        }
    )
    sid = stripe_id(created)
    if not sid:
        raise RuntimeError("Stripe Customer.create no devolvió id")
    return sid


def create_checkout_session(
    *,
    client_id: str,
    client_email: str,
    automation_types: list[str],
    billing_interval: str = "monthly",
    stripe_customer_id: str | None = None,
    client_name: str = "",
    settings: StripeSettings | None = None,
    business_pairs: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Create a Stripe Checkout Session (subscription + optional trial).

    Always attaches to a persistent Stripe Customer (created once per client).

    ``business_pairs`` (automation_type, business_id) enables multi-business
    checkout: buying the same automation for several of the client's Google
    Business locations in one session, with a discount applied from the 2nd
    business onward per automation type. When omitted, falls back to the
    simple one-line-item-per-type behaviour (single implicit business).
    """
    import stripe

    cfg = settings or load_stripe_settings()
    if not cfg.secret_key:
        raise RuntimeError("Stripe no está configurado (ZEROMANUAL_STRIPE_SECRET_KEY)")

    interval = "yearly" if billing_interval == "yearly" else "monthly"
    stripe.api_key = cfg.secret_key

    customer_id = ensure_stripe_customer(
        client_id=client_id,
        client_email=client_email,
        client_name=client_name,
        stripe_customer_id=stripe_customer_id,
        settings=cfg,
    )

    success_url = (
        f"{cfg.public_url}/client/checkout/success"
        f"?session_id={{CHECKOUT_SESSION_ID}}"
    )
    cancel_url = f"{cfg.public_url}/?checkout=cancelled"

    if business_pairs:
        pairs = validate_checkout_pairs(business_pairs)
        types = sorted({t for t, _ in pairs})
        line_items = _line_items_for_pairs(cfg, pairs, interval)
        metadata = {
            "client_id": client_id,
            "automation_types": ",".join(types),
            "business_pairs": ",".join(f"{t}:{b}" for t, b in pairs),
            "billing_interval": interval,
        }
    else:
        types = validate_automation_types(automation_types)
        line_items = _line_items(cfg, types, interval)
        metadata = {
            "client_id": client_id,
            "automation_types": ",".join(types),
            "billing_interval": interval,
        }

    params: dict[str, Any] = {
        "mode": "subscription",
        "customer": customer_id,
        "line_items": line_items,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": client_id,
        "metadata": metadata,
        "subscription_data": {
            "metadata": metadata,
        },
        "allow_promotion_codes": True,
    }
    if cfg.trial_days > 0:
        params["subscription_data"]["trial_period_days"] = cfg.trial_days

    session = stripe.checkout.Session.create(**params)
    return {
        "session_id": session["id"],
        "checkout_url": session["url"],
        "automation_types": types,
        "billing_interval": interval,
        "stripe_customer_id": customer_id,
        "business_pairs": metadata.get("business_pairs"),
    }


def stripe_object_to_dict(obj: Any) -> dict[str, Any]:
    """Normalize StripeObject / dict / nested refs to a plain dict.

    Newer stripe-python StripeObject does not support dict-like ``.get()``;
    ``dict(stripe_object)`` can also fail. Prefer ``to_dict()``.
    """
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        raw = to_dict()
        return raw if isinstance(raw, dict) else {}
    try:
        return {k: obj[k] for k in obj.keys()}  # type: ignore[attr-defined]
    except Exception:
        return {}


def stripe_id(value: Any) -> str | None:
    """Extract an id string from a plain id or expanded Stripe object."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        sid = value.get("id")
        return str(sid) if sid else None
    sid = getattr(value, "id", None)
    return str(sid) if sid else None


def retrieve_checkout_session(session_id: str, settings: StripeSettings | None = None) -> dict[str, Any]:
    import stripe

    cfg = settings or load_stripe_settings()
    stripe.api_key = cfg.secret_key
    session = stripe.checkout.Session.retrieve(session_id)
    return stripe_object_to_dict(session)


def create_billing_portal_session(
    *,
    stripe_customer_id: str,
    return_url: str | None = None,
    settings: StripeSettings | None = None,
) -> dict[str, str]:
    import stripe

    cfg = settings or load_stripe_settings()
    if not cfg.secret_key:
        raise RuntimeError("Stripe no está configurado")
    stripe.api_key = cfg.secret_key
    portal = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=return_url or f"{cfg.public_url}/client",
    )
    data = stripe_object_to_dict(portal)
    return {"portal_url": str(data.get("url") or portal["url"])}


def cancel_subscription(
    stripe_subscription_id: str,
    *,
    at_period_end: bool = False,
    settings: StripeSettings | None = None,
) -> dict[str, Any]:
    """Cancel a Stripe Subscription only — never delete the Customer.

    The Stripe Customer stays linked to the ZeroManual client for future
    checkouts, invoices, and the billing portal.
    """
    import stripe

    cfg = settings or load_stripe_settings()
    if not cfg.secret_key:
        raise RuntimeError("Stripe no está configurado")
    stripe.api_key = cfg.secret_key
    if at_period_end:
        sub = stripe.Subscription.modify(
            stripe_subscription_id, cancel_at_period_end=True
        )
    else:
        sub = stripe.Subscription.cancel(stripe_subscription_id)
    return stripe_object_to_dict(sub)


def construct_webhook_event(
    payload: bytes, signature: str, settings: StripeSettings | None = None
) -> Any:
    import stripe

    cfg = settings or load_stripe_settings()
    if not cfg.webhook_secret:
        raise RuntimeError("ZEROMANUAL_STRIPE_WEBHOOK_SECRET no configurado")
    return stripe.Webhook.construct_event(payload, signature, cfg.webhook_secret)


def parse_session_metadata(session: Any) -> tuple[str, list[str], str]:
    data = stripe_object_to_dict(session)
    meta_raw = data.get("metadata") or {}
    meta = stripe_object_to_dict(meta_raw) if not isinstance(meta_raw, dict) else meta_raw
    client_id = str(
        meta.get("client_id")
        or data.get("client_reference_id")
        or ""
    )
    raw_types = meta.get("automation_types") or ""
    types = [t.strip() for t in str(raw_types).split(",") if t.strip()]
    interval = str(meta.get("billing_interval") or "monthly")
    if not client_id:
        raise ValueError("Sesión Stripe sin client_id")
    if not types:
        raise ValueError("Sesión Stripe sin automation_types")
    return client_id, validate_automation_types(types), interval


def parse_session_business_pairs(session: Any) -> list[tuple[str, str]]:
    """Extract (automation_type, business_id) pairs from checkout metadata, if present.

    Returns an empty list for checkouts created without explicit business selection
    (single implicit business — the common case for single-location clients).
    """
    data = stripe_object_to_dict(session)
    meta_raw = data.get("metadata") or {}
    meta = stripe_object_to_dict(meta_raw) if not isinstance(meta_raw, dict) else meta_raw
    raw_pairs = meta.get("business_pairs") or ""
    pairs: list[tuple[str, str]] = []
    for chunk in str(raw_pairs).split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        automation_type, business_id = chunk.split(":", 1)
        if automation_type and business_id:
            pairs.append((automation_type, business_id))
    return pairs
