import json as _json

import js
from pyodide.ffi import create_proxy, to_js

import asgi
from workers import Request

BASE_URL = "http://testserver"


def _with_content_length(headers, body):
    """Ensure Content-Length is present when a body is provided."""
    hdrs = dict(headers or {})
    if body is not None and not any(k.lower() == "content-length" for k in hdrs):
        length = len(body.encode() if isinstance(body, str) else body)
        hdrs["Content-Length"] = str(length)
    return hdrs


async def fetch(app, path, env=None, method="GET", headers=None, body=None):
    request = Request(
        f"{BASE_URL}{path}",
        method=method,
        headers=_with_content_length(headers, body),
        body=body,
    )
    return await asgi.fetch(app, request, env or {})


async def read_json(response):
    text = await response.text()
    return _json.loads(text) if text else None


async def get_json(app, path, **kwargs):
    response = await fetch(app, path, **kwargs)
    return response, await read_json(response)


async def post_json(app, path, data, **kwargs):
    return await fetch(
        app,
        path,
        method="POST",
        headers={"Content-Type": "application/json"},
        body=_json.dumps(data),
        **kwargs,
    )


def build_multipart_bytes(files, boundary="----WebTestBoundary"):
    """Build a binary-safe multipart body from (name, filename, bytes) tuples."""
    body = bytearray()
    for name, filename, content in files:
        if isinstance(content, str):
            content = content.encode()
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
        body.extend(content)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


async def fetch_chunks(app, path, chunks, env=None, method="POST", headers=None):
    """Send a request body as a JS ReadableStream with explicit chunk boundaries."""
    from js import Object

    chunks = list(chunks)

    def start(controller):
        for chunk in chunks:
            controller.enqueue(to_js(chunk))
        controller.close()

    start_proxy = create_proxy(start)
    try:
        stream = js.ReadableStream.new(
            to_js({"start": start_proxy}, dict_converter=Object.fromEntries)
        )
        hdrs = dict(headers or {})
        hdrs.setdefault("Content-Length", str(sum(len(chunk) for chunk in chunks)))
        request = Request(
            f"{BASE_URL}{path}",
            method=method,
            headers=hdrs,
            body=stream,
        )
        return await asgi.fetch(app, request, env or {})
    finally:
        start_proxy.destroy()


def build_multipart(files, boundary="----WebTestBoundary"):
    """Build a multipart/form-data body from a list of (name, filename, content) tuples."""
    lines = []
    for name, filename, content in files:
        if isinstance(content, bytes):
            content = content.decode()
        lines.append(f"--{boundary}")
        lines.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'
        )
        lines.append("Content-Type: application/octet-stream")
        lines.append("")
        lines.append(content)
    lines.append(f"--{boundary}--")
    lines.append("")
    body = "\r\n".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type
