# pyright: reportMissingImports=false

import json as _json

import asgi as _asgi
from workers import Request

BASE_URL = "http://testserver"


def _with_content_length(headers, body):
    hdrs = dict(headers or {})
    if body is not None and not any(key.lower() == "content-length" for key in hdrs):
        length = len(body.encode() if isinstance(body, str) else body)
        hdrs["Content-Length"] = str(length)
    return hdrs


async def fetch(app, path, *, method="GET", headers=None, body=None, env=None):
    request = Request(
        f"{BASE_URL}{path}",
        method=method,
        headers=_with_content_length(headers, body),
        body=body,
    )
    return await _asgi.fetch(app, request, {} if env is None else env)


async def read_json(response):
    text = await response.text()
    return _json.loads(text) if text else None


async def get_json(app, path, **kwargs):
    response = await fetch(app, path, **kwargs)
    return response, await read_json(response)
