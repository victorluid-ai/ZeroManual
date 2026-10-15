"""Mark two duplicate Google review rows inactive. Does not delete rows.

Those workflows are already off in n8n. This only updates SQLite so the
partial unique index can be created the next time the API starts.

Default is dry-run. ``--apply`` copies the database, then sets ``status`` to
``inactive`` (the value ``DataStore.deactivate_automation`` uses). That status
is outside ``idx_client_automations_gbp_location_live``, which covers only
``active`` and ``paused``.

Does not call n8n or Stripe and does not print secrets.

    python scripts/fix_duplicate_gbp_locations.py
    python scripts/fix_duplicate_gbp_locations.py --apply
    python scripts/fix_duplicate_gbp_locations.py --db runtime/zeromanual.db --apply
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Same literal as apps.orchestrator.store.DataStore.deactivate_automation.
DEACTIVATED_STATUS = "inactive"
LIVE_STATUSES = ("active", "paused")
DUPLICATE_WORKFLOW_IDS = ("ePhhOcDT7ew5q74A", "74hUH1G0aTgGBrZT")
DEFAULT_DB = Path("runtime/zeromanual.db")
_MADRID = ZoneInfo("Europe/Madrid")


def backup_path(db_path: Path, when: datetime | None = None) -> Path:
    """``runtime/zeromanual.db`` becomes ``runtime/zeromanual.db.bak-<fecha>``."""
    moment = when or datetime.now(_MADRID)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_MADRID)
    fecha = moment.astimezone(_MADRID).strftime("%Y%m%d-%H%M%S")
    dest = db_path.with_name(f"{db_path.name}.bak-{fecha}")
    suffix = 2
    while dest.exists():
        dest = db_path.with_name(f"{db_path.name}.bak-{fecha}-{suffix}")
        suffix += 1
    return dest


def rows_to_fix(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    marks = ",".join("?" * len(DUPLICATE_WORKFLOW_IDS))
    status_marks = ",".join("?" * len(LIVE_STATUSES))
    return list(
        conn.execute(
            f"""
            SELECT id, client_id, business_id, automation_type, n8n_workflow_id, status
            FROM client_automations
            WHERE n8n_workflow_id IN ({marks})
              AND status IN ({status_marks})
            ORDER BY id
            """,
            (*DUPLICATE_WORKFLOW_IDS, *LIVE_STATUSES),
        )
    )


def describe_change(row: sqlite3.Row) -> str:
    return (
        f"id={row['id']} client_id={row['client_id']} "
        f"business_id={row['business_id']} "
        f"n8n_workflow_id={row['n8n_workflow_id']} "
        f"status {row['status']} -> {DEACTIVATED_STATUS}"
    )


def rollback_statements(rows: list[sqlite3.Row]) -> str:
    lines = []
    for row in rows:
        lines.append(
            "UPDATE client_automations "
            f"SET status='{row['status']}' "
            f"WHERE id={int(row['id'])} "
            f"AND n8n_workflow_id='{row['n8n_workflow_id']}';"
        )
    return "\n".join(lines)


def copy_database(src: Path, dest: Path) -> None:
    """Consistent SQLite snapshot, including a database that is in WAL mode."""
    source = sqlite3.connect(src)
    try:
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def run(db_path: Path, *, apply: bool, when: datetime | None = None) -> int:
    if not db_path.is_file():
        print(f"No existe la base: {db_path}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = rows_to_fix(conn)
        if not rows:
            print("Nada que cambiar. Esas filas no están active ni paused.")
            return 0
        for row in rows:
            print(describe_change(row))
        if not apply:
            print("Dry-run: no se ha escrito nada. Repite con --apply para aplicar.")
            print("Valores previos, por si hay que volver atrás:")
            print(rollback_statements(rows))
            return 0
        dest = backup_path(db_path, when)
        copy_database(db_path, dest)
        print(f"Copia: {dest}")
        conn.execute("BEGIN")
        for row in rows:
            cur = conn.execute(
                """
                UPDATE client_automations
                SET status = ?
                WHERE id = ? AND n8n_workflow_id = ? AND status IN ('active', 'paused')
                """,
                (DEACTIVATED_STATUS, row["id"], row["n8n_workflow_id"]),
            )
            if cur.rowcount != 1:
                conn.rollback()
                print("No se escribió: la fila ya no estaba active o paused.", file=sys.stderr)
                return 1
        conn.commit()
    finally:
        conn.close()
    print("Rollback: restaurar la copia")
    print(f"  cp {dest} {db_path}")
    print("o volver a poner el status anterior:")
    print(rollback_statements(rows))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pasa a inactive las filas duplicadas de google_reviews, sin borrarlas."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Escribe. Sin esta opción solo muestra el cambio.",
    )
    args = parser.parse_args(argv)
    return run(args.db, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
