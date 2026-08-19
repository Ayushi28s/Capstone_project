"""
Thin async client over the custom Order DB MCP server. Each call spins
up the server as a stdio subprocess, opens an MCP session, calls one
tool, and tears down — simple over fast, which is the right trade for a
teaching capstone.

Always launches via sys.executable — the exact interpreter running this
process, guaranteed to have the `mcp` package installed — on every
platform including Windows. An earlier version of this file routed the
Windows branch through `cmd /c python ...` instead, which relies on
PATH resolution finding the venv's python.exe first inside the
subprocess; on a machine with any other Python on PATH (a system
install, Anaconda, etc.) that launches the wrong interpreter — one
without `mcp` installed — and the server fails to start, which surfaces
as every order lookup silently failing. `cmd /c` wrapping is only
needed for launching .cmd shims like npx; sys.executable is already a
real, absolute, directly-executable path and needs no such wrapping on
any platform.
"""
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "mcp_servers", "order_db_server.py")


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=[_SERVER_SCRIPT])


async def get_order(order_id: str) -> dict:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_order", {"order_id": order_id})
            return json.loads(result.content[0].text)


async def get_customer_orders(customer_id: str) -> list[dict]:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_customer_orders", {"customer_id": customer_id})
            return json.loads(result.content[0].text)


async def update_order_status(order_id: str, new_status: str) -> dict:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "update_order_status", {"order_id": order_id, "new_status": new_status}
            )
            return json.loads(result.content[0].text)
