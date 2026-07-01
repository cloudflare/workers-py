import io
import logging
import sys
from typing import Any
from urllib.parse import unquote

import js

from workers import Context, Request

logger = logging.getLogger("wsgi")


def _wsgi_native_string(value: str) -> str:
    """Convert a (possibly non-ASCII) Python ``str`` into a WSGI "native string".

    PEP 3333 requires that strings handed to a WSGI application use the
    bytes-in-unicode convention: the string contains characters whose code
    points correspond to the raw bytes (i.e. it is decoded with ``latin-1``).
    Frameworks such as Werkzeug/Flask undo this by re-encoding with ``latin-1``
    and decoding with ``utf-8``.
    """
    return value.encode("utf-8").decode("latin-1")


class _ReadableStreamInput(io.RawIOBase):
    """A blocking, file-like ``wsgi.input`` backed by an async ``ReadableStream``.

    WSGI apps read the request body synchronously, but the Workers body is an
    async ``ReadableStream``. We bridge the two lazily using Pyodide's
    ``run_sync`` (JSPI stack switching): each ``readinto`` pulls only as much
    from the stream as the application asks for, so the body is never fully
    buffered up-front.

    This only works while a JSPI suspender is on the stack, which is the case
    here because the WSGI app runs synchronously inside the async ``fetch``
    handler. Callers must gate construction on :func:`_can_stream`.
    """

    def __init__(self, js_body: "js.ReadableStream") -> None:
        self._reader = js_body.getReader()
        self._buf = bytearray()
        self._eof = False

    def readable(self) -> bool:
        return True

    def _fill(self) -> None:
        from pyodide.ffi import run_sync

        while not self._buf and not self._eof:
            result = run_sync(self._reader.read())
            if result.done:
                self._eof = True
            elif result.value is not None:
                self._buf.extend(result.value.to_bytes())

    def readinto(self, b) -> int:
        self._fill()
        if not self._buf:
            return 0
        n = min(len(b), len(self._buf))
        b[:n] = self._buf[:n]
        del self._buf[:n]
        return n

    def close(self) -> None:
        if not self.closed:
            try:
                self._reader.releaseLock()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
        super().close()


def _can_stream() -> bool:
    """Return True if we can lazily stream the body via run_sync"""
    try:
        from pyodide.ffi import can_run_sync
    except ImportError:
        return False
    return can_run_sync()


def _make_wsgi_input(req: "Request | js.Request") -> "io.BufferedIOBase | None":
    """Build a lazy, stream-backed ``wsgi.input`` if the runtime supports it.

    Returns ``None`` when lazy streaming is unavailable, signalling the caller
    to fall back to pre-buffering the body.
    """
    if not _can_stream():
        return None
    if not req.body:
        return io.BytesIO(b"")
    # `req.body` is a JS ReadableStream for both workers.Request and js.Request.
    return io.BufferedReader(_ReadableStreamInput(req.body))


async def _read_body(req: "Request | js.Request") -> bytes:
    """Read the entire request body into memory (fallback when streaming is off)."""
    if not req.body:
        return b""
    chunks = [data.to_bytes() async for data in req.body]
    return b"".join(chunks)


