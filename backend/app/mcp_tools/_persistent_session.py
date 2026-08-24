"""
Persistent MCP client connections — one subprocess + session per
server, opened once and reused for every tool call, instead of
spawning a fresh subprocess and tearing the whole thing down on every
single call.

This is the deeper fix behind "unhandled errors in a TaskGroup"
failures that persisted even after switching to a shared, persistent
event loop (_event_loop.py): that earlier fix addressed the outer event
loop being recreated per call, but every MCP client function was still
opening `async with stdio_client(...)` fresh, spawning a brand new
subprocess, and tearing the whole thing down (subprocess included) on
every single call — regardless of whether the surrounding event loop
persisted. Repeated subprocess spawn/teardown against Windows'
ProactorEventLoop, not just event-loop churn, is the more likely actual
source of the race. This keeps one subprocess and one MCP session alive
for the worker process's whole lifetime instead, started lazily on
first use.

IMPORTANT — everything in this module is async and must only ever be
awaited from a coroutine that's already running on the shared
persistent loop (see _event_loop.py). It deliberately does NOT do any
cross-thread dispatch (run_coroutine_threadsafe) internally — only
_event_loop.run_async() does that, exactly once, at the top level, when
a caller like support_crew.py's synchronous CrewAI tool functions first
hand off a coroutine to the persistent loop's thread. If this module's
own connection-startup logic also tried to cross-thread-dispatch-and-
block-wait for itself, it would deadlock the instant it's called from
inside a coroutine that's already executing ON that loop's thread —
the loop can't make progress on starting the connection while its own
thread is blocked waiting for that same connection to start. Staying
purely `await`-based here, with only ONE cross-thread handoff at the
very top of the call chain, is what avoids that.
"""
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
