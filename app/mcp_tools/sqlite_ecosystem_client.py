"""
Client wrapper for the ECOSYSTEM SQLite MCP server — the real,
pre-built `mcp-server-sqlite` package (pip install mcp-server-sqlite),
not a custom reimplementation. This is the second of the two "ecosystem
server" integrations the curriculum asks for (the first is the GitHub
MCP server in github_client.py).

Unlike the custom Order DB / Catalog servers, this server has NO
built-in field-level scoping — read_query runs any SELECT statement
against the whole database, including products.wholesale_cost_usd.
That's fine here specifically because this client is wired into exactly
one place in the whole system: the Merchandising Analytics Agent
(app/agents/merchandising_agent.py), which is an internal-only agent
never exposed to customer-facing flows. See the Solution Guide's
Guardrails phase for the full read-only-vs-read-write and
customer-facing-vs-internal scoping rationale.

Launch the real server standalone for debugging:
    mcp-server-sqlite --db-path ./data/commerceops.db
"""
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import settings


def _console_script_path() -> str:
    """Resolves mcp-server-sqlite's real path inside THIS interpreter's
    venv, rather than trusting bare-name PATH resolution inside a
    subprocess. pip installs console-script entry points into the same
    directory as the interpreter itself (venv/Scripts on Windows,
    venv/bin elsewhere), so sys.executable's directory always has it —
    no dependency on which venv (if any) happens to be first on PATH
    inside a freshly spawned subprocess."""
    script_dir = os.path.dirname(sys.executable)
    name = "mcp-server-sqlite.exe" if sys.platform.startswith("win") else "mcp-server-sqlite"
    full_path = os.path.join(script_dir, name)
    return full_path if os.path.exists(full_path) else "mcp-server-sqlite"  # fall back to PATH lookup


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=_console_script_path(), args=["--db-path", settings.MCP_SQLITE_DB_PATH]
    )


async def read_query(sql: str) -> list[dict]:
    """Run a SELECT-only query against the full database, including
    internal cost/margin fields. Only ever called from the internal
    Merchandising Analytics Agent."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("read_query", {"query": sql})
            text = result.content[0].text
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return [{"raw_result": text}]


async def list_tables() -> list[str]:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("list_tables", {})
            try:
                return json.loads(result.content[0].text)
            except json.JSONDecodeError:
                return []
