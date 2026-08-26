import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


_SERVER_SCRIPT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "mcp_servers",
        "catalog_server.py",
    )
)


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[_SERVER_SCRIPT],
    )


async def get_product(sku: str) -> dict:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "get_product",
                {"sku": sku},
            )

            text = result.content[0].text

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw_result": text}


async def search_products(
    category: str = "",
    name_contains: str = "",
) -> list[dict]:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "search_products",
                {
                    "category": category,
                    "name_contains": name_contains,
                },
            )

            text = result.content[0].text

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return [{"raw_result": text}]