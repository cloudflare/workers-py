import json

import js
import pytest
from pyodide.ffi import to_js
from worker import (
    STREAMING_CHUNK_SIZE,
    STREAMING_NUM_CHUNKS,
    crash_app,
    example_hdr,
)

from workers import Request, env, wsgi


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


@pytest.mark.asyncio
async def test_streaming():
    response = await env.SELF.fetch("http://example.com/stream")
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
