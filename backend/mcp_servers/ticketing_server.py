"""
Custom Ticketing MCP server for CommerceOps AI.

Exposes ticket creation and lookup — used by the Support Triage Crew to
log every interaction it handles, and by the billing-dispute agent
specifically to escalate disputes it can't resolve automatically.

Run standalone for debugging with the MCP Inspector:
    npx @modelcontextprotocol/inspector python mcp_servers/ticketing_server.py
"""
import sqlite3
import uuid
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from app.config import settings

mcp = FastMCP("commerceops-ticketing")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.MCP_SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@mcp.tool()
def create_ticket(customer_id: str, category: str, subject: str, order_id: str = "") -> dict:
    """Create a new support ticket. category must be one of:
    order_status, refund_request, billing_dispute, policy_question."""
    allowed_categories = {"order_status", "refund_request", "billing_dispute", "policy_question"}
    if category not in allowed_categories:
        return {"error": f"'{category}' is not a valid category. Allowed: {sorted(allowed_categories)}"}

    ticket_id = f"TCK-{uuid.uuid4().hex[:8].upper()}"
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO tickets (ticket_id, customer_id, order_id, category, subject, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?)",
            (ticket_id, customer_id, order_id or None, category, subject, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return {"ticket_id": ticket_id, "status": "open"}
    finally:
        conn.close()


@mcp.tool()
def get_ticket(ticket_id: str) -> dict:
    """Look up a single ticket by ID."""
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"error": f"No ticket found with ID {ticket_id}"}
        return dict(row)
    finally:
        conn.close()


@mcp.tool()
def escalate_ticket(ticket_id: str, reason: str) -> dict:
    """Mark a ticket as escalated — used when a billing dispute or
    refund needs human review beyond what the agent can resolve."""
    conn = _connect()
    try:
        cur = conn.execute("UPDATE tickets SET status = 'escalated' WHERE ticket_id = ?", (ticket_id,))
        conn.commit()
        if cur.rowcount == 0:
            return {"error": f"No ticket found with ID {ticket_id}"}
        return {"ticket_id": ticket_id, "status": "escalated", "reason": reason}
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
