import asyncio
import os
import sys

import pytest
from pyodide.ffi import run_sync
from pyodide.webloop import WebLoop

from workers import WorkerEntrypoint, wsgi


async def noop(*args):
    pass


# pytest-asyncio relies on these but in Pyodide < 0.29 WebLoop does not implement them
WebLoop.shutdown_asyncgens = noop
WebLoop.shutdown_default_executor = noop

# Pyodide 0.26.0a2's _cancel_all_tasks calls task.exception() on pending tasks,
# which raises InvalidStateError under Pyodide's WebLoop.
# Ignore this error to prevent pytest-asyncio from crashing.
if sys.version_info < (3, 13):
    asyncio.runners._cancel_all_tasks = lambda loop: None  # type: ignore[attr-defined]


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
        }.get(path, header_echo_app)

        return await wsgi.fetch(app, request, self.env)

    async def test(self, ctrl):
        os.chdir("/session/metadata/tests")
        args = [".", "-vv"]
        if self.env.color:
            args.append("--color=yes")
        assert pytest.main(args) == 0
