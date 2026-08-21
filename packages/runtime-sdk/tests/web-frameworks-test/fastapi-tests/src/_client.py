import json as _json

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
