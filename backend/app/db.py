"""
SQLite persistence for CommerceOps AI.

Deliberately not an ORM — the project already leans on ChromaDB, a
NetworkX knowledge graph, and Redis, so the operational data stays plain
SQL and inspectable. This same commerceops.db file is also what the
custom Order DB / Catalog MCP servers and the SQLite ecosystem MCP
server expose to agents (each scoped to different tables — see
mcp_servers/), and what the Merchandising Analytics Agent's SQL tool
queries directly.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    signup_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price_usd REAL NOT NULL,
    wholesale_cost_usd REAL NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    status TEXT NOT NULL,          -- placed | shipped | delivered | returned
    carrier TEXT,
    estimated_delivery TEXT,
    total_amount_usd REAL NOT NULL,
    fulfillment_center TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (sku) REFERENCES products(sku)
);

CREATE TABLE IF NOT EXISTS sales (
    sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL,
    sale_date TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    revenue_usd REAL NOT NULL,
    fulfillment_center TEXT NOT NULL,
    FOREIGN KEY (sku) REFERENCES products(sku)
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_id TEXT,
    category TEXT NOT NULL,        -- order_status | refund_request | billing_dispute | policy_question
    subject TEXT NOT NULL,
    status TEXT NOT NULL,          -- open | resolved | escalated
    created_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE IF NOT EXISTS refund_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    requested_at TEXT NOT NULL,
    approved INTEGER,              -- NULL until decided
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE IF NOT EXISTS chat_jobs (
    session_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'queued',
    current_node TEXT,
    progress_pct INTEGER DEFAULT 0,
    error TEXT,
    last_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    approved INTEGER NOT NULL,
    reviewer TEXT NOT NULL,
    comments TEXT,
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guardrail_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    rail_type TEXT NOT NULL,          -- input_rail | pii_redaction | cost_data_redaction | output_guard | mcp_scope
    action TEXT NOT NULL,             -- blocked | redacted | flagged | passed
    detail TEXT,
    occurred_at TEXT NOT NULL
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(settings.SQLITE_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# --- jobs ---
def create_job(session_id: str, last_message: str) -> None:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO chat_jobs (session_id, status, last_message, created_at, updated_at) "
            "VALUES (?, 'queued', ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET status='queued', last_message=excluded.last_message, "
            "updated_at=excluded.updated_at",
            (session_id, last_message, now, now),
        )


def update_job(session_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE chat_jobs SET {cols} WHERE session_id = ?", (*fields.values(), session_id))


def get_job(session_id: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM chat_jobs WHERE session_id = ?", (session_id,)).fetchone()


def list_jobs(limit: int = 50) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM chat_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()


# --- approvals ---
def record_approval(session_id: str, approved: bool, reviewer: str, comments: Optional[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO approvals (session_id, approved, reviewer, comments, decided_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, int(approved), reviewer, comments, datetime.utcnow().isoformat()),
        )


# --- guardrail audit log ---
def log_guardrail_event(session_id: Optional[str], rail_type: str, action: str, detail: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO guardrail_events (session_id, rail_type, action, detail, occurred_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, rail_type, action, detail, datetime.utcnow().isoformat()),
        )
    if action in ("blocked", "flagged"):
        _notify_n8n_guardrail_alert(session_id, rail_type, action, detail)


def _notify_n8n_guardrail_alert(session_id, rail_type: str, action: str, detail: str) -> None:
    """Fires the n8n Guardrail Alert Flow (see n8n/guardrail_alert_flow.json)
    for anything blocked or flagged — a Slack/webhook notification separate
    from, and in addition to, the SQLite audit row above. Fails silently:
    a down or unconfigured n8n instance must never take down the actual
    guardrail decision it's just reporting on."""
    from app.config import settings
    if not settings.N8N_GUARDRAIL_ALERT_WEBHOOK_URL:
        return
    try:
        import requests
        requests.post(
            settings.N8N_GUARDRAIL_ALERT_WEBHOOK_URL,
            json={
                "session_id": session_id, "rail_type": rail_type,
                "action": action, "detail": detail,
                "occurred_at": datetime.utcnow().isoformat(),
            },
            timeout=3,
        )
    except Exception:
        pass


def list_guardrail_events(limit: int = 100, session_id: Optional[str] = None) -> list[sqlite3.Row]:
    with get_conn() as conn:
        if session_id:
            return conn.execute(
                "SELECT * FROM guardrail_events WHERE session_id = ? ORDER BY occurred_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM guardrail_events ORDER BY occurred_at DESC LIMIT ?", (limit,)
        ).fetchall()


# --- refund anomaly detection (red-team prompt #7: rapid requests just under threshold) ---
def record_refund_request(order_id: str, customer_id: str, amount_usd: float) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO refund_requests (order_id, customer_id, amount_usd, requested_at) "
            "VALUES (?, ?, ?, ?)",
            (order_id, customer_id, amount_usd, datetime.utcnow().isoformat()),
        )


def recent_refund_request_count(customer_id: str, window_minutes: int = 60) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as n FROM refund_requests "
            "WHERE customer_id = ? AND requested_at >= datetime('now', ?)",
            (customer_id, f"-{window_minutes} minutes"),
        ).fetchone()
    return row["n"] if row else 0


# --- domain data lookups (used by MCP servers and agents) ---
def get_order(order_id: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()


def get_product(sku: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()


def get_customer_orders(customer_id: str) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE customer_id = ? ORDER BY order_date DESC", (customer_id,)
        ).fetchall()
