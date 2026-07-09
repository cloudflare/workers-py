import logging
from asyncio import Event, Future, Queue, create_task, ensure_future
from collections.abc import Awaitable
from contextlib import contextmanager
from typing import Any

import js

from workers import Context, Request

ASGI = {"spec_version": "2.0", "version": "3.0"}
NULL_BODY_STATUSES = frozenset({101, 103, 204, 205, 304})
logger = logging.getLogger("asgi")
background_tasks = set()


def run_in_background(coro: Awaitable[Any]) -> None:
    fut = ensure_future(coro)
    background_tasks.add(fut)

    def _on_done(f):
        background_tasks.discard(f)
        exc = f.exception() if not f.cancelled() else None
        if exc is not None:
            logger.error("Unhandled exception in background task", exc_info=exc)

    fut.add_done_callback(_on_done)


@contextmanager
def acquire_js_buffer(pybuffer):
    from pyodide.ffi import create_proxy

    px = create_proxy(pybuffer)
    buf = px.getBuffer()
    px.destroy()
    try:
        yield buf.data
    finally:
        buf.release()


def request_to_scope(req, env, ws=False):
    from js import URL

    # @app.get("/example")
    # async def example(request: Request):
    #     request.headers.get("content-type")
    # - this will error if header is not "bytes" as in ASGI spec.

    # Support both JS and Python http.client.HTTPMessage headers.
    req_headers = req.headers.items() if isinstance(req, Request) else req.headers

    headers = [(k.lower().encode(), v.encode()) for k, v in req_headers]
    url = URL.new(req.url)
    assert url.protocol[-1] == ":"
    scheme = url.protocol[:-1]
    path = url.pathname
    assert "?".startswith(url.search[0:1])
    query_string = url.search[1:].encode()
    if ws:
        ty = "websocket"
    else:
        ty = "http"
    return {
        "asgi": ASGI,
        "headers": headers,
        "http_version": "1.1",
        "method": req.method,
        "scheme": scheme,
        "path": path,
        "query_string": query_string,
        "type": ty,
        "env": env,
    }


async def start_application(app):
    # Drives one ASGI lifespan startup/shutdown cycle before/after serving the
    # request. The lifespan protocol is optional, so we must tolerate apps that
    # don't implement it and fall back to serving requests without lifespan.
    # https://asgi.readthedocs.io/en/latest/specs/lifespan.html
    receive_queue = Queue()
    await receive_queue.put({"type": "lifespan.startup"})

    # `startup` resolves True on `lifespan.startup.complete`, False when the app
    # has no lifespan support, and raises on `lifespan.startup.failed`.
    # `shutdown_complete` mirrors the shutdown phase.
    startup = Future()
    shutdown_complete = Future()

    async def shutdown():
        # Nothing to shut down if the app never completed a lifespan startup.
        if startup.done() and not startup.result():
            return
        await receive_queue.put({"type": "lifespan.shutdown"})
        await shutdown_complete

    async def no_lifespan_shutdown():
        return

    async def receive():
        return await receive_queue.get()

    async def send(got):
        if got["type"] == "lifespan.startup.complete":
            if not startup.done():
                startup.set_result(True)
            return
        if got["type"] == "lifespan.startup.failed":
            message = got.get("message", "ASGI lifespan startup failed")
            if not startup.done():
                startup.set_exception(RuntimeError(message))
            return
        if got["type"] == "lifespan.shutdown.complete":
            if not shutdown_complete.done():
                shutdown_complete.set_result(None)
            return
        if got["type"] == "lifespan.shutdown.failed":
            message = got.get("message", "ASGI lifespan shutdown failed")
            if not shutdown_complete.done():
                shutdown_complete.set_exception(RuntimeError(message))
            return
        raise RuntimeError(f"Unexpected lifespan event {got['type']}")

    async def run_lifespan():
        try:
            await app(
                {
                    "asgi": ASGI,
                    "state": {},
                    "type": "lifespan",
                },
                receive,
                send,
            )
            # App returned without acking: a missing startup ack means it has no
            # lifespan handler, so mark startup unsupported rather than hanging.
            if not startup.done():
                startup.set_result(False)
            elif not shutdown_complete.done():
                shutdown_complete.set_result(None)
        except Exception as exc:
            # Spec: an exception raised before startup is acked signals that the
            # app doesn't support lifespan; swallow it and serve requests anyway.
            if not startup.done():
                startup.set_result(False)
                return
            # After a successful startup, a shutdown-phase error can't affect the
            # already-served request, so log it and let shutdown complete.
            logger.exception("Exception in ASGI lifespan application", exc_info=exc)
            if not shutdown_complete.done():
                shutdown_complete.set_result(None)

    run_in_background(run_lifespan())
    supported = await startup
    if not supported:
        return no_lifespan_shutdown
    return shutdown


