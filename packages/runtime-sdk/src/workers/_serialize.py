import asyncio
from weakref import ReferenceType, WeakKeyDictionary, ref

# Use weakref so that event loops can be garbage collected
# when they are no longer in use.
_locks: WeakKeyDictionary[asyncio.AbstractEventLoop, ReferenceType[asyncio.Lock]] = (
    WeakKeyDictionary()
)


def _get_lock() -> asyncio.Lock:
    """Return the serialization lock for the currently running event loop."""
    loop = asyncio.get_running_loop()
    lock_ref = _locks.get(loop)
    lock = lock_ref() if lock_ref is not None else None
    if lock is None:
        lock = asyncio.Lock()
        _locks[loop] = ref(lock)
    return lock


class RequestLock:
    """Manage one request's ownership of the shared serialization lock."""

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled
        self._lock: asyncio.Lock | None = None
        self._release_on_exit = True

    async def __aenter__(self) -> "RequestLock":
        if self._enabled:
            self._lock = _get_lock()
            await self._lock.acquire()
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
        if not self._enabled:
            return
        if self._release_on_exit:
            self.release()

    def defer_release(self) -> None:
        """
        When there are background streams that need to be processed,
        we need to defer the release of the lock until the streams are done.
        """
        if not self._enabled:
            return

        self._release_on_exit = False

    def release(self) -> None:
        """Release this request's lock once."""
        if not self._enabled:
            return

        lock = self._lock
        if lock is not None:
            self._lock = None
            lock.release()
