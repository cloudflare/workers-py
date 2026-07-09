import io
import logging
import sys
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import unquote, urlsplit

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
    handler.
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
            self._release_reader()
        super().close()

    def __del__(self):
        self.close()

    def _release_reader(self) -> None:
        """Discard the request body and release the underlying reader.

        If the body was fully consumed we just release the lock. Otherwise we
        ``cancel()`` the reader to drop the remainder; ``cancel()`` returns a JS
        promise that the runtime settles on its own, so we don't await it.
        """
        from pyodide.ffi import run_sync

        try:
            if self._eof:
                self._reader.releaseLock()
            else:
                run_sync(self._reader.cancel())
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass


def _make_wsgi_input(req: "Request | js.Request") -> "io.BufferedIOBase | None":
    """Build a lazy, stream-backed ``wsgi.input`` if the runtime supports it.

    Returns ``None`` when lazy streaming is unavailable, signalling the caller
    to fall back to pre-buffering the body.
    """
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
    env: dict[str, Any],
    body: "bytes | io.IOBase",
) -> dict[str, Any]:
    # `body` may be raw bytes or a file-like `wsgi.input` stream
    if isinstance(body, (bytes, bytearray)):
        wsgi_input: Any = io.BytesIO(body)
        content_length_fallback: int | None = len(body)
    else:
        wsgi_input = body
        content_length_fallback = None

    req_headers = req.headers.items() if isinstance(req, Request) else req.headers

    url = urlsplit(req.url)
    scheme = url.scheme
    if not scheme:
        raise ValueError(f"Request URL is not absolute: {req.url!r}")

    # PATH_INFO is the URL-decoded path expressed as a WSGI native string.
    path_info = _wsgi_native_string(unquote(url.path or "/"))
    # QUERY_STRING stays percent-encoded per the spec.
    query_string = url.query

    server_port = str(url.port) if url.port else ("443" if scheme == "https" else "80")

    method = req.method
    # `workers.Request.method` is an `http.HTTPMethod` (a str subclass); coerce
    # to a plain string so frameworks comparing against literals behave.
    method = str(method.value) if hasattr(method, "value") else str(method)

    environ: dict[str, Any] = {
        "REQUEST_METHOD": method,
        "SCRIPT_NAME": "",
        "PATH_INFO": path_info,
        "QUERY_STRING": query_string,
        # A request URL is always absolute here, so hostname is populated; keep a
        # fallback since WSGI requires SERVER_NAME to be non-empty.
        "SERVER_NAME": url.hostname,
        "SERVER_PORT": server_port,
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


def _to_js_uint8array(chunk: bytes) -> "js.Uint8Array":
    """Copy Python ``bytes`` into a standalone, JS-owned ``Uint8Array``.

    A copy (rather than a view over the WASM heap) is required because
    ``ReadableStreamDefaultController.enqueue`` keeps the chunk by reference in
    the stream's internal queue until the consumer reads it later, by which
    point ``chunk`` has been released. ``to_js`` copies buffer data out of the
    heap into a fresh ``ArrayBuffer`` (pyodide's ``python2js_buffer``), so its
    result stays valid.
    """
    from pyodide.ffi import to_js

    return to_js(chunk)


def _close_iterable(iterable: Any) -> None:
    # PEP 3333: if the iterable has a close() method, the server must call it.
    close = getattr(iterable, "close", None)
    if close is not None:
        close()


# Sentinel marking exhaustion of the response body iterator.
_END = object()


def _make_streaming_response(
    status: str,
    headers: "list[tuple[str, str]]",
    chunks: "Iterator[bytes]",
    on_close: "Callable[[], None]",
) -> js.Response:
    """Build a ``js.Response`` whose body is pulled lazily from *chunks*.

    Uses a ``ReadableStream`` with a synchronous, pull-based source so response
    bytes are produced on demand as the client reads, instead of buffering the
    whole body in memory. ``on_close`` runs exactly once when the stream is
    exhausted, errored, or cancelled.
    """
    from js import Headers as JsHeaders
    from js import ReadableStream, Response
    from pyodide.ffi import create_proxy

    # WSGI status is e.g. "200 OK"; split into code + reason phrase.
    code_str, _, reason = status.partition(" ")
    options: dict[str, Any] = {"status": int(code_str)}
    if reason:
        options["statusText"] = reason

    js_headers = JsHeaders.new()
    for key, value in headers:
        # `append` (not `set`) preserves repeated headers such as Set-Cookie.
        js_headers.append(key, value)
    options["headers"] = js_headers

    proxies: list[Any] = []
    done = False

    def cleanup() -> None:
        nonlocal done
        if done:
            return
        done = True
        try:
            on_close()
        finally:
            for proxy in proxies:
                proxy.destroy()

    @create_proxy
    def pull(controller: Any) -> None:
        try:
            chunk = next(chunks, _END)
        except Exception as exc:  # noqa: BLE001 - forward app errors to the stream
            logger.exception("Exception while streaming WSGI response body")
            cleanup()
            controller.error(str(exc))
            return
        if chunk is _END:
            controller.close()
            cleanup()
            return
        controller.enqueue(_to_js_uint8array(chunk))

    @create_proxy
    def cancel(_reason: Any = None) -> None:
        cleanup()

    proxies = [pull, cancel]
    return Response.new(ReadableStream.new(pull=pull, cancel=cancel), **options)


def process_request(
    app: Any,
    req: "Request | js.Request",
    env: Any,
    body: "bytes | io.IOBase",
) -> js.Response:
    environ = build_environ(req, env, body)

    response_state: dict[str, Any] = {"status": None, "headers": None}
    # Output from the (rarely used) legacy `write()` callable. Modern frameworks
    # (Flask, Werkzeug, Django) return an iterable instead; when they do use
    # write(), that output is emitted before the iterable's chunks.
    write_chunks: list[bytes] = []

    def write(chunk: bytes) -> None:
        if response_state["status"] is None:
            raise AssertionError("write() called before start_response()")
        if chunk:
            write_chunks.append(chunk)

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
        response_state["headers"] = response_headers
        return write

    result = app(environ, start_response)
    result_iter = iter(result)

    def close_all() -> None:
        _close_iterable(result)
        try:
            environ["wsgi.input"].close()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            logger.exception("Failed to close wsgi.input")

    # WSGI apps must call start_response before yielding the first body chunk,
    # but some defer it until the first non-empty chunk is produced. Pull that
    # chunk now so status/headers are known before we construct the Response.
    try:
        first_chunk: Any = _END
        for chunk in result_iter:
            if chunk:
                first_chunk = chunk
                break
    except Exception:
        close_all()
        raise

    if response_state["status"] is None:
        close_all()
        raise RuntimeError("The WSGI application did not call start_response()")

    def body_chunks() -> "Iterator[bytes]":
        yield from write_chunks
        if first_chunk is not _END:
            yield first_chunk
        for chunk in result_iter:
            if chunk:
                yield chunk

    return _make_streaming_response(
        response_state["status"], response_state["headers"], body_chunks(), close_all
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
    body: bytes | io.IOBase | None = _make_wsgi_input(req)
    if body is None:
        body = await _read_body(req)
    try:
        return process_request(app, req, env, body)
    except Exception:
        logger.exception("WSGI request failed")
        raise
