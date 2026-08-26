import sqlite3

from mcp.server.fastmcp import FastMCP

from app.config import settings

mcp = FastMCP("commerceops-catalog")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.MCP_SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Deliberately excludes wholesale_cost_usd — see module docstring.
_CUSTOMER_FACING_COLUMNS = "sku, name, category, price_usd, description"


@mcp.tool()
def get_product(sku: str) -> dict:
    """Look up a single product by SKU. Returns customer-facing fields
    only — name, category, price, description. Never returns wholesale
    cost, margin, or any internal financial field."""
    conn = _connect()
    try:
        row = conn.execute(
            f"SELECT {_CUSTOMER_FACING_COLUMNS} FROM products WHERE sku = ?", (sku,)
        ).fetchone()
        if row is None:
            return {"error": f"No product found with SKU {sku}"}
        return dict(row)
    finally:
        conn.close()


@mcp.tool()
def search_products(category: str = "", name_contains: str = "") -> list[dict]:
    """Search products by category and/or a name substring. Same
    customer-facing field scope as get_product."""
    conn = _connect()
    try:
        query = f"SELECT {_CUSTOMER_FACING_COLUMNS} FROM products WHERE 1=1"
        params = []
        if category:
            query += " AND lower(category) = lower(?)"
            params.append(category)
        if name_contains:
            query += " AND lower(name) LIKE lower(?)"
            params.append(f"%{name_contains}%")
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
