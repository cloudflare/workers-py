"""
Top level runtime compatibility patches for packages.

These patches adapt packages that assume capabilities the workers runtime does
not provide. Unlike the entropy patches, they are not related to snapshotting.
"""

from contextlib import contextmanager

from _cloudflare.import_patch_manager import (
    register_exec_patch,
)


@register_exec_patch("anyio.to_thread")
@contextmanager
def anyio_to_thread_context(module):
    """`anyio.to_thread.run_sync` dispatches blocking work to an OS thread, but the
    workers runtime is single threaded, so starting a thread raises
    `RuntimeError: can't start new thread`. Run the callable inline instead.

    This function is the only caller of `run_sync_in_worker_thread`, which makes it
    the single chokepoint for every blocking call anyio makes on behalf of a
    framework. In starlette/fastapi that covers sync route handlers, sync
    dependencies, `StaticFiles`, `FileResponse`, `UploadFile`, `BackgroundTask` and
    `GZipMiddleware`, as well as `anyio.Path` and `anyio.open_file`.

    Patching the module attribute is enough because every caller looks it up at
    call time (e.g. `starlette.concurrency` and `anyio._core._fileio` both import
    the module rather than the function).

    We patch `anyio.to_thread` rather than the backend's
    `run_sync_in_worker_thread` because `anyio._backends._asyncio` is imported
    lazily by `get_async_backend()` during a request, by which point the import
    patch manager is no longer installed.
    """
    yield

    async def run_sync(func, *args, **kwargs):
        # Callers pass the function's own arguments positionally and anyio's
        # options (`limiter`, `abandon_on_cancel`, `cancellable`) as keywords.
        # None of the options mean anything without threads, so drop them.
        return func(*args)

    module.run_sync = run_sync
