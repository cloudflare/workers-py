import asyncio
import os
import sys

import asgi
import pytest
from pyodide.webloop import WebLoop
from workers import WorkerEntrypoint


async def noop(*args):
    pass


# pytest-asyncio relies on these but in Pyodide < 0.29 WebLoop does not implement them
WebLoop.shutdown_asyncgens = noop
WebLoop.shutdown_default_executor = noop

# Pyodide 0.26.0a2's _cancel_all_tasks calls task.exception() on pending tasks,
# which raises InvalidStateError under Pyodide's WebLoop.
if sys.version_info < (3, 13):
    asyncio.runners._cancel_all_tasks = lambda loop: None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ASGI apps
# ---------------------------------------------------------------------------


def check_encoding(byte_str, encoding="utf-8"):
    try:
        byte_str.decode(encoding)
    except UnicodeDecodeError:
        return False
    return True


class HeaderEchoApp:
    """ASGI app that echoes request headers back in the response."""

    def __init__(self):
        pass

    async def __call__(self, scope, receive, send) -> None:
        scope["app"] = self

        assert scope["type"] in ("http", "websocket", "lifespan")

        if scope["type"] == "lifespan":
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            return

        elif scope["type"] == "http":
            headers = scope["headers"]
            for header in headers:
                assert isinstance(header[0], bytes) and isinstance(header[1], bytes)
                assert check_encoding(header[0]) and check_encoding(header[1])

            await receive()
            # Send response and return
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": headers,
                }
            )

            await send(
                {
                    "type": "http.response.body",
                    "body": b"Hello, World",
                }
            )


class SSEApp:
    """ASGI app that sends Server-Sent Events (multiple streamed chunks)."""

    async def __call__(self, scope, receive, send) -> None:
        scope["app"] = self

        assert scope["type"] in ("http", "websocket", "lifespan")

        if scope["type"] == "lifespan":
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            return

        elif scope["type"] == "http":
            await receive()

            # Send SSE response headers
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"cache-control", b"no-store"),
                        (b"connection", b"keep-alive"),
                        (b"content-type", b"text/event-stream; charset=utf-8"),
                        (b"x-accel-buffering", b"no"),
                    ],
                }
            )

            # Send initial event
            await send(
                {
                    "type": "http.response.body",
                    "body": b"event: endpoint\r\ndata: /messages/?session_id=test123\r\n\r\n",
                    "more_body": True,
                }
            )

            # Send three ping events
            for i in range(3):
                # In a real app we would wait between events, but in the test we'll send them quickly
                await send(
                    {
                        "type": "http.response.body",
                        "body": f": ping - message {i + 1}\r\n\r\n".encode(),
                        "more_body": i < 2,  # last message has more_body=False
                    }
                )


STREAMING_CHUNK_SIZE = 1024
STREAMING_NUM_CHUNKS = 5


class StreamingApp:
    """ASGI app that streams multiple body chunks with a non-SSE content type.

    Reproduction test for bug https://github.com/cloudflare/workers-py/issues/67
    """

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            return

        if scope["type"] != "http":
            return

        # Consume the request body
        await receive()

        # Send response headers — NOT text/event-stream
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/octet-stream"),
                ],
            }
        )

        # Send multiple body chunks
        for i in range(STREAMING_NUM_CHUNKS):
            is_last = i == STREAMING_NUM_CHUNKS - 1
            # Each chunk is STREAMING_CHUNK_SIZE bytes filled with the chunk index
            chunk = bytes([i % 256]) * STREAMING_CHUNK_SIZE
            await send(
                {
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": not is_last,
                }
            )


# ---------------------------------------------------------------------------
# App instances and constants
# ---------------------------------------------------------------------------

app = HeaderEchoApp()
sse_app = SSEApp()
streaming_app = StreamingApp()

example_hdr = {"Header1": "Value1", "Header2": "Value2"}


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        from js import URL

        url = URL.new(request.url)
        path = url.pathname

        if path == "/sse":
            return await asgi.fetch(sse_app, request, self.env, self.ctx)
        elif path == "/stream":
            return await asgi.fetch(streaming_app, request, self.env, self.ctx)

        return await asgi.fetch(app, request, self.env, self.ctx)

    async def test(self):
        os.chdir("/session/metadata/tests")
        args = [".", "-vv"]
        assert pytest.main(args) == 0
