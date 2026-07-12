from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from apps.integrations.settings import load_integration_settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_PBKDF2_ITERS = 260_000


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)
    return base64.b64encode(salt + key).decode()


def _verify_password(password: str, stored: str) -> bool:
    try:
        data = base64.b64decode(stored.encode())
        salt, key = data[:16], data[16:]
        new_key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)
        return secrets.compare_digest(key, new_key)
    except Exception:
        return False


class DataStore:
    def __init__(self, db_path: str = "runtime/zeromanual.db") -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self.ensure_default_admin()
        self.ensure_default_client()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS pending_approvals (
                    event_id TEXT PRIMARY KEY,
                    agent_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS invoices (
                    invoice_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    client_name TEXT,
                    amount_eur REAL,
                    status TEXT NOT NULL,
                    approved_by TEXT,
                    created_at TEXT NOT NULL,
                    invoice_number TEXT,
                    pdf_path TEXT,
                    client_email TEXT,
                    client_nif TEXT,
                    base_amount_eur REAL,
                    vat_rate REAL,
                    vat_amount_eur REAL,
                    total_eur REAL,
                    email_sent_at TEXT
                );

                CREATE TABLE IF NOT EXISTS event_log (
                    event_id TEXT PRIMARY KEY,
                    agent_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT,
                    payload_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS processed_emails (
                    uid TEXT NOT NULL,
                    folder TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY (uid, folder)
                );

                CREATE TABLE IF NOT EXISTS trigger_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    activated INTEGER NOT NULL,
                    agent_name TEXT,
                    reason TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS client_memory (
                    client_name TEXT PRIMARY KEY,
                    notes TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ledger_entries (
                    entry_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    client_name TEXT,
                    amount_eur REAL,
                    category TEXT NOT NULL,
                    reference TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS compliance_checks (
                    check_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    check_type TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS invoice_sequence (
                    year INTEGER PRIMARY KEY,
                    last_number INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT NOT NULL DEFAULT '',
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'admin',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS clients (
                    client_id             TEXT    PRIMARY KEY,
                    name                  TEXT    NOT NULL,
                    email                 TEXT    UNIQUE NOT NULL,
                    password_hash         TEXT    NOT NULL,
                    plan                  TEXT    NOT NULL DEFAULT 'starter',
                    created_at            TEXT    NOT NULL,
                    pending_automation_type TEXT
                );

                CREATE TABLE IF NOT EXISTS client_sessions (
                    token       TEXT    PRIMARY KEY,
                    client_id   TEXT    NOT NULL,
                    expires_at  TEXT    NOT NULL,
                    created_at  TEXT    NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS client_google_creds (
                    client_id     TEXT    PRIMARY KEY,
                    refresh_token TEXT    NOT NULL,
                    access_token  TEXT,
                    token_expiry  TEXT,
                    google_email  TEXT,
                    location_id   TEXT,
                    connected_at  TEXT    NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS client_automations (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id        TEXT    NOT NULL,
                    automation_type  TEXT    NOT NULL,
                    n8n_workflow_id  TEXT,
                    status           TEXT    NOT NULL DEFAULT 'inactive',
                    activated_at     TEXT,
                    UNIQUE (client_id, automation_type),
                    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS automation_drafts (
                    draft_id         TEXT    PRIMARY KEY,
                    client_id        TEXT    NOT NULL,
                    automation_type  TEXT    NOT NULL,
                    review_id        TEXT,
                    reviewer_name    TEXT,
                    rating           TEXT,
                    source_text      TEXT,
                    suggested_reply  TEXT    NOT NULL,
                    final_reply      TEXT,
                    status           TEXT    NOT NULL DEFAULT 'pending',
                    created_at       TEXT    NOT NULL,
                    updated_at       TEXT    NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
                );
                """
            )
            self._apply_migrations(conn)

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current = row[0] if row[0] is not None else 0

        if current < 1:
            existing = {r[1] for r in conn.execute("PRAGMA table_info(invoices)").fetchall()}
            for column, col_type in (
                ("invoice_number", "TEXT"),
                ("pdf_path", "TEXT"),
                ("client_email", "TEXT"),
                ("client_nif", "TEXT"),
                ("base_amount_eur", "REAL"),
                ("vat_rate", "REAL"),
                ("vat_amount_eur", "REAL"),
                ("total_eur", "REAL"),
                ("email_sent_at", "TEXT"),
            ):
                if column not in existing:
                    conn.execute(f"ALTER TABLE invoices ADD COLUMN {column} {col_type}")
            conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (1)")

        if current < 2:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    client_id     TEXT    PRIMARY KEY,
                    name          TEXT    NOT NULL,
                    email         TEXT    UNIQUE NOT NULL,
                    password_hash TEXT    NOT NULL,
                    plan          TEXT    NOT NULL DEFAULT 'starter',
                    created_at    TEXT    NOT NULL
                );
                CREATE TABLE IF NOT EXISTS client_sessions (
                    token       TEXT    PRIMARY KEY,
                    client_id   TEXT    NOT NULL,
                    expires_at  TEXT    NOT NULL,
                    created_at  TEXT    NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS client_google_creds (
                    client_id     TEXT    PRIMARY KEY,
                    refresh_token TEXT    NOT NULL,
                    access_token  TEXT,
                    token_expiry  TEXT,
                    google_email  TEXT,
                    location_id   TEXT,
                    connected_at  TEXT    NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS client_automations (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id        TEXT    NOT NULL,
                    automation_type  TEXT    NOT NULL,
                    n8n_workflow_id  TEXT,
                    status           TEXT    NOT NULL DEFAULT 'inactive',
                    activated_at     TEXT,
                    UNIQUE (client_id, automation_type),
                    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (2)")

        if current < 3:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS automation_drafts (
                    draft_id         TEXT    PRIMARY KEY,
                    client_id        TEXT    NOT NULL,
                    automation_type  TEXT    NOT NULL,
                    review_id        TEXT,
                    reviewer_name    TEXT,
                    rating           TEXT,
                    source_text      TEXT,
                    suggested_reply  TEXT    NOT NULL,
                    final_reply      TEXT,
                    status           TEXT    NOT NULL DEFAULT 'pending',
                    created_at       TEXT    NOT NULL,
                    updated_at       TEXT    NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (3)")

        if current < 4:
            existing = {r[1] for r in conn.execute("PRAGMA table_info(clients)").fetchall()}
            if "pending_automation_type" not in existing:
                conn.execute("ALTER TABLE clients ADD COLUMN pending_automation_type TEXT")
            conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (4)")

    def save_pending_approval(
        self,
        event_id: str,
        agent_name: str,
        action: str,
        payload: dict[str, Any],
        decision: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pending_approvals
                (event_id, agent_name, action, payload_json, decision_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    agent_name,
                    action,
                    json.dumps(payload),
                    json.dumps(decision),
                    _utc_now(),
                ),
            )

    def delete_pending_approval(self, event_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM pending_approvals WHERE event_id = ?", (event_id,))

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pending_approvals ORDER BY created_at DESC"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "event_id": row["event_id"],
                    "agent_name": row["agent_name"],
                    "action": row["action"],
                    "payload": json.loads(row["payload_json"]),
                    "decision": json.loads(row["decision_json"]),
                }
            )
        return result

    def load_pending_approval(self, event_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pending_approvals WHERE event_id = ?", (event_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "event_id": row["event_id"],
            "agent_name": row["agent_name"],
            "action": row["action"],
            "payload": json.loads(row["payload_json"]),
            "decision": json.loads(row["decision_json"]),
        }

    def next_invoice_number(self) -> str:
        settings = load_integration_settings()
        year = datetime.now(timezone.utc).year
        series = settings.company.invoice_series
        conn = self._connect()
        try:
            conn.execute("BEGIN EXCLUSIVE")
            row = conn.execute(
                "SELECT last_number FROM invoice_sequence WHERE year = ?", (year,)
            ).fetchone()
            if row is None:
                last_number = 1
                conn.execute(
                    "INSERT INTO invoice_sequence (year, last_number) VALUES (?, ?)",
                    (year, last_number),
                )
            else:
                last_number = int(row["last_number"]) + 1
                conn.execute(
                    "UPDATE invoice_sequence SET last_number = ? WHERE year = ?",
                    (last_number, year),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return f"{series}-{year}-{last_number:04d}"

    def save_invoice(
        self,
        invoice_id: str,
        event_id: str,
        client_name: str | None,
        amount_eur: float | None,
        status: str,
        approved_by: str | None = None,
        invoice_number: str | None = None,
        pdf_path: str | None = None,
        client_email: str | None = None,
        client_nif: str | None = None,
        base_amount_eur: float | None = None,
        vat_rate: float | None = None,
        vat_amount_eur: float | None = None,
        total_eur: float | None = None,
        email_sent_at: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO invoices
                (invoice_id, event_id, client_name, amount_eur, status, approved_by, created_at,
                 invoice_number, pdf_path, client_email, client_nif, base_amount_eur, vat_rate,
                 vat_amount_eur, total_eur, email_sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    event_id,
                    client_name,
                    amount_eur,
                    status,
                    approved_by,
                    _utc_now(),
                    invoice_number,
                    pdf_path,
                    client_email,
                    client_nif,
                    base_amount_eur,
                    vat_rate,
                    vat_amount_eur,
                    total_eur,
                    email_sent_at,
                ),
            )

    def get_invoice(self, invoice_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM invoices WHERE invoice_id = ?", (invoice_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_invoice_status(self, invoice_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE invoices SET status = ? WHERE invoice_id = ?",
                (status, invoice_id),
            )

    def mark_invoice_email_sent(self, invoice_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE invoices SET email_sent_at = ? WHERE invoice_id = ?",
                (_utc_now(), invoice_id),
            )

    def list_invoices(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM invoices ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def is_email_processed(self, uid: str, folder: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_emails WHERE uid = ? AND folder = ?",
                (uid, folder),
            ).fetchone()
        return row is not None

    def mark_email_processed(self, uid: str, folder: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_emails (uid, folder, processed_at)
                VALUES (?, ?, ?)
                """,
                (uid, folder, _utc_now()),
            )

    def log_trigger(
        self,
        signal_id: str,
        trigger_type: str,
        activated: bool,
        agent_name: str | None,
        reason: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trigger_log (signal_id, trigger_type, activated, agent_name, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (signal_id, trigger_type, 1 if activated else 0, agent_name, reason, _utc_now()),
            )

    def list_recent_triggers(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trigger_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_client_memory(self, client_name: str, notes: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO client_memory (client_name, notes, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(client_name) DO UPDATE SET
                    notes=excluded.notes,
                    updated_at=excluded.updated_at
                """,
                (client_name, notes, _utc_now()),
            )

    def get_client_memory(self, client_name: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT notes FROM client_memory WHERE client_name = ?",
                (client_name,),
            ).fetchone()
        if row is None:
            return None
        return row["notes"]

    def save_ledger_entry(
        self,
        event_id: str,
        client_name: str | None,
        amount_eur: float | None,
        category: str,
        reference: str | None,
        status: str,
    ) -> str:
        entry_id = f"LED-{event_id[:8].upper()}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ledger_entries
                (entry_id, event_id, client_name, amount_eur, category, reference, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    event_id,
                    client_name,
                    amount_eur,
                    category,
                    reference,
                    status,
                    _utc_now(),
                ),
            )
        return entry_id

    def save_compliance_check(
        self,
        event_id: str,
        check_type: str,
        outcome: str,
        details: str = "",
    ) -> str:
        check_id = f"CMP-{event_id[:8].upper()}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO compliance_checks
                (check_id, event_id, check_type, outcome, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (check_id, event_id, check_type, outcome, details, _utc_now()),
            )
        return check_id

    def list_ledger_entries(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ledger_entries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def purge_pii_older_than(self, days: int) -> dict[str, int | str]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE invoices SET client_nif = NULL, client_email = NULL WHERE created_at < ?",
                (cutoff,),
            )
            purged = result.rowcount
        return {"purged_invoices": purged, "cutoff": cutoff}

    def log_event(
        self,
        event_id: str,
        agent_name: str,
        action: str,
        status: str,
        source: str | None,
        payload: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO event_log
                (event_id, agent_name, action, status, source, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    agent_name,
                    action,
                    status,
                    source,
                    json.dumps(payload),
                    _utc_now(),
                ),
            )

    # ---- Users ----

    def ensure_default_admin(self) -> None:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count == 0:
                user_id = f"USR-{secrets.token_hex(4).upper()}"
                conn.execute(
                    "INSERT INTO users (user_id, username, email, password_hash, role, created_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (user_id, "admin", "", _hash_password("admin123"), "admin", _utc_now()),
                )
                print("[ZeroManual] Default admin created — username: admin / password: admin123 — CHANGE THIS NOW")  # noqa: T201

    def ensure_default_client(self) -> None:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            if count == 0:
                self.create_client("Empresa de prueba", "test@empresa.com", "test123")
                print("[ZeroManual] Cliente de prueba creado — email: test@empresa.com / password: test123 — CAMBIA ESTO")  # noqa: T201

    def create_user(self, username: str, email: str, password: str, role: str = "admin") -> dict[str, Any]:
        user_id = f"USR-{secrets.token_hex(4).upper()}"
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO users (user_id, username, email, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
                    (user_id, username, email, _hash_password(password), role, _utc_now()),
                )
            except sqlite3.IntegrityError:
                raise ValueError(f"Username '{username}' already exists")
        return {"user_id": user_id, "username": username, "email": email, "role": role}

    def authenticate_user(self, username: str, password: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, email, role, password_hash FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None or not _verify_password(password, row["password_hash"]):
            return None
        return {"user_id": row["user_id"], "username": row["username"], "email": row["email"], "role": row["role"]}

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, email, role FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, username, email, role, created_at FROM users ORDER BY created_at ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_user(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    # ---- Sessions ----

    def create_session(self, user_id: str, ttl_hours: int = 24) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?,?,?,?)",
                (token, user_id, expires_at, _utc_now()),
            )
        return token

    def get_session_user(self, token: str) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT u.user_id, u.username, u.email, u.role
                   FROM sessions s JOIN users u ON s.user_id = u.user_id
                   WHERE s.token = ? AND s.expires_at > ?""",
                (token, now),
            ).fetchone()
        return dict(row) if row else None

    def delete_session(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    # ---- Clients ----

    def create_client(
        self, name: str, email: str, password: str, plan: str = "starter"
    ) -> dict[str, Any]:
        client_id = f"CLI-{secrets.token_hex(4).upper()}"
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO clients (client_id, name, email, password_hash, plan, created_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (client_id, name, email, _hash_password(password), plan, _utc_now()),
                )
            except sqlite3.IntegrityError:
                raise ValueError(f"Email '{email}' already registered")
        return {"client_id": client_id, "name": name, "email": email, "plan": plan}

    def authenticate_client(self, email: str, password: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT client_id, name, email, plan, password_hash FROM clients WHERE email = ?",
                (email,),
            ).fetchone()
        if row is None or not _verify_password(password, row["password_hash"]):
            return None
        return {"client_id": row["client_id"], "name": row["name"], "email": row["email"], "plan": row["plan"]}

    def get_client_by_id(self, client_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT client_id, name, email, plan FROM clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_clients(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT client_id, name, email, plan, created_at FROM clients ORDER BY created_at ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_client(self, client_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM client_sessions WHERE client_id = ?", (client_id,))
            conn.execute("DELETE FROM clients WHERE client_id = ?", (client_id,))

    def set_pending_automation(self, client_id: str, automation_type: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE clients SET pending_automation_type=? WHERE client_id=?",
                (automation_type, client_id),
            )

    def get_pending_automation(self, client_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT pending_automation_type FROM clients WHERE client_id=?",
                (client_id,),
            ).fetchone()
        return row["pending_automation_type"] if row else None

    def clear_pending_automation(self, client_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE clients SET pending_automation_type=NULL WHERE client_id=?",
                (client_id,),
            )

    # ---- Client Sessions ----

    def create_client_session(self, client_id: str, ttl_hours: int = 24) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO client_sessions (token, client_id, expires_at, created_at) VALUES (?,?,?,?)",
                (token, client_id, expires_at, _utc_now()),
            )
        return token

    def get_client_session(self, token: str) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT c.client_id, c.name, c.email, c.plan
                   FROM client_sessions s JOIN clients c ON s.client_id = c.client_id
                   WHERE s.token = ? AND s.expires_at > ?""",
                (token, now),
            ).fetchone()
        return dict(row) if row else None

    def delete_client_session(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM client_sessions WHERE token = ?", (token,))

    # ---- Google Credentials ----

    def save_google_creds(
        self,
        client_id: str,
        refresh_token: str,
        access_token: str | None,
        token_expiry: str | None,
        google_email: str | None,
        location_id: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO client_google_creds
                   (client_id, refresh_token, access_token, token_expiry, google_email, location_id, connected_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (client_id, refresh_token, access_token, token_expiry, google_email, location_id, _utc_now()),
            )

    def get_google_creds(self, client_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM client_google_creds WHERE client_id = ?",
                (client_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_google_creds(self, client_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM client_google_creds WHERE client_id = ?", (client_id,))

    # ---- Client Automations ----

    def activate_automation(
        self, client_id: str, automation_type: str, n8n_workflow_id: str
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO client_automations
                   (client_id, automation_type, n8n_workflow_id, status, activated_at)
                   VALUES (?,?,?,'active',?)""",
                (client_id, automation_type, n8n_workflow_id, now),
            )
        return {
            "client_id": client_id,
            "automation_type": automation_type,
            "n8n_workflow_id": n8n_workflow_id,
            "status": "active",
            "activated_at": now,
        }

    def deactivate_automation(self, client_id: str, automation_type: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE client_automations SET status='inactive', n8n_workflow_id=NULL"
                " WHERE client_id=? AND automation_type=?",
                (client_id, automation_type),
            )

    def get_automation(self, client_id: str, automation_type: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM client_automations WHERE client_id=? AND automation_type=?",
                (client_id, automation_type),
            ).fetchone()
        return dict(row) if row else None

    def list_client_automations(self, client_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM client_automations WHERE client_id=? ORDER BY automation_type ASC",
                (client_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ---- Automation Drafts (AI-suggested replies) ----

    def create_draft(
        self,
        client_id: str,
        automation_type: str,
        suggested_reply: str,
        review_id: str | None = None,
        reviewer_name: str | None = None,
        rating: str | None = None,
        source_text: str | None = None,
    ) -> dict[str, Any]:
        draft_id = f"DRF-{secrets.token_hex(6).upper()}"
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO automation_drafts
                   (draft_id, client_id, automation_type, review_id, reviewer_name, rating,
                    source_text, suggested_reply, final_reply, status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,NULL,'pending',?,?)""",
                (
                    draft_id, client_id, automation_type, review_id, reviewer_name, rating,
                    source_text, suggested_reply, now, now,
                ),
            )
        return self.get_draft(draft_id)  # type: ignore[return-value]

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM automation_drafts WHERE draft_id = ?", (draft_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_drafts(
        self, client_id: str, automation_type: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM automation_drafts WHERE client_id = ?"
        params: list[Any] = [client_id]
        if automation_type is not None:
            query += " AND automation_type = ?"
            params.append(automation_type)
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def resolve_draft(self, draft_id: str, status: str, final_reply: str | None) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE automation_drafts SET status = ?, final_reply = ?, updated_at = ? WHERE draft_id = ?",
                (status, final_reply, _utc_now(), draft_id),
            )
        return self.get_draft(draft_id)
