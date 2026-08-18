"""
Custom Order DB MCP server for CommerceOps AI.

Exposes exactly three read-only tools against the orders/customers
tables. This is what the order-status and refund/billing agents in the
Support Triage Crew call — nothing else in the system is wired to this
server, so "give this agent write access to orders" isn't even a
question that comes up.

Run standalone for debugging with the MCP Inspector:
    npx @modelcontextprotocol/inspector python mcp_servers/order_db_server.py
"""
import sqlite3

from mcp.server.fastmcp import FastMCP

from app.config import settings

mcp = FastMCP("commerceops-order-db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.MCP_SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@mcp.tool()
def get_order(order_id: str) -> dict:
    """Look up a single order by its order ID. Returns status, carrier,
    estimated delivery, and total — never wholesale cost or any
    internal-cost field, since this server is customer-facing scope."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT order_id, customer_id, sku, quantity, order_date, status, "
            "carrier, estimated_delivery, total_amount_usd, fulfillment_center "
            "FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            return {"error": f"No order found with ID {order_id}"}
        return dict(row)
    finally:
        conn.close()


@mcp.tool()
def get_customer_orders(customer_id: str) -> list[dict]:
    """List all orders for a given customer ID, most recent first."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT order_id, sku, order_date, status, total_amount_usd "
            "FROM orders WHERE customer_id = ? ORDER BY order_date DESC",
            (customer_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@mcp.tool()
def update_order_status(order_id: str, new_status: str) -> dict:
    """Update an order's status (e.g. mark as 'returned' after a
    processed refund). Restricted to the specific status values a
    support agent can legitimately set — never exposes a way to modify
    price, customer, or SKU fields."""
    allowed_statuses = {"placed", "shipped", "delivered", "returned"}
    if new_status not in allowed_statuses:
        return {"error": f"'{new_status}' is not an allowed status. Allowed: {sorted(allowed_statuses)}"}
    conn = _connect()
    try:
        cur = conn.execute("UPDATE orders SET status = ? WHERE order_id = ?", (new_status, order_id))
        conn.commit()
        if cur.rowcount == 0:
            return {"error": f"No order found with ID {order_id}"}
        return {"order_id": order_id, "new_status": new_status, "updated": True}
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
