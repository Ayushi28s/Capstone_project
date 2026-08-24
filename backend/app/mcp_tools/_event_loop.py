"""
Runs async MCP client calls from CrewAI's synchronous tool functions,
via ONE persistent background event loop shared for the whole process's
lifetime — not a fresh event loop created and torn down on every single
call.

Why this matters specifically: MCP's stdio_client() uses anyio's
TaskGroup internally to manage the subprocess's stdin/stdout
reader/writer tasks concurrently with the session logic. asyncio.run()
tears its event loop down immediately after the coroutine returns; on
Windows specifically (which needs ProactorEventLoop for subprocess
support), that teardown can race against the TaskGroup's own subprocess
cleanup still finishing up, surfacing as "unhandled errors in a
TaskGroup." This didn't show up until after the earlier Windows
subprocess-launch fix (using sys.executable instead of a bare "python"
string) — before that fix, the subprocess failed to start immediately,
before the TaskGroup ever reached real concurrent work that could race
on teardown. Fixing the launch bug is what surfaced this one
underneath it. A single long-lived loop, reused for every call instead
of recreated each time, avoids the repeated create/teardown cycle
entirely.
"""
import asyncio
import atexit
import threading
from typing import Any, Coroutine

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()


def _ensure_loop_running() -> asyncio.AbstractEventLoop:
    global _loop, _thread
    with _lock:
        if _loop is not None and _loop.is_running():
            return _loop
        _loop = asyncio.new_event_loop()
        _thread = threading.Thread(target=_loop.run_forever, name="mcp-event-loop", daemon=True)
        _thread.start()
        atexit.register(_stop_loop)
        return _loop


def _stop_loop() -> None:
    global _loop, _thread
    if _loop is not None and _loop.is_running():
        _loop.call_soon_threadsafe(_loop.stop)
    if _thread is not None:
        _thread.join(timeout=5)


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Submits a coroutine to the shared persistent loop and blocks
    until it completes, re-raising any exception the coroutine itself
    raised — exception handling in callers (e.g. try/except around a
    tool call) works exactly the same as it did with asyncio.run().

    Unwraps ExceptionGroup/BaseExceptionGroup (what asyncio.TaskGroup
    raises, Python 3.11+) before re-raising, surfacing the real
    underlying exception instead of the opaque wrapper. "unhandled
    errors in a TaskGroup" on its own says nothing about what actually
    failed inside — this is what makes the real cause visible instead
    of requiring another round of guessing."""
    loop = _ensure_loop_running()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result()
    except BaseException as exc:
        # ExceptionGroup / BaseExceptionGroup are the same concept;
        # checking by class name avoids needing a Python-version guard
        # for a class that's only a real builtin from 3.11 onward.
        if type(exc).__name__ in ("ExceptionGroup", "BaseExceptionGroup"):
            inner = getattr(exc, "exceptions", ())
            if inner:
                raise inner[0] from exc
        raise
