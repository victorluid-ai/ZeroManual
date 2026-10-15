"""Dry-run and apply for the two duplicate Google location rows."""

from __future__ import annotations

import importlib.util
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CDV = "1d0ZyxxIU3cPSlXg"
DUP_A = "ePhhOcDT7ew5q74A"
DUP_B = "74hUH1G0aTgGBrZT"
KEEP = "wf-other-active"


def _load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "fix_duplicate_gbp_locations.py"
    spec = importlib.util.spec_from_file_location("fix_duplicate_gbp_locations", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE client_automations (
            id INTEGER PRIMARY KEY,
            client_id TEXT NOT NULL,
            business_id TEXT NOT NULL,
            automation_type TEXT NOT NULL,
            n8n_workflow_id TEXT,
            status TEXT NOT NULL,
            location_id TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO client_automations
            (id, client_id, business_id, automation_type, n8n_workflow_id, status, location_id)
        VALUES (?, ?, ?, 'google_reviews', ?, ?, ?)
        """,
        [
            (3, "CLI-A60A38F5", "BIZ-CDV", CDV, "active", "accounts/1/locations/1"),
            (4, "CLI-4CCD64B7", "BIZ-A", DUP_A, "active", "accounts/1/locations/1"),
            (5, "CLI-3D0DCD67", "BIZ-B", DUP_B, "paused", "accounts/1/locations/1"),
            (6, "CLI-OTHER", "BIZ-OTHER", KEEP, "active", "accounts/9/locations/9"),
        ],
    )
    conn.commit()
    conn.close()


def _statuses(db_path: Path) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT n8n_workflow_id, status FROM client_automations ORDER BY id"
    ).fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def _count(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    total = conn.execute("SELECT COUNT(*) FROM client_automations").fetchone()[0]
    conn.close()
    return int(total)


def test_dry_run_prints_plan_and_does_not_write(tmp_path: Path, capsys) -> None:
    module = _load()
    db_path = tmp_path / "zeromanual.db"
    _seed(db_path)
    before = _statuses(db_path)
    code = module.main(["--db", str(db_path)])
    captured = capsys.readouterr()
    assert code == 0
    assert _statuses(db_path) == before
    assert _count(db_path) == 4
    assert list(tmp_path.glob("*.bak-*")) == []
    assert "Dry-run" in captured.out
    assert DUP_A in captured.out
    assert DUP_B in captured.out
    assert "status active -> inactive" in captured.out
    assert "status paused -> inactive" in captured.out
    assert "SET status='active'" in captured.out
    assert "SET status='paused'" in captured.out
    assert CDV not in captured.out


def test_apply_changes_only_duplicate_rows_and_second_run_is_noop(
    tmp_path: Path, capsys
) -> None:
    module = _load()
    db_path = tmp_path / "zeromanual.db"
    _seed(db_path)
    when = datetime(2026, 10, 15, 13, 5, tzinfo=ZoneInfo("Europe/Madrid"))
    code = module.run(db_path, apply=True, when=when)
    first_out = capsys.readouterr().out
    assert code == 0
    statuses = _statuses(db_path)
    assert statuses[CDV] == "active"
    assert statuses[KEEP] == "active"
    assert statuses[DUP_A] == "inactive"
    assert statuses[DUP_B] == "inactive"
    assert _count(db_path) == 4
    backups = list(tmp_path.glob("zeromanual.db.bak-*"))
    assert len(backups) == 1
    assert backups[0].name == "zeromanual.db.bak-20261015-130500"
    assert "Copia:" in first_out
    assert "SET status='active'" in first_out
    assert "SET status='paused'" in first_out
    backup_statuses = _statuses(backups[0])
    assert backup_statuses[DUP_A] == "active"
    assert backup_statuses[DUP_B] == "paused"
    assert backup_statuses[CDV] == "active"

    again = module.run(db_path, apply=True, when=when)
    second_out = capsys.readouterr().out
    assert again == 0
    assert _statuses(db_path) == statuses
    assert list(tmp_path.glob("zeromanual.db.bak-*")) == backups
    assert "Nada que cambiar" in second_out


def test_script_does_not_call_n8n_or_stripe() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "fix_duplicate_gbp_locations.py"
    text = path.read_text(encoding="utf-8")
    assert "import httpx" not in text
    assert "import stripe" not in text
    assert "stripe." not in text
    assert "urllib" not in text
    assert "requests" not in text
    assert "DELETE FROM" not in text
    assert "inactive" in text