async def process_request(
    app: Any,
    req: "Request | js.Request",
    env: Any,
    # added for waitUntil, but not used anymore
    # TODO(later): remove this parameter after unvendoring Python SDK from workerd
    ctx: Context | None,
) -> js.Response:
    from js import Object, Response, TransformStream
    from pyodide.ffi import create_proxy

    status = None
    headers = None
    result = Future()
    finished_response = Event()

    # Streaming state — initialized lazily on first body chunk with more_body=True.
    writer = None

    receive_queue = Queue()
    if req.body:
        async for data in req.body:
            await receive_queue.put(
                {
                    "body": data.to_bytes(),
                    "more_body": True,
                    "type": "http.request",
                }
            )
    await receive_queue.put({"body": b"", "more_body": False, "type": "http.request"})

    async def receive():
        message = None
        if not receive_queue.empty():
            message = await receive_queue.get()
        else:
            await finished_response.wait()
            message = {"type": "http.disconnect"}
        return message

    async def send(got):
        nonlocal status
        nonlocal headers
        nonlocal writer

        if got["type"] == "http.response.start":
            status = got["status"]
            # Like above, we need to convert byte-pairs into string explicitly.
            headers = [(k.decode(), v.decode()) for k, v in got.get("headers", [])]

        elif got["type"] == "http.response.body":
            body = got.get("body", b"")
            more_body = got.get("more_body", False)

            if writer is not None:
                # Already in streaming mode — write chunk to the stream.
                with acquire_js_buffer(body) as jsbytes:
                    await writer.write(jsbytes.slice())
                if not more_body:
                    await writer.close()
                    finished_response.set()
            elif more_body:
                # First body chunk with more data coming — switch to streaming.
                # Create a TransformStream so the runtime can start consuming
                # body chunks as they are written.
                transform_stream = TransformStream.new()
                readable = transform_stream.readable
                writer = transform_stream.writable.getWriter()
                resp = Response.new(
                    readable, headers=Object.fromEntries(headers), status=status
                )
                result.set_result(resp)
                with acquire_js_buffer(body) as jsbytes:
                    await writer.write(jsbytes.slice())
            elif status in NULL_BODY_STATUSES:
                # 101/103/204/205/304 must not carry a body per the Fetch spec.
                # https://fetch.spec.whatwg.org/#null-body-status
                resp = Response.new(
                    None, headers=Object.fromEntries(headers), status=status
                )
                result.set_result(resp)
                finished_response.set()
            else:
                # Complete body in a single chunk
                px = create_proxy(body)
                buf = px.getBuffer()
                px.destroy()
                resp = Response.new(
                    buf.data, headers=Object.fromEntries(headers), status=status
                )
                result.set_result(resp)
                finished_response.set()

    # Run the application in the background
    async def run_app():
        try:
            await app(request_to_scope(req, env), receive, send)

            # If we get here and no response has been set yet, the app didn't generate a response
            if not result.done():
                raise RuntimeError("The application did not generate a response")  # noqa: TRY301
        except Exception as e:
            if not result.done():
                result.set_exception(e)
                if writer is not None:
                    await writer.close()
                finished_response.set()
            else:
                # Response already sent — exception can't be propagated to the
                # client, so log it to avoid silently swallowing errors.
                logger.exception("Exception in ASGI application after response started")

    # Create task to run the application in the background
    app_task = create_proxy(create_task(run_app()))

    from workers import wait_until

    wait_until(app_task)

    try:
        return await result
    finally:
        app_task.destroy()


async def process_websocket(app: Any, req: "Request | js.Request") -> js.Response:
    from js import Response, WebSocketPair

    client, server = WebSocketPair.new().object_values()
    server.accept()
    queue = Queue()

    def onopen(evt):
        msg = {"type": "websocket.connect"}
        queue.put_nowait(msg)

    # onopen doesn't seem to get called. WS lifecycle events are a bit messed up
    # here.
    onopen(1)

    def onclose(evt):
        msg = {"type": "websocket.close", "code": evt.code, "reason": evt.reason}
        queue.put_nowait(msg)

    def onmessage(evt):
        msg = {"type": "websocket.receive", "text": evt.data}
        queue.put_nowait(msg)

    server.onopen = onopen
    server.onopen = onclose
    server.onmessage = onmessage

    async def ws_send(got):
        if got["type"] == "websocket.send":
            b = got.get("bytes", None)
            s = got.get("text", None)
            if b:
                with acquire_js_buffer(b) as jsbytes:
                    # Unlike the `Response` constructor,  server.send seems to
                    # eagerly copy the source buffer
                    server.send(jsbytes)
            if s:
                server.send(s)

        else:
            logger.warning(" == Not implemented %s", got["type"])

    async def ws_receive():
        received = await queue.get()
        return received

    env = {}
    run_in_background(app(request_to_scope(req, env, ws=True), ws_receive, ws_send))

    return Response.new(None, status=101, webSocket=client)


async def fetch(
    app: Any, req: "Request | js.Request", env: Any, ctx: Context | None = None
) -> js.Response:
    logger.debug("ASGI request: %s %s", req.method, req.url)
    shutdown = await start_application(app)
    try:
        result = await process_request(app, req, env, ctx)
    except Exception:
        logger.exception("ASGI request failed")
        raise
    await shutdown()
    return result


async def websocket(app: Any, req: "Request | js.Request") -> js.Response:
    return await process_websocket(app, req)


def __getattr__(name):
    if name == "env":
        from fastapi import Depends, Request

        @Depends
        async def env(request: Request):
            return request.scope["env"]

        return env

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
