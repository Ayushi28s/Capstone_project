import asyncio
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class PersistentMCPConnection:
    def __init__(self, server_params: StdioServerParameters):
        self._server_params = server_params
        self._session: Optional[ClientSession] = None
        self._call_lock: Optional[asyncio.Lock] = None
        self._ready: Optional[asyncio.Event] = None
        self._start_lock: Optional[asyncio.Lock] = None
        self._error: Optional[BaseException] = None

    def _lazy_init_sync_primitives(self) -> None:
        # asyncio.Event/Lock need a running loop under them in general;
        # created on first async use rather than in __init__, since
        # __init__ can run before the persistent loop exists at all.
        if self._ready is None:
            self._ready = asyncio.Event()
        if self._start_lock is None:
            self._start_lock = asyncio.Lock()

    async def _run_connection(self) -> None:
        """Runs for the life of the process once started — the two
        async context managers (stdio_client, ClientSession) stay
        entered the whole time, which is what keeps the subprocess and
        the session alive across many separate calls instead of
        spawning fresh ones each time."""
        try:
            async with stdio_client(self._server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    self._call_lock = asyncio.Lock()
                    self._ready.set()
                    await asyncio.Event().wait()  # blocks here until the process exits
        except BaseException as exc:
            self._error = exc
            self._ready.set()
            raise

    async def _ensure_started(self) -> None:
        self._lazy_init_sync_primitives()
        if self._session is not None:
            return
        async with self._start_lock:
            if self._session is not None:  # re-check: another caller may have started it while we waited
                return
            asyncio.create_task(self._run_connection())
            await asyncio.wait_for(self._ready.wait(), timeout=15)
            if self._error is not None:
                raise self._error

    async def call_tool(self, name: str, args: dict) -> Any:
        await self._ensure_started()
        async with self._call_lock:
            result = await self._session.call_tool(name, args)
            return result.content[0].text
