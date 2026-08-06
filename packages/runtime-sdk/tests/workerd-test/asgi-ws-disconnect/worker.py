import asyncio
import os
import sys
from urllib.parse import urlsplit

import pytest
from pyodide.webloop import WebLoop

import asgi
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


ws_events = []


class WSWatchApp:
    """Accepts and records the client's disconnect in ws_events."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await _drain_lifespan(receive, send)
            return
        message = await receive()
        assert message["type"] == "websocket.connect"
        await send({"type": "websocket.accept"})
        while True:
            message = await receive()
            if message["type"] == "websocket.disconnect":
                ws_events.append({"type": "disconnect", "code": message.get("code")})
                return


class WSEmptyFrameApp:
    """On each client frame, replies with an empty text frame, an empty binary
    frame, and a sentinel, so a test can tell whether empty frames reach the
    client at all."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await _drain_lifespan(receive, send)
            return
        message = await receive()
        assert message["type"] == "websocket.connect"
        await send({"type": "websocket.accept"})
        while True:
            message = await receive()
            if message["type"] == "websocket.disconnect":
                return
            await send({"type": "websocket.send", "text": ""})
            await send({"type": "websocket.send", "bytes": b""})
            await send({"type": "websocket.send", "text": "done"})


ws_app = WSWatchApp()
empty_frame_app = WSEmptyFrameApp()


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        if (request.headers.get("upgrade") or "").lower() == "websocket":
            path = urlsplit(request.url).path
            app = empty_frame_app if path == "/ws-empty" else ws_app
            return await asgi.websocket(app, request)
        import json

        from workers import Response

        return Response(
            json.dumps(ws_events), headers={"content-type": "application/json"}
        )

    async def test(self):
        os.chdir("/session/metadata/tests")
        args = [".", "-vv"]
        assert pytest.main(args) == 0
