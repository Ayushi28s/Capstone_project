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
    status TEXT NOT NULL,
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
    category TEXT NOT NULL,
    subject TEXT NOT NULL,
    status TEXT NOT NULL,
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
    approved INTEGER,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE IF NOT EXISTS chat_jobs (
    session_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'queued',
    current_node TEXT,
    progress_pct INTEGER DEFAULT 0,
    error TEXT,
    last_message TEXT,
    employee_name TEXT,
    employee_role TEXT,
    customer_id TEXT,
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
    rail_type TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT,
    occurred_at TEXT NOT NULL
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(
        settings.SQLITE_DB_PATH,
        timeout=10,
    )

    conn.row_factory = sqlite3.Row

    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate_add_missing_columns(conn)


def _migrate_add_missing_columns(
    conn: sqlite3.Connection,
) -> None:
    """
    CREATE TABLE IF NOT EXISTS does not alter existing tables.

    Add newer chat_jobs columns safely when an older database
    already exists.
    """

    existing_cols = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(chat_jobs)"
        ).fetchall()
    }

    for col in (
        "employee_name",
        "employee_role",
        "customer_id",
    ):
        if col not in existing_cols:
            conn.execute(
                f"ALTER TABLE chat_jobs ADD COLUMN {col} TEXT"
            )


# -------------------------------------------------------------------
# Jobs
# -------------------------------------------------------------------

def create_job(
    session_id: str,
    last_message: str,
    employee_name: str = "",
    employee_role: str = "",
    customer_id: str = "",
) -> None:
    now = datetime.utcnow().isoformat()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO chat_jobs (
                session_id,
                status,
                last_message,
                employee_name,
                employee_role,
                customer_id,
                created_at,
                updated_at
            )
            VALUES (?, 'queued', ?, ?, ?, ?, ?, ?)

            ON CONFLICT(session_id)
            DO UPDATE SET
                status='queued',
                last_message=excluded.last_message,
                employee_name=excluded.employee_name,
                employee_role=excluded.employee_role,
                customer_id=excluded.customer_id,
                updated_at=excluded.updated_at
            """,
            (
                session_id,
                last_message,
                employee_name,
                employee_role,
                customer_id,
                now,
                now,
            ),
        )


def update_job(
    session_id: str,
    **fields,
) -> None:
    if not fields:
        return

    fields["updated_at"] = datetime.utcnow().isoformat()

    cols = ", ".join(
        f"{key} = ?"
        for key in fields
    )

    with get_conn() as conn:
        conn.execute(
            f"""
            UPDATE chat_jobs
            SET {cols}
            WHERE session_id = ?
            """,
            (
                *fields.values(),
                session_id,
            ),
        )


def get_job(
    session_id: str,
) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM chat_jobs
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()


def list_jobs(
    limit: int = 50,
) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM chat_jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


# -------------------------------------------------------------------
# Approvals
# -------------------------------------------------------------------

def record_approval(
    session_id: str,
    approved: bool,
    reviewer: str,
    comments: Optional[str],
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO approvals (
                session_id,
                approved,
                reviewer,
                comments,
                decided_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                int(approved),
                reviewer,
                comments,
                datetime.utcnow().isoformat(),
            ),
        )


# -------------------------------------------------------------------
# Guardrail audit log
# -------------------------------------------------------------------

def log_guardrail_event(
    session_id: Optional[str],
    rail_type: str,
    action: str,
    detail: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO guardrail_events (
                session_id,
                rail_type,
                action,
                detail,
                occurred_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                rail_type,
                action,
                detail,
                datetime.utcnow().isoformat(),
            ),
        )


def list_guardrail_events(
    limit: int = 100,
    session_id: Optional[str] = None,
) -> list[sqlite3.Row]:
    with get_conn() as conn:

        if session_id:
            return conn.execute(
                """
                SELECT *
                FROM guardrail_events
                WHERE session_id = ?
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                (
                    session_id,
                    limit,
                ),
            ).fetchall()

        return conn.execute(
            """
            SELECT *
            FROM guardrail_events
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


# -------------------------------------------------------------------
# Refund approval persistence and anomaly detection
# -------------------------------------------------------------------

def record_refund_request(
    order_id: str,
    customer_id: str,
    amount_usd: float,
) -> None:
    """
    Record a new refund request.

    A new row is created only when an identical approved refund does
    not already exist. This avoids creating unnecessary duplicate
    pending records for previously approved business requests.
    """

    existing = get_existing_approved_refund(
        order_id=order_id,
        customer_id=customer_id,
        amount_usd=amount_usd,
    )

    if existing:
        return

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO refund_requests (
                order_id,
                customer_id,
                amount_usd,
                requested_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                order_id,
                customer_id,
                amount_usd,
                datetime.utcnow().isoformat(),
            ),
        )


def get_existing_approved_refund(
    order_id: str,
    customer_id: str,
    amount_usd: float,
) -> Optional[sqlite3.Row]:
    """
    Return an existing approved refund matching the same
    order, customer, and amount.
    """

    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM refund_requests
            WHERE order_id = ?
              AND customer_id = ?
              AND ABS(amount_usd - ?) < 0.01
              AND approved = 1
            ORDER BY requested_at DESC
            LIMIT 1
            """,
            (
                order_id,
                customer_id,
                amount_usd,
            ),
        ).fetchone()


def get_existing_rejected_refund(
    order_id: str,
    customer_id: str,
    amount_usd: float,
) -> Optional[sqlite3.Row]:
    """
    Return the latest rejected matching refund, if present.
    """

    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM refund_requests
            WHERE order_id = ?
              AND customer_id = ?
              AND ABS(amount_usd - ?) < 0.01
              AND approved = 0
            ORDER BY requested_at DESC
            LIMIT 1
            """,
            (
                order_id,
                customer_id,
                amount_usd,
            ),
        ).fetchone()


def update_latest_refund_decision(
    order_id: str,
    customer_id: str,
    amount_usd: float,
    approved: bool,
) -> None:
    """
    Store the HITL decision against the newest matching pending refund.
    """

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM refund_requests
            WHERE order_id = ?
              AND customer_id = ?
              AND ABS(amount_usd - ?) < 0.01
              AND approved IS NULL
            ORDER BY requested_at DESC
            LIMIT 1
            """,
            (
                order_id,
                customer_id,
                amount_usd,
            ),
        ).fetchone()

        if not row:
            return

        conn.execute(
            """
            UPDATE refund_requests
            SET approved = ?
            WHERE id = ?
            """,
            (
                int(approved),
                row["id"],
            ),
        )


def recent_refund_request_count(
    customer_id: str,
    window_minutes: int = 60,
) -> int:
    """
    Count recent refund requests for anomaly detection.
    """

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM refund_requests
            WHERE customer_id = ?
              AND requested_at >= datetime('now', ?)
            """,
            (
                customer_id,
                f"-{window_minutes} minutes",
            ),
        ).fetchone()

    return row["n"] if row else 0


# -------------------------------------------------------------------
# Domain data lookups
# -------------------------------------------------------------------

def get_order(
    order_id: str,
) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM orders
            WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()


def get_product(
    sku: str,
) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM products
            WHERE sku = ?
            """,
            (sku,),
        ).fetchone()


def get_customer_orders(
    customer_id: str,
) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM orders
            WHERE customer_id = ?
            ORDER BY order_date DESC
            """,
            (customer_id,),
        ).fetchall()