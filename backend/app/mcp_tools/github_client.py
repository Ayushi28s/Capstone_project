import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import settings


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command="docker",
        args=[
            "run", "-i", "--rm",
            "-e", f"GITHUB_PERSONAL_ACCESS_TOKEN={settings.GITHUB_TOKEN}",
            "ghcr.io/github/github-mcp-server",
            "--read-only",
        ],
    )


async def get_file_contents(owner: str, repo: str, path: str) -> dict:
    """Read-only file lookup — the only kind of GitHub call this
    project's design permits any agent to make, and even this is not
    currently wired into any agent's tool list."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_file_contents", {"owner": owner, "repo": repo, "path": path}
            )
            text = result.content[0].text
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw_result": text}
