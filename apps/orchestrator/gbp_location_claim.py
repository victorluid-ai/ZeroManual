"""One live Google Business location belongs to one ExManual account.

The check and the reservation run in the same SQLite transaction. A partial
unique index on active/paused ``google_reviews`` rows is the backstop when the
current data allows it. Existing duplicates are left in place.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable

from apps.integrations.google_business import is_valid_gbp_location_id

logger = logging.getLogger(__name__)

GBP_LOCATION_TAKEN_MESSAGE = (
    "Esta ficha de Google ya está conectada a otra cuenta de ExManual. "
    "Si es tuya, escríbenos y lo revisamos."
)

AMBIGUOUS_GBP_LOCATION_MESSAGE = (
    "Hay varias fichas de Google. Elige un negocio antes de activar."
)

LIVE_LOCATION_INDEX = "idx_client_automations_gbp_location_live"

_LIVE_STATUS_SQL = "('active', 'paused')"

_INDEX_SQL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS {LIVE_LOCATION_INDEX}
ON client_automations(location_id)
WHERE automation_type = 'google_reviews'
  AND status IN {_LIVE_STATUS_SQL}
  AND location_id IS NOT NULL
  AND location_id != ''
"""


class LocationClaimedError(Exception):
    """Another ExManual account already holds this Google location."""

    def __init__(self) -> None:
        super().__init__(GBP_LOCATION_TAKEN_MESSAGE)


Connect = Callable[[], sqlite3.Connection]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_locations(location_ids: list[str | None]) -> list[str]:
    return [loc for loc in location_ids if is_valid_gbp_location_id(loc)]


def _live_holders(conn: sqlite3.Connection, location_ids: list[str]) -> list[sqlite3.Row]:
    if not location_ids:
        return []
    marks = ",".join("?" * len(location_ids))
    return conn.execute(
        f"""
        SELECT ca.client_id, ca.business_id, ca.n8n_workflow_id, ca.status,
               ca.reply_mode, ca.automation_type, ca.activated_at, ca.location_id
        FROM client_automations ca
        LEFT JOIN client_businesses cb ON cb.business_id = ca.business_id
        WHERE ca.automation_type = 'google_reviews'
          AND ca.status IN {_LIVE_STATUS_SQL}
          AND (
                ca.location_id IN ({marks})
             OR cb.location_id IN ({marks})
          )
        """,
        (*location_ids, *location_ids),
    ).fetchall()


def ensure_live_location_index(conn: sqlite3.Connection) -> bool:
    """Create the partial unique index. Return False when current rows collide.

    A failure leaves every row untouched. Callers must not delete workflows or
    automations to force the index through.
    """
    try:
        conn.execute(_INDEX_SQL)
    except sqlite3.IntegrityError:
        logger.warning(
            "Índice único de location_id (active/paused) no creado: "
            "hay filas duplicadas. Datos conservados. Decisión pendiente."
        )
        return False
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
        (LIVE_LOCATION_INDEX,),
    ).fetchone()
    return row is not None


def google_locations_held_by_other(
    connect: Connect, client_id: str, location_ids: list[str | None]
) -> bool:
    valid = _valid_locations(location_ids)
    if not valid:
        return False
    conn = connect()
    try:
        holders = _live_holders(conn, valid)
    finally:
        conn.close()
    return any(row["client_id"] != client_id for row in holders)


def _automation_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "client_id": row["client_id"],
        "business_id": row["business_id"],
        "automation_type": row["automation_type"],
        "n8n_workflow_id": row["n8n_workflow_id"],
        "status": row["status"],
        "activated_at": row["activated_at"],
        "reply_mode": row["reply_mode"] or "approval",
        "location_id": row["location_id"],
    }


def _backfill_location(
    conn: sqlite3.Connection, client_id: str, business_id: str, location_id: str
) -> None:
    conn.execute(
        """
        UPDATE client_automations
        SET location_id = ?
        WHERE client_id = ? AND business_id = ? AND automation_type = 'google_reviews'
          AND (location_id IS NULL OR location_id = '')
        """,
        (location_id, client_id, business_id),
    )


def _lookup_owner(connect: Connect, location_id: str) -> sqlite3.Row | None:
    conn = connect()
    try:
        holders = _live_holders(conn, [location_id])
    finally:
        conn.close()
    return holders[0] if holders else None


