import asyncio
import contextvars
import os
from urllib.parse import parse_qs

from pyodide.ffi import run_sync
from testlib.entrypoint import run_pytest

from workers import WorkerEntrypoint, wsgi

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


def streaming_app_stack_switch(environ, start_response):
    """WSGI app that returns multiple body chunks via a generator."""
    start_response("200 OK", [("Content-Type", "application/octet-stream")])

    def generate():
        for i in range(STREAMING_NUM_CHUNKS):
            run_sync(asyncio.sleep(0))
            yield bytes([i % 256]) * STREAMING_CHUNK_SIZE

    return generate()


REQUEST_VALUE: contextvars.ContextVar[str] = contextvars.ContextVar("request_value")
# Outcome of resetting REQUEST_VALUE when each response generator closes, keyed
# by request value: "ok", or the repr of the exception raised by reset().
CONTEXTVAR_CLOSE_RESULTS: dict[str, list[str]] = {}


def contextvar_streaming_app(environ, start_response):
    """WSGI app whose body generator depends on a ContextVar set by the app.

    Mirrors what Flask's ``stream_with_context`` does: state set in a ContextVar
    while the app runs must stay visible while the body is iterated, and the
    token must be reset in the same context when the iterable is closed.
    """
    value = parse_qs(environ["QUERY_STRING"])["value"][0]
    token = REQUEST_VALUE.set(value)
    start_response("200 OK", [("Content-Type", "text/plain")])

    def generate():
        try:
            yield b"value:"
            for _ in range(STREAMING_NUM_CHUNKS):
                run_sync(asyncio.sleep(0))
                yield REQUEST_VALUE.get().encode()
        finally:
            try:
                REQUEST_VALUE.reset(token)
                result = "ok"
            except Exception as exc:  # noqa: BLE001 - recorded for the test
                result = repr(exc)
            CONTEXTVAR_CLOSE_RESULTS.setdefault(value, []).append(result)

    return generate()


def crash_app(environ, start_response):
    raise RuntimeError("app crash before response for testing")


example_hdr = {"Header1": "Value1", "Header2": "Value2"}


class Default(WorkerEntrypoint):
    # Each path in this handler serves one of the WSGI apps above; the
    # assertions live in tests/test_wsgi.py.
    async def fetch(self, request):
        from js import URL

        url = URL.new(request.url)
        path = url.pathname

        app = {
            "/echo-body": echo_body_app,
            "/meta": echo_meta_app,
            "/cookies": cookies_app,
            "/stream": streaming_app,
            "/stream-stack-switch": streaming_app_stack_switch,
            "/stream-contextvar": contextvar_streaming_app,
        }.get(path, header_echo_app)

        return await wsgi.fetch(app, request, self.env)

    async def test(self, ctrl):
        os.chdir("/session/metadata/tests")
        args = [".", "-vv"]
        if self.env.color:
            args.append("--color=yes")
        run_pytest(args)
