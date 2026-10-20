"""La baja al final del periodo no exige SQL manual sobre una BD ya creada."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from apps.orchestrator.store import DataStore

_OLD_SUBSCRIPTION = (
    "SUB-OLD",
    "CLI-OLD",
    "google_reviews",
    "active",
    "yearly",
    "stripe",
    "sub_old",
    "cs_old",
    "2026-02-01T00:00:00+00:00",
    "2026-02-02T00:00:00+00:00",
)


def _legacy_database(path: Path) -> None:
    """Esquema de client_subscriptions anterior a las columnas de la baja."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
        INSERT INTO schema_version (version) VALUES (9);

        CREATE TABLE clients (
            client_id             TEXT PRIMARY KEY,
            name                  TEXT NOT NULL,
            email                 TEXT UNIQUE NOT NULL,
            password_hash         TEXT NOT NULL,
            plan                  TEXT NOT NULL DEFAULT 'starter',
            created_at            TEXT NOT NULL,
            pending_automation_type TEXT,
            stripe_customer_id    TEXT
        );

        CREATE TABLE client_subscriptions (
            subscription_id            TEXT PRIMARY KEY,
            client_id                  TEXT NOT NULL,
            automation_type            TEXT NOT NULL,
            status                     TEXT NOT NULL,
            billing_interval           TEXT NOT NULL DEFAULT 'monthly',
            provider                   TEXT NOT NULL DEFAULT 'stripe',
            stripe_subscription_id     TEXT,
            stripe_checkout_session_id TEXT,
            created_at                 TEXT NOT NULL,
            updated_at                 TEXT NOT NULL,
            UNIQUE (client_id, automation_type)
        );
        """
    )
    conn.execute(
        """INSERT INTO clients
           (client_id, name, email, password_hash, plan, created_at, stripe_customer_id)
           VALUES ('CLI-OLD', 'Antigua', 'antigua@example.com', 'hash', 'starter',
                   '2026-01-01T00:00:00+00:00', 'cus_old')"""
    )
    conn.execute(
        """INSERT INTO client_subscriptions
           (subscription_id, client_id, automation_type, status, billing_interval,
            provider, stripe_subscription_id, stripe_checkout_session_id,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        _OLD_SUBSCRIPTION,
    )
    conn.commit()
    conn.close()


def _columns(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(client_subscriptions)")}
    conn.close()
    return cols


def _subscription_row(path: Path) -> tuple:
    conn = sqlite3.connect(path)
    row = conn.execute(
        """SELECT subscription_id, client_id, automation_type, status, billing_interval,
                  provider, stripe_subscription_id, stripe_checkout_session_id,
                  created_at, updated_at, current_period_end, cancel_at_period_end
           FROM client_subscriptions WHERE subscription_id='SUB-OLD'"""
    ).fetchone()
    conn.close()
    return tuple(row)


def test_legacy_subscriptions_gain_period_columns_without_losing_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _legacy_database(db_path)
    assert "current_period_end" not in _columns(db_path)
    assert "cancel_at_period_end" not in _columns(db_path)

    DataStore(str(db_path))
    DataStore(str(db_path))

    assert {"current_period_end", "cancel_at_period_end"} <= _columns(db_path)
    assert _subscription_row(db_path) == _OLD_SUBSCRIPTION + (None, 0)

    conn = sqlite3.connect(db_path)
    client = conn.execute(
        "SELECT name, email, stripe_customer_id FROM clients WHERE client_id='CLI-OLD'"
    ).fetchone()
    version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    count = conn.execute("SELECT COUNT(*) FROM client_subscriptions").fetchone()[0]
    conn.close()
    assert client == ("Antigua", "antigua@example.com", "cus_old")
    assert version >= 10
    assert count == 1
