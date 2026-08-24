"""
Thin client for the custom NorthPeak Order DB MCP server.

Each call creates a short-lived MCP stdio session.

The MCP server is launched as a Python module from the backend
directory. This ensures imports such as `from app.config import
settings` work correctly inside the child process.
"""

import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


_BACKEND_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
    )
)


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "mcp_servers.order_db_server",
        ],
        cwd=_BACKEND_ROOT,
        env={
            **os.environ,
            "PYTHONPATH": _BACKEND_ROOT,
        },
    )


async def get_order(order_id: str) -> dict:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "get_order",
                {"order_id": order_id},
            )

            text = result.content[0].text

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw_result": text}


async def get_customer_orders(
    customer_id: str,
) -> list[dict]:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "get_customer_orders",
                {"customer_id": customer_id},
            )

            text = result.content[0].text

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return [{"raw_result": text}]


async def update_order_status(
    order_id: str,
    new_status: str,
) -> dict:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "update_order_status",
                {
                    "order_id": order_id,
                    "new_status": new_status,
                },
            )

            text = result.content[0].text

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw_result": text}