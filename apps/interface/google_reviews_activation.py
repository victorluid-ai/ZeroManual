"""Activate google_reviews for one business without sharing its location."""

from __future__ import annotations

from typing import Any

from apps.integrations.google_business import (
    GBP_LOCATION_REQUIRED_MESSAGE,
    is_valid_gbp_location_id,
    require_gbp_location_id,
)
from apps.integrations.n8n_client import negocio_ordinal
from apps.orchestrator.gbp_location_claim import (
    AMBIGUOUS_GBP_LOCATION_MESSAGE,
    LocationClaimedError,
)


def _business_for_activation(store: Any, client_id: str, business_id: str | None) -> dict:
    """Location comes only from the business row. Several valid rows are ambiguous."""
    if business_id:
        business = store.get_business(business_id)
        if not business:
            raise ValueError(GBP_LOCATION_REQUIRED_MESSAGE)
        return business
    businesses = store.list_businesses(client_id)
    valid = [row for row in businesses if is_valid_gbp_location_id(row.get("location_id"))]
    if len(valid) > 1:
        raise ValueError(AMBIGUOUS_GBP_LOCATION_MESSAGE)
    if len(valid) == 1:
        return valid[0]
    if businesses:
        return businesses[0]
    return store.ensure_default_business(client_id)


def _result(workflow_id: str | None, automation: dict | None, business_id: str) -> dict:
    return {
        "status": (automation or {}).get("status") or "active",
        "workflow_id": workflow_id,
        "automation": automation,
        "business_id": business_id,
    }


def activate_google_reviews_for_client(
    *,
    store: Any,
    n8n: Any,
    client_id: str,
    client_name: str,
    business_id: str | None,
    refresh_token: str,
    template_id: str,
) -> dict:
    business = _business_for_activation(store, client_id, business_id)
    resolved_business_id = business.get("business_id") or business_id
    if not resolved_business_id:
        raise ValueError(GBP_LOCATION_REQUIRED_MESSAGE)
    location_id = require_gbp_location_id(business.get("location_id"))
    claim = store.begin_google_reviews_claim(client_id, resolved_business_id, location_id)
    claimed_business_id = claim.get("business_id") or resolved_business_id
    if claim.get("action") != "reserve":
        return _result(claim.get("workflow_id"), claim.get("automation"), claimed_business_id)

    try:
        ordinal = negocio_ordinal(store.list_businesses(client_id), claimed_business_id)
        wf_id = n8n.duplicate_template(
            template_id=template_id,
            client_id=client_id,
            client_name=client_name,
            refresh_token=refresh_token,
            location_id=location_id,
            automation_type="google_reviews",
            business_id=claimed_business_id,
            business_ordinal=ordinal,
            activated_at=(claim.get("automation") or {}).get("activated_at"),
        )
    except LocationClaimedError:
        raise
    except ValueError:
        store.abort_google_reviews_claim(client_id, claimed_business_id)
        raise
    except Exception as exc:
        store.abort_google_reviews_claim(client_id, claimed_business_id)
        raise RuntimeError(f"Error al activar en n8n: {exc}") from exc

    try:
        record = store.bind_google_reviews_workflow(
            client_id, claimed_business_id, str(wf_id), location_id
        )
    except Exception:
        store.abort_google_reviews_claim(client_id, claimed_business_id)
        raise
    return _result(str(wf_id), record, claimed_business_id)
