import json
import os
import sys

from mcp import StdioServerParameters

from app.config import settings
from app.mcp_tools._persistent_session import PersistentMCPConnection

_connection: PersistentMCPConnection | None = None


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


def _get_connection() -> PersistentMCPConnection:
    global _connection
    if _connection is None:
        params = StdioServerParameters(
            command=_console_script_path(), args=["--db-path", settings.MCP_SQLITE_DB_PATH]
        )
        _connection = PersistentMCPConnection(params)
    return _connection


async def read_query(sql: str) -> list[dict]:
    """Run a SELECT-only query against the full database, including
    internal cost/margin fields. Only ever intended for an internal
    agent, never a customer-facing one."""
    text = await _get_connection().call_tool("read_query", {"query": sql})
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return [{"raw_result": text}]


async def list_tables() -> list[str]:
    text = await _get_connection().call_tool("list_tables", {})
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return []
