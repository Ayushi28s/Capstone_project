"""
Thin async client over the custom Ticketing MCP server. Always launches
via sys.executable on every platform — see order_db_client.py's module
docstring for why the Windows branch was fixed to do the same rather
than routing through `cmd /c python ...`.
"""
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "mcp_servers", "ticketing_server.py")


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=[_SERVER_SCRIPT])


async def create_ticket(customer_id: str, category: str, subject: str, order_id: str = "") -> dict:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "create_ticket",
                {"customer_id": customer_id, "category": category, "subject": subject, "order_id": order_id},
            )
            return json.loads(result.content[0].text)


async def escalate_ticket(ticket_id: str, reason: str) -> dict:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("escalate_ticket", {"ticket_id": ticket_id, "reason": reason})
            return json.loads(result.content[0].text)
