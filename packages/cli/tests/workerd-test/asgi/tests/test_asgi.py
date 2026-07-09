import asyncio
import logging

import asgi
import js
import pytest
from pyodide.ffi import to_js
from worker import STREAMING_CHUNK_SIZE, STREAMING_NUM_CHUNKS, example_hdr
from workers import Request, env


def test_request_to_scope_matches_js_and_py():
    # Verify that `asgi` can handle JS-style headers and Python-style headers:
    js_request = js.Request.new("http://example.com/", headers=to_js(example_hdr))
    py_request = Request("http://example.com/", headers=example_hdr)
    js_scope = asgi.request_to_scope(js_request, env)
    py_scope = asgi.request_to_scope(py_request, env)
    expected = [(k.lower().encode(), v.encode()) for k, v in example_hdr.items()]
    assert js_scope["headers"] == py_scope["headers"] == expected


@pytest.mark.asyncio
async def test_headers():
    response = await env.SELF.fetch("http://example.com/", headers=to_js(example_hdr))
    expected_hdr = {k.lower(): v.lower() for k, v in example_hdr.items()}
    for header in response.headers.items():
        assert isinstance(header[0], str) and isinstance(header[1], str)
        assert header[0] in expected_hdr
        assert expected_hdr[header[0]] == header[1].lower()


@pytest.mark.asyncio
async def test_sse():
    response = await env.SELF.fetch("http://example.com/sse")

    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert response.headers["cache-control"] == "no-store"

    reader = response.body.getReader()
    decoder = js.TextDecoder.new()
    content = ""
    while True:
        result = await reader.read()
        if result.done:
            break
        content += decoder.decode(result.value, {"stream": True})
    # Final flush
    content += decoder.decode()

    # Verify the expected events are in the response
    assert "event: endpoint" in content
    assert "data: /messages/?session_id=test123" in content
    assert ": ping - message 1" in content
    assert ": ping - message 2" in content
    assert ": ping - message 3" in content


@pytest.mark.asyncio
async def test_streaming():
    response = await env.SELF.fetch("http://example.com/stream")

    assert response.status == 200
    assert response.headers["content-type"] == "application/octet-stream"

    # Read the full response body via ReadableStream (same pattern as SSE test)
    reader = response.body.getReader()
    body_bytes = b""
    while True:
        result = await reader.read()
        if result.done:
            break
        body_bytes += result.value.to_bytes()

    expected_size = STREAMING_CHUNK_SIZE * STREAMING_NUM_CHUNKS  # 5120 bytes
    assert len(body_bytes) == expected_size
    # Verify each chunk has the correct content
    for i in range(STREAMING_NUM_CHUNKS):
        start = i * STREAMING_CHUNK_SIZE
        chunk = body_bytes[start : start + STREAMING_CHUNK_SIZE]
        assert all(b == i % 256 for b in chunk)


class _ListHandler(logging.Handler):
    """A logging handler that captures records into a list for assertions."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


def _install_handler():
    """Install a ListHandler on the 'asgi' logger and return it."""
    handler = _ListHandler()
    logger = logging.getLogger("asgi")
    logger.addHandler(handler)
    # Ensure the logger level is low enough to capture everything.
    logger.setLevel(logging.DEBUG)
    return handler


def _remove_handler(handler):
    logging.getLogger("asgi").removeHandler(handler)


class _ErrorAfterResponseApp:
    """ASGI app that sends a valid response, then raises an exception."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            return
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})
        # Response is already sent — now raise an error.
        raise RuntimeError("post-response error for testing")


@pytest.mark.asyncio
async def test_error_after_response_is_logged():
    handler = _install_handler()
    try:
        req = js.Request.new("http://example.com/log-test")
        # The response should still succeed — the error happens after it's sent.
        response = await asgi.fetch(_ErrorAfterResponseApp(), req, env)
        assert response.status == 200
        # consume the body
        await response.arrayBuffer()
        # Let the event loop run
        await asyncio.sleep(0.5)

        # The error should have been logged, not swallowed.
        errors = [r for r in handler.records if r.levelno >= logging.ERROR]
        assert any(
            r.exc_info and "post-response error for testing" in str(r.exc_info[1])
            for r in errors
        )
    finally:
        _remove_handler(handler)