def begin_google_reviews_claim(
    connect: Connect, client_id: str, business_id: str, location_id: str
) -> dict[str, Any]:
    """Reserve this location or reuse the caller's live workflow.

    ``action`` is ``reuse`` when this client already has the live automation,
    or ``reserve`` when this transaction inserted the live row. Another
    client's live row raises ``LocationClaimedError`` and does not write.
    """
    conn = connect()
    try:
        conn.execute("BEGIN EXCLUSIVE")
        holders = _live_holders(conn, [location_id])
        own = [row for row in holders if row["client_id"] == client_id]
        others = [row for row in holders if row["client_id"] != client_id]
        filled = next((row for row in own if row["n8n_workflow_id"]), None)
        if filled is not None:
            try:
                _backfill_location(conn, filled["client_id"], filled["business_id"], location_id)
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
            automation = _automation_dict(filled)
            automation["location_id"] = automation["location_id"] or location_id
            return {
                "action": "reuse",
                "workflow_id": filled["n8n_workflow_id"],
                "business_id": filled["business_id"],
                "automation": automation,
            }
        if others:
            conn.rollback()
            raise LocationClaimedError()
        if own:
            # Same client already reserved this location and n8n has not
            # returned an id yet. Do not insert or clone a second workflow.
            conn.commit()
            return {
                "action": "pending",
                "workflow_id": None,
                "business_id": own[0]["business_id"],
                "automation": _automation_dict(own[0]),
            }

        existing = conn.execute(
            """
            SELECT reply_mode FROM client_automations
            WHERE client_id = ? AND business_id = ? AND automation_type = 'google_reviews'
            """,
            (client_id, business_id),
        ).fetchone()
        reply_mode = existing["reply_mode"] if existing else "approval"
        now = _utc_now()
        if existing:
            conn.execute(
                """
                UPDATE client_automations
                SET status = 'active', n8n_workflow_id = NULL, activated_at = ?,
                    location_id = ?, reply_mode = ?
                WHERE client_id = ? AND business_id = ? AND automation_type = 'google_reviews'
                """,
                (now, location_id, reply_mode, client_id, business_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO client_automations
                    (client_id, business_id, automation_type, n8n_workflow_id,
                     status, activated_at, reply_mode, location_id)
                VALUES (?, ?, 'google_reviews', NULL, 'active', ?, ?, ?)
                """,
                (client_id, business_id, now, reply_mode, location_id),
            )
        conn.commit()
        return {
            "action": "reserve",
            "workflow_id": None,
            "business_id": business_id,
            "automation": {
                "client_id": client_id,
                "business_id": business_id,
                "automation_type": "google_reviews",
                "n8n_workflow_id": None,
                "status": "active",
                "activated_at": now,
                "reply_mode": reply_mode,
                "location_id": location_id,
            },
        }
    except LocationClaimedError:
        raise
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        owner = _lookup_owner(connect, location_id)
        if owner is not None and owner["client_id"] == client_id and owner["n8n_workflow_id"]:
            return {
                "action": "reuse",
                "workflow_id": owner["n8n_workflow_id"],
                "business_id": owner["business_id"],
                "automation": _automation_dict(owner),
            }
        if owner is not None and owner["client_id"] == client_id:
            return {
                "action": "pending",
                "workflow_id": owner["n8n_workflow_id"],
                "business_id": owner["business_id"],
                "automation": _automation_dict(owner),
            }
        if owner is not None:
            raise LocationClaimedError() from exc
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def bind_google_reviews_workflow(
    connect: Connect,
    client_id: str,
    business_id: str,
    workflow_id: str,
    location_id: str,
) -> dict[str, Any]:
    """Store the workflow id returned by n8n on the reserved row."""
    if not workflow_id:
        raise RuntimeError("n8n no devolvió un workflow_id")
    conn = connect()
    try:
        conn.execute("BEGIN EXCLUSIVE")
        cur = conn.execute(
            """
            UPDATE client_automations
            SET n8n_workflow_id = ?, location_id = ?, status = 'active'
            WHERE client_id = ? AND business_id = ? AND automation_type = 'google_reviews'
            """,
            (workflow_id, location_id, client_id, business_id),
        )
        if cur.rowcount == 0:
            raise RuntimeError("No se pudo sincronizar el workflow de n8n")
        row = conn.execute(
            """
            SELECT client_id, business_id, automation_type, n8n_workflow_id,
                   status, activated_at, reply_mode, location_id
            FROM client_automations
            WHERE client_id = ? AND business_id = ? AND automation_type = 'google_reviews'
            """,
            (client_id, business_id),
        ).fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    if row is None:
        raise RuntimeError("No se pudo sincronizar el workflow de n8n")
    return _automation_dict(row)


def abort_google_reviews_claim(connect: Connect, client_id: str, business_id: str) -> None:
    """Drop a reservation that never received an n8n workflow id."""
    conn = connect()
    try:
        conn.execute("BEGIN EXCLUSIVE")
        conn.execute(
            """
            UPDATE client_automations
            SET status = 'inactive', n8n_workflow_id = NULL
            WHERE client_id = ? AND business_id = ? AND automation_type = 'google_reviews'
              AND (n8n_workflow_id IS NULL OR n8n_workflow_id = '')
            """,
            (client_id, business_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