def build_environ(
    req: "Request | js.Request",
    env: Any,
    body: "bytes | io.IOBase",
) -> dict[str, Any]:
    from js import URL

    # `body` may be raw bytes or a file-like `wsgi.input` stream
    if isinstance(body, (bytes, bytearray)):
        wsgi_input: Any = io.BytesIO(body)
        content_length_fallback: int | None = len(body)
    else:
        wsgi_input = body
        content_length_fallback = None

    req_headers = req.headers.items() if isinstance(req, Request) else req.headers

    url = URL.new(req.url)
    assert url.protocol[-1] == ":"
    scheme = url.protocol[:-1]

    # PATH_INFO is the URL-decoded path expressed as a WSGI native string.
    path_info = _wsgi_native_string(unquote(url.pathname))
    # QUERY_STRING stays percent-encoded per the spec.
    assert "?".startswith(url.search[0:1])
    query_string = url.search[1:]

    server_port = url.port or ("443" if scheme == "https" else "80")

    method = req.method
    # `workers.Request.method` is an `http.HTTPMethod` (a str subclass); coerce
    # to a plain string so frameworks comparing against literals behave.
    method = str(method.value) if hasattr(method, "value") else str(method)

    environ: dict[str, Any] = {
        "REQUEST_METHOD": method,
        "SCRIPT_NAME": "",
        "PATH_INFO": path_info,
        "QUERY_STRING": query_string,
        "SERVER_NAME": url.hostname or "localhost",
        "SERVER_PORT": str(server_port),
        "SERVER_PROTOCOL": "HTTP/1.1",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": scheme,
        "wsgi.input": wsgi_input,
        "wsgi.errors": sys.stderr,
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        # Cloudflare-specific extension so handlers can reach bindings, mirroring
        # the `scope["env"]` convention used by asgi.py.
        "workers.env": env,
    }

    for key, value in req_headers:
        name = key.upper().replace("-", "_")
        if name in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            environ[name] = value
        else:
            http_name = "HTTP_" + name
            if http_name in environ:
                # Repeated headers are folded into a single comma-separated value.
                environ[http_name] += "," + value
            else:
                environ[http_name] = value

    # Only synthesize CONTENT_LENGTH when the body was pre-buffered; when
    # streaming lazily we don't know the length without consuming it.
    if "CONTENT_LENGTH" not in environ and content_length_fallback:
        environ["CONTENT_LENGTH"] = str(content_length_fallback)

    return environ


def _make_js_response(status: str, headers: list, body: bytes) -> js.Response:
    from js import Headers, Response
    from pyodide.ffi import create_proxy

    # WSGI status is e.g. "200 OK"; split into code + reason phrase.
    code_str, _, reason = status.partition(" ")
    status_code = int(code_str)

    js_headers = Headers.new()
    for key, value in headers:
        # `append` (not `set`) preserves repeated headers such as Set-Cookie.
        js_headers.append(key, value)

    options = {"status": status_code, "headers": js_headers}
    if reason:
        options["statusText"] = reason

    if not body:
        return Response.new(None, **options)

    px = create_proxy(body)
    buf = px.getBuffer()
    px.destroy()
    try:
        return Response.new(buf.data, **options)
    finally:
        buf.release()


def process_request(
    app: Any,
    req: "Request | js.Request",
    env: Any,
    body: "bytes | io.IOBase",
) -> js.Response:
    environ = build_environ(req, env, body)

    response_state: dict[str, Any] = {"status": None, "headers": None}
    # Buffer used only for the legacy `write()` callable; modern apps (Flask,
    # Werkzeug, Django) return an iterable instead and never touch this.
    write_buffer: list[bytes] = []

    def write(chunk: bytes) -> None:
        if response_state["status"] is None:
            raise AssertionError("write() called before start_response()")
        write_buffer.append(chunk)

    def start_response(status, response_headers, exc_info=None):
        if exc_info is not None:
            try:
                if response_state["status"] is not None:
                    # Headers were already sent; re-raise the original error.
                    raise exc_info[1].with_traceback(exc_info[2])
            finally:
                exc_info = None
        elif response_state["status"] is not None:
            raise AssertionError("start_response() called more than once")

        response_state["status"] = status
        response_state["headers"] = list(response_headers)
        return write

    result = app(environ, start_response)
    try:
        body_chunks = list(write_buffer)
        body_chunks.extend(chunk for chunk in result if chunk)
    finally:
        # PEP 3333: if the iterable has a close() method, the server must call it.
        close = getattr(result, "close", None)
        if close is not None:
            close()

    if response_state["status"] is None:
        raise RuntimeError("The WSGI application did not call start_response()")

    return _make_js_response(
        response_state["status"], response_state["headers"], b"".join(body_chunks)
    )


async def fetch(
    app: Any,
    req: "Request | js.Request",
    env: Any,
    # Accepted for parity with asgi.fetch; WSGI has no use for it.
    ctx: Context | None = None,
) -> js.Response:
    logger.debug("WSGI request: %s %s", req.method, req.url)
    # Prefer lazily streaming the body through `wsgi.input` (no full buffering);
    # fall back to pre-buffering when `run_sync`/JSPI isn't available.
    body: "bytes | io.IOBase | None" = _make_wsgi_input(req)
    if body is None:
        body = await _read_body(req)
    try:
        return process_request(app, req, env, body)
    except Exception:
        logger.exception("WSGI request failed")
        raise
