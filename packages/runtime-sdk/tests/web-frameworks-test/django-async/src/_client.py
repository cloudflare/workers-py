import json as _json

import asgi
from workers import Request

BASE_URL = "http://testserver"


# Django uses content-length header when handling request body.
# Ensure content-length header is set when body is provided.
# Note that this is required only for testing as we build requests manually.
# In real HTTP requests, the browser sets the content-length header automatically.
def _with_content_length(headers, body):
    hdrs = dict(headers or {})
    if body is not None and not any(k.lower() == "content-length" for k in hdrs):
        length = len(body.encode() if isinstance(body, str) else body)
        hdrs["Content-Length"] = str(length)
    return hdrs


async def fetch(app, path, method="GET", headers=None, body=None):
    request = Request(
        f"{BASE_URL}{path}",
        method=method,
        headers=_with_content_length(headers, body),
        body=body,
    )
    return await asgi.fetch(app, request, {})


async def read_json(response):
    text = await response.text()
    return _json.loads(text) if text else None


async def get_json(app, path, **kwargs):
    response = await fetch(app, path, **kwargs)
    return response, await read_json(response)


async def post_json(app, path, data, headers=None, **kwargs):
    return await fetch(
        app,
        path,
        method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
        body=_json.dumps(data),
        **kwargs,
    )


async def post_form(app, path, body, headers=None, **kwargs):
    return await fetch(
        app,
        path,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            **(headers or {}),
        },
        body=body,
        **kwargs,
    )


def build_multipart(files, boundary="----WebTestBoundary"):
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


def cookie_value(header_value, name):
    if not header_value:
        return None
    for part in header_value.split(","):
        candidate = part.strip().split(";", 1)[0]
        if candidate.startswith(f"{name}="):
            return candidate.split("=", 1)[1]
    return None
