import json

import pytest
from _client import fetch, get_json, post_json


@pytest.mark.asyncio
async def test_api_view_and_function_view(django_asgi_app):
    cases = [
        ("GET", "/drf/api-view/", None, 200, {"method": "GET", "query": {}}),
        (
            "GET",
            "/drf/api-view/?foo=bar",
            None,
            200,
            {"method": "GET", "query": {"foo": "bar"}},
        ),
        (
            "POST",
            "/drf/api-view/",
            {"key": "val"},
            201,
            {"method": "POST", "data": {"key": "val"}},
        ),
        ("PUT", "/drf/api-view/", {"updated": True}, 200, None),
        ("DELETE", "/drf/api-view/", None, 204, None),
        (
            "GET",
            "/drf/function-view/",
            None,
            200,
            {"message": "hello from function view"},
        ),
        (
            "POST",
            "/drf/function-view/",
            {"hello": "world"},
            201,
            {"received": {"hello": "world"}},
        ),
    ]

    for method, path, data, status, expected in cases:
        if method == "GET":
            response, payload = await get_json(django_asgi_app, path)
        elif method == "DELETE":
            response = await fetch(django_asgi_app, path, method=method)
            payload = None
        elif method == "PUT":
            response = await fetch(
                django_asgi_app,
                path,
                method=method,
                headers={"Content-Type": "application/json"},
                body=json.dumps(data),
            )
            payload = json.loads(await response.text())
        else:
            response = await post_json(django_asgi_app, path, data)
            payload = json.loads(await response.text())
        assert response.status == status
        if expected is not None:
            assert payload == expected
        if path == "/drf/api-view/" and method == "PUT":
            assert isinstance(payload, dict)
            assert payload["method"] == "PUT"


@pytest.mark.asyncio
async def test_method_not_allowed(django_asgi_app):
    response = await fetch(django_asgi_app, "/drf/function-view/", method="PATCH")

    assert response.status == 405
