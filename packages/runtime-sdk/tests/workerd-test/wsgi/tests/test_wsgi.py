import asyncio
import json

import js
import pytest
from pyodide.ffi import run_sync, to_js
from worker import (
    STREAMING_CHUNK_SIZE,
    STREAMING_NUM_CHUNKS,
    crash_app,
    example_hdr,
    header_echo_app,
)

from workers import Request, WorkerEntrypoint, env, wsgi


@pytest.mark.asyncio
async def test_generated_entrypoint_serves_wsgi_app():
    default = wsgi.entrypoint(header_echo_app)
    assert default.__name__ == "Default"
    assert issubclass(default, WorkerEntrypoint)

    entrypoint = object.__new__(default)
    entrypoint.env = {}
    response = await entrypoint.fetch(js.Request.new("http://example.com/"))

    assert response.status == 200
    assert await response.text() == "Hello, World"


@pytest.mark.asyncio
async def test_headers():
    response = await env.SELF.fetch("http://example.com/", headers=to_js(example_hdr))
    assert response.status == 200
    text = await response.text()
    assert text == "Hello, World"
    # Echoed-back headers should be present.
    assert response.headers.get("header1") == "Value1"
    assert response.headers.get("header2") == "Value2"


@pytest.mark.asyncio
async def test_echo_body():
    response = await env.SELF.fetch(
        "http://example.com/echo-body",
        method="POST",
        body="hello body",
    )
    assert response.status == 200
    text = await response.text()
    assert text == "hello body"


@pytest.mark.asyncio
async def test_meta():
    response = await env.SELF.fetch("http://example.com/meta?foo=bar&baz=qux")
    assert response.status == 200

    payload = json.loads(await response.text())
    assert payload["method"] == "GET"
    assert payload["path"] == "/meta"
    assert payload["query"] == "foo=bar&baz=qux"
    assert payload["scheme"] == "http"
    assert payload["has_env"] is True


@pytest.mark.asyncio
async def test_cookies():
    response = await env.SELF.fetch("http://example.com/cookies")
    assert response.status == 200
    # `env.SELF.fetch` returns the SDK `FetchResponse`, whose `.headers` is an
    # `http.client.HTTPMessage`. Repeated Set-Cookie headers are preserved as
    # separate entries (see `python_request_headers_preserve_commas`), so use
    # `get_all` to recover the individual values.
    cookies = response.headers.get_all("Set-Cookie")
    assert "a=1" in cookies
    assert "b=2" in cookies


@pytest.mark.parametrize("endpoint", ("stream", "stream-stack-switch"))
@pytest.mark.asyncio
async def test_streaming(endpoint):
    response = await env.SELF.fetch("http://example.com/" + endpoint)
    assert response.status == 200
    assert response.headers.get("content-type") == "application/octet-stream"

    reader = response.body.getReader()
    body_bytes = b""
    while True:
        result = await reader.read()
        if result.done:
            break
        body_bytes += result.value.to_bytes()

    expected_size = STREAMING_CHUNK_SIZE * STREAMING_NUM_CHUNKS
    assert len(body_bytes) == expected_size, (
        f"Expected {expected_size} bytes, got {len(body_bytes)}"
    )
    for i in range(STREAMING_NUM_CHUNKS):
        start = i * STREAMING_CHUNK_SIZE
        end = start + STREAMING_CHUNK_SIZE
        expected_byte = i % 256
        assert all(b == expected_byte for b in body_bytes[start:end])


@pytest.mark.asyncio
async def test_app_exception_is_raised():
    req = js.Request.new("http://example.com/crash-test")
    with pytest.raises(RuntimeError, match="app crash before response for testing"):
        await wsgi.fetch(crash_app, req, env)


def test_build_environ_handles_js_and_python_requests():
    # Verify `build_environ` handles JS-style and Python-style headers
    # identically, mirroring the asgi `request_to_scope` check.
    js_request = js.Request.new("http://example.com/", headers=to_js(example_hdr))
    py_request = Request("http://example.com/", headers=example_hdr)
    js_env = wsgi.build_environ(js_request, env, b"")
    py_env = wsgi.build_environ(py_request, env, b"")
    assert js_env["HTTP_HEADER1"] == py_env["HTTP_HEADER1"] == "Value1"
    assert js_env["HTTP_HEADER2"] == py_env["HTTP_HEADER2"] == "Value2"


class _ConcurrentApp:
    def __init__(self):
        self.active = 0
        self.max_active = 0

    def __call__(self, environ, start_response):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        run_sync(asyncio.sleep(0.05))
        self.active -= 1
        start_response("200 OK", [])
        return [b"ok"]


async def _fetch_wsgi_text(app, *, serialize=False):
    response = await wsgi.fetch(
        app, js.Request.new("http://example.com/"), env, serialize=serialize
    )
    return await response.text()


@pytest.mark.asyncio
async def test_serialized_wsgi_requests_do_not_overlap():
    app = _ConcurrentApp()
    await asyncio.wait_for(
        asyncio.gather(
            _fetch_wsgi_text(app, serialize=True),
            _fetch_wsgi_text(app, serialize=True),
            _fetch_wsgi_text(app, serialize=True),
            _fetch_wsgi_text(app, serialize=True),
        ),
        timeout=5,
    )
    assert app.max_active == 1


@pytest.mark.asyncio
async def test_default_wsgi_requests_can_overlap():
    app = _ConcurrentApp()
    await asyncio.wait_for(
        asyncio.gather(
            _fetch_wsgi_text(app),
            _fetch_wsgi_text(app),
        ),
        timeout=5,
    )
    assert app.max_active == 2


@pytest.mark.asyncio
async def test_serialized_wsgi_streams_and_closes_original_iterable():
    class Iterable:
        def __init__(self):
            self.closed = False

        def __iter__(self):
            yield b"first"
            yield b"second"

        def close(self):
            self.closed = True

    result = Iterable()
    seen_input = None
    seen_body = None

    def app(environ, start_response):
        nonlocal seen_body, seen_input
        seen_input = environ["wsgi.input"]
        seen_body = seen_input.read()
        write = start_response(
            "200 Everything", [("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")]
        )
        write(b"before")
        return result

    response = await wsgi.fetch(
        app,
        js.Request.new("http://example.com/", method="POST", body="request"),
        env,
        serialize=True,
    )
    assert seen_input is not None
    assert seen_body == b"request"
    assert response.status == 200
    assert response.statusText == "Everything"
    assert not result.closed
    assert not seen_input.closed
    assert await response.text() == "beforefirstsecond"
    assert result.closed
    assert seen_input.closed
    assert response.headers.get("set-cookie") == "a=1, b=2"


@pytest.mark.asyncio
async def test_serialized_wsgi_iteration_error_releases_lock():
    def failing_app(environ, start_response):
        start_response("200 OK", [])

        def fail():
            raise RuntimeError("iteration failed")
            yield b"unreachable"

        return fail()

    with pytest.raises(RuntimeError, match="iteration failed"):
        await asyncio.wait_for(
            wsgi.fetch(
                failing_app, js.Request.new("http://example.com/"), env, serialize=True
            ),
            timeout=5,
        )
    response = await asyncio.wait_for(
        wsgi.fetch(
            header_echo_app, js.Request.new("http://example.com/"), env, serialize=True
        ),
        timeout=5,
    )
    assert await response.text() == "Hello, World"