@pytest.mark.asyncio
async def test_background_task_error_is_logged():
    handler = _install_handler()
    try:

        async def failing_task():
            raise ValueError("background task failure for testing")

        asgi.run_in_background(failing_task())
        # Let the event loop run
        await asyncio.sleep(0.5)

        errors = [r for r in handler.records if r.levelno >= logging.ERROR]
        assert any(
            r.exc_info and "background task failure for testing" in str(r.exc_info[1])
            for r in errors
        )
    finally:
        _remove_handler(handler)


class _ErrorBeforeResponseApp:
    """ASGI app that raises before sending any response."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            return
        await receive()
        raise RuntimeError("app crash before response for testing")


@pytest.mark.asyncio
async def test_app_exception_before_response_is_logged():
    handler = _install_handler()
    try:
        req = js.Request.new("http://example.com/crash-test")
        with pytest.raises(RuntimeError, match="app crash before response for testing"):
            await asgi.fetch(_ErrorBeforeResponseApp(), req, {})

        # fetch() should have logged the error before re-raising.
        errors = [r for r in handler.records if r.levelno >= logging.ERROR]
        assert any("ASGI request failed" in r.getMessage() for r in errors)
    finally:
        _remove_handler(handler)


class _NoLifespanApp:
    """Mimics Django's ASGIHandler, which raises on any non-http scope."""

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            raise ValueError(f"can only handle http, not {scope['type']}")
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"served"})


@pytest.mark.asyncio
async def test_lifespan_unsupported_app_does_not_hang():
    req = js.Request.new("http://example.com/no-lifespan")
    # The previous adaptor blocked forever waiting for a startup ack the app
    # never sends; wait_for turns that hang into an observable test failure.
    response = await asyncio.wait_for(asgi.fetch(_NoLifespanApp(), req, env), timeout=5)
    assert response.status == 200
    assert await response.text() == "served"


class _NullBodyApp:
    def __init__(self, status):
        self._status = status

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            return
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": self._status,
                "headers": [(b"x-null-body", b"1")],
            }
        )
        await send({"type": "http.response.body", "body": b"body-should-be-dropped"})


@pytest.mark.asyncio
async def test_null_body_statuses():
    for status in (204, 205, 304):
        req = js.Request.new(f"http://example.com/null-body/{status}")
        response = await asgi.fetch(_NullBodyApp(status), req, env)
        assert response.status == status
        assert response.headers["x-null-body"] == "1"
        assert await response.text() == ""


class _MissingHeadersApp:
    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            return
        await receive()
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"ok"})


@pytest.mark.asyncio
async def test_response_start_without_headers():
    req = js.Request.new("http://example.com/missing-headers")
    response = await asgi.fetch(_MissingHeadersApp(), req, env)
    assert response.status == 200
    assert await response.text() == "ok"


class _MissingBodyKeyApp:
    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            return
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body"})


@pytest.mark.asyncio
async def test_response_body_without_body_key():
    req = js.Request.new("http://example.com/missing-body")
    response = await asgi.fetch(_MissingBodyKeyApp(), req, env)
    assert response.status == 200
    assert await response.text() == ""


class _LifespanCycleApp:
    def __init__(self):
        self.events = []

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    self.events.append("startup")
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    self.events.append("shutdown")
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})


@pytest.mark.asyncio
async def test_lifespan_full_cycle():
    lifespan_app = _LifespanCycleApp()
    req = js.Request.new("http://example.com/lifespan-cycle")
    response = await asgi.fetch(lifespan_app, req, env)
    assert response.status == 200
    assert lifespan_app.events == ["startup", "shutdown"]


class _StartupFailApp:
    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await receive()
            await send({"type": "lifespan.startup.failed", "message": "boom-startup"})
            return
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


@pytest.mark.asyncio
async def test_lifespan_startup_failed_propagates():
    req = js.Request.new("http://example.com/startup-fail")
    with pytest.raises(RuntimeError, match="boom-startup"):
        await asyncio.wait_for(asgi.fetch(_StartupFailApp(), req, env), timeout=5)


class _ShutdownFailApp:
    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send(
                        {"type": "lifespan.shutdown.failed", "message": "boom-shutdown"}
                    )
                    return
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


@pytest.mark.asyncio
async def test_lifespan_shutdown_failed_propagates():
    req = js.Request.new("http://example.com/shutdown-fail")
    with pytest.raises(RuntimeError, match="boom-shutdown"):
        await asyncio.wait_for(asgi.fetch(_ShutdownFailApp(), req, env), timeout=5)
