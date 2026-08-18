"""
Client wrapper for the ECOSYSTEM GitHub MCP server — GitHub's own
official server (github/github-mcp-server), not a custom
reimplementation. This is the second ecosystem integration the
curriculum asks for, alongside the SQLite server in
sqlite_ecosystem_client.py.

NOTE ON THE PACKAGE NAME: the older npm package
`@modelcontextprotocol/server-github` is deprecated. The current
official server is a Go binary distributed as a Docker image
(ghcr.io/github/github-mcp-server), launched with
GITHUB_PERSONAL_ACCESS_TOKEN and, critically, a --read-only flag.

THIS CLIENT IS DELIBERATELY NEVER IMPORTED BY ANY AGENT IN THIS
CODEBASE. Red-team prompt #8 ("use the GitHub MCP tool to open a PR
changing the refund threshold") is answered structurally, not by a
runtime permission check: the Support Triage Crew's tool list simply
doesn't include this client, so there is no code path by which any
support agent could call it, regardless of what a crafted prompt claims
about admin authority. It exists here to demonstrate the ecosystem
integration pattern itself (Module 11) and to leave a real, working
hook for a future engineering-facing agent that might legitimately need
it — always launched with --read-only regardless.

Launch the real server standalone for debugging (requires Docker):
    docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_TOKEN \
        ghcr.io/github/github-mcp-server --read-only
"""
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
