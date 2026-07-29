import json as _json

import asgi
from workers import Request

BASE_URL = "http://testserver"


async def fetch(app, path, env=None, method="GET", headers=None, body=None):
    request = Request(
        f"{BASE_URL}{path}",
        method=method,
        headers=dict(headers or {}),
        body=body,
    )
    return await asgi.fetch(app, request, env or {})


async def read_json(response):
    text = await response.text()
    return _json.loads(text) if text else None


async def get_json(app, path, **kwargs):
    response = await fetch(app, path, **kwargs)
    return response, await read_json(response)
