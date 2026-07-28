import asyncio
import os
import sys

import asgi
import pytest
from pyodide.webloop import WebLoop
from workers import WorkerEntrypoint


async def _noop(*args):
    pass


# pytest-asyncio relies on these but in Pyodide < 0.29 WebLoop does not implement them
WebLoop.shutdown_asyncgens = _noop
WebLoop.shutdown_default_executor = _noop

# Pyodide 0.26.0a2's _cancel_all_tasks calls task.exception() on pending tasks,
# which raises InvalidStateError under Pyodide's WebLoop.
if sys.version_info < (3, 13):
    asyncio.runners._cancel_all_tasks = lambda loop: None  # type: ignore[attr-defined]


async def _drain_lifespan(receive, send):
    message = await receive()
    if message["type"] == "lifespan.startup":
        await send({"type": "lifespan.startup.complete"})


class ScopeEchoApp:
    """Echoes selected scope fields as JSON so tests can inspect them."""

    async def __call__(self, scope, receive, send):
        import json

        if scope["type"] == "lifespan":
            await _drain_lifespan(receive, send)
            return
        await receive()
        body = json.dumps(
            {
                "path": scope["path"],
                "raw_path": (scope.get("raw_path") or b"").decode(),
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})


app = ScopeEchoApp()


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return await asgi.fetch(app, request, self.env, self.ctx)

    async def test(self):
        os.chdir("/session/metadata/tests")
        args = [".", "-vv"]
        assert pytest.main(args) == 0
