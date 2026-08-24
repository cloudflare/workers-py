# pyright: reportMissingImports=false

import json as _json

from _django_app import django_wsgi_app
from workers import Request

from django_cf import handle_wsgi

BASE_URL = "http://testserver"


async def fetch(path, *, env=None):
    request = Request(f"{BASE_URL}{path}")
    return await handle_wsgi(request, django_wsgi_app(), {} if env is None else env)


async def read_json(response):
    text = await response.text()
    return _json.loads(text) if text else None


async def get_json(path, **kwargs):
    response = await fetch(path, **kwargs)
    return response, await read_json(response)
