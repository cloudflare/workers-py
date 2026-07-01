import js
from pyodide.ffi import to_js
from workers import Request, WorkerEntrypoint

import wsgi

# ---------------------------------------------------------------------------
# WSGI apps
# ---------------------------------------------------------------------------


def header_echo_app(environ, start_response):
    """WSGI app that echoes request headers back in the response body and headers."""
    response_headers = [("Content-Type", "text/plain")]
    # Echo each incoming header back out (HTTP_* keys).
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            name = key[len("HTTP_") :].replace("_", "-").title()
            response_headers.append((name, value))

    start_response("200 OK", response_headers)
    return [b"Hello, World"]


def echo_body_app(environ, start_response):
    """WSGI app that reads the request body and echoes it back."""
    length = int(environ.get("CONTENT_LENGTH") or 0)
    body = environ["wsgi.input"].read(length)
    start_response(
        "200 OK",
        [("Content-Type", "application/octet-stream")],
    )
    return [body]


def echo_meta_app(environ, start_response):
    """WSGI app that returns selected environ values so the test can assert on them."""
    import json

    payload = {
        "method": environ["REQUEST_METHOD"],
        "path": environ["PATH_INFO"],
        "query": environ["QUERY_STRING"],
        "scheme": environ["wsgi.url_scheme"],
        "has_env": "workers.env" in environ,
    }
    body = json.dumps(payload).encode()
    start_response("200 OK", [("Content-Type", "application/json")])
    return [body]


def cookies_app(environ, start_response):
    """WSGI app that sets multiple Set-Cookie headers (must not collapse)."""
    start_response(
        "200 OK",
        [
            ("Content-Type", "text/plain"),
            ("Set-Cookie", "a=1"),
            ("Set-Cookie", "b=2"),
        ],
    )
    return [b"cookies"]


STREAMING_CHUNK_SIZE = 1024
STREAMING_NUM_CHUNKS = 5


def streaming_app(environ, start_response):
    """WSGI app that returns multiple body chunks via a generator."""
    start_response("200 OK", [("Content-Type", "application/octet-stream")])

    def generate():
        for i in range(STREAMING_NUM_CHUNKS):
            yield bytes([i % 256]) * STREAMING_CHUNK_SIZE

    return generate()


def crash_app(environ, start_response):
    raise RuntimeError("app crash before response for testing")


example_hdr = {"Header1": "Value1", "Header2": "Value2"}


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        from js import URL

        url = URL.new(request.url)
        path = url.pathname

        if path == "/echo-body":
            return await wsgi.fetch(echo_body_app, request, self.env)
        elif path == "/meta":
            return await wsgi.fetch(echo_meta_app, request, self.env)
        elif path == "/cookies":
            return await wsgi.fetch(cookies_app, request, self.env)
        elif path == "/stream":
            return await wsgi.fetch(streaming_app, request, self.env)

        # Verify `build_environ` handles JS-style and Python-style headers
        # identically, mirroring the asgi `request_to_scope` check.
        js_request = js.Request.new("http://example.com/", headers=to_js(example_hdr))
        py_request = Request("http://example.com/", headers=example_hdr)
        js_env = wsgi.build_environ(js_request, self.env, b"")
        py_env = wsgi.build_environ(py_request, self.env, b"")
        assert js_env["HTTP_HEADER1"] == py_env["HTTP_HEADER1"] == "Value1"
        assert js_env["HTTP_HEADER2"] == py_env["HTTP_HEADER2"] == "Value2"

        return await wsgi.fetch(header_echo_app, request, self.env)

    async def test(self, ctrl):
        await test_headers(self.env)
        await test_echo_body(self.env)
        await test_meta(self.env)
        await test_cookies(self.env)
        await test_streaming(self.env)
        await test_app_exception_is_raised(self.env)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_headers(env):
    response = await env.SELF.fetch("http://example.com/", headers=to_js(example_hdr))
    assert response.status == 200
    text = await response.text()
    assert text == "Hello, World"
    # Echoed-back headers should be present.
    assert response.headers.get("header1") == "Value1"
    assert response.headers.get("header2") == "Value2"


async def test_echo_body(env):
    response = await env.SELF.fetch(
        "http://example.com/echo-body",
        method="POST",
        body="hello body",
    )
    assert response.status == 200
    text = await response.text()
    assert text == "hello body"


async def test_meta(env):
    response = await env.SELF.fetch("http://example.com/meta?foo=bar&baz=qux")
    assert response.status == 200
    import json

    payload = json.loads(await response.text())
    assert payload["method"] == "GET"
    assert payload["path"] == "/meta"
    assert payload["query"] == "foo=bar&baz=qux"
    assert payload["scheme"] == "http"
    assert payload["has_env"] is True


async def test_cookies(env):
    response = await env.SELF.fetch("http://example.com/cookies")
    assert response.status == 200
    # workerd folds repeated Set-Cookie into a comma list when read via get();
    # use getSetCookie() to recover the individual values.
    cookies = list(response.headers.getSetCookie())
    assert "a=1" in cookies
    assert "b=2" in cookies


async def test_streaming(env):
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


async def test_app_exception_is_raised(env):
    req = js.Request.new("http://example.com/crash-test")
    threw = False
    try:
        await wsgi.fetch(crash_app, req, env)
    except RuntimeError as e:
        threw = True
        assert "app crash before response for testing" in str(e)
    assert threw, "Expected RuntimeError to be raised from wsgi.fetch"
