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
