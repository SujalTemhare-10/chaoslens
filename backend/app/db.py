"""Tiny SQLite store for experiment results."""
from __future__ import annotations

import json
import os
import sqlite3
import threading

DB_PATH = os.environ.get("CHAOSLENS_DB", os.path.join(os.path.dirname(__file__), "..", "chaoslens.db"))
_lock = threading.Lock()


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _lock, _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY,
                project TEXT,
                campaign_id TEXT,
                fault_type TEXT,
                faults TEXT,
                predicted_down TEXT,
                observed_down TEXT,
                matched INTEGER,
                duration_s REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""")


def save(exp: dict) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO experiments (id, project, campaign_id, fault_type, faults, predicted_down,"
            " observed_down, matched, duration_s) VALUES (?,?,?,?,?,?,?,?,?)",
            (exp["id"], exp["project"], exp.get("campaign_id"), exp["fault_type"], json.dumps(exp["faults"]),
             json.dumps(exp["predicted_down"]), json.dumps(exp["observed_down"]),
             int(exp["matched"]), exp["duration_s"]))


def history(project: str | None = None, limit: int = 200) -> list[dict]:
    q = "SELECT * FROM experiments"
    args: tuple = ()
    if project:
        q += " WHERE project = ?"
        args = (project,)
    q += " ORDER BY created_at DESC LIMIT ?"
    with _lock, _conn() as conn:
        rows = conn.execute(q, args + (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("faults", "predicted_down", "observed_down"):
            d[k] = json.loads(d[k])
        d["matched"] = bool(d["matched"])
        out.append(d)
    return out
