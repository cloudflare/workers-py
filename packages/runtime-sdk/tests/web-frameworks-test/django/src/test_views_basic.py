import json

import pytest
from _client import fetch, post_json


@pytest.mark.asyncio
async def test_simple_async_view(django_app):
    response = await fetch(django_app, "/hello/")

    assert response.status == 200
    assert await response.text() == "hello"


@pytest.mark.asyncio
async def test_status_codes(django_app):
    for path, status in (
        ("/status/201/", 201),
        ("/status/204/", 204),
        ("/status/404/", 404),
    ):
        response = await fetch(django_app, path)

        assert response.status == status


@pytest.mark.asyncio
async def test_echo_method(django_app):
    for method in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
        if method == "POST":
            response = await post_json(django_app, "/echo-method/", {"ok": True})
        else:
            response = await fetch(django_app, "/echo-method/", method=method)

        assert response.status == 200
        assert json.loads(await response.text()) == {"method": method}


@pytest.mark.asyncio
async def test_async_cbv_get(django_app):
    response = await fetch(django_app, "/cbv/")

    assert response.status == 200
    assert json.loads(await response.text()) == {"method": "GET"}


@pytest.mark.asyncio
async def test_async_cbv_post(django_app):
    response = await post_json(django_app, "/cbv/", {"hello": "world"})

    assert response.status == 200
    assert json.loads(await response.text()) == {"method": "POST"}


@pytest.mark.asyncio
async def test_head_request(django_app):
    response = await fetch(django_app, "/hello/", method="HEAD")

    assert response.status == 200
    assert response.headers.has("Content-Type")


@pytest.mark.asyncio
async def test_options_returns_allowed(django_app):
    response = await fetch(django_app, "/cbv/", method="OPTIONS")

    assert response.status == 200
    allow = response.headers.get("Allow")
    assert allow is not None
    assert "GET" in allow
    assert "POST" in allow
