import json

import pytest
from _client import fetch, get_json


@pytest.mark.asyncio
async def test_path_int_converter(django_asgi_app):
    for path, payload in (
        ("/items/42/", {"id": 42, "type": "int"}),
        ("/users/alice/", {"name": "alice"}),
        ("/posts/my-first-post/", {"slug": "my-first-post"}),
    ):
        response, data = await get_json(django_asgi_app, path)

        assert response.status == 200
        assert data == payload

    uid = "550e8400-e29b-41d4-a716-446655440000"
    response, payload = await get_json(django_asgi_app, f"/uuids/{uid}/")

    assert response.status == 200
    assert uid in json.dumps(payload)


@pytest.mark.asyncio
async def test_re_path(django_asgi_app):
    response, payload = await get_json(django_asgi_app, "/archive/2024/")

    assert response.status == 200
    assert payload == {"year": "2024"}


@pytest.mark.asyncio
async def test_include_namespace(django_asgi_app):
    response, payload = await get_json(django_asgi_app, "/api/v1/info/")

    assert response.status == 200
    assert payload == {"namespace": "api-v1"}


@pytest.mark.asyncio
async def test_reverse_url(django_asgi_app):
    response = await fetch(django_asgi_app, "/reverse-test/")

    assert response.status == 200
    assert "/hello/" in await response.text()


@pytest.mark.asyncio
async def test_unmatched_url_404(django_asgi_app):
    response = await fetch(django_asgi_app, "/nonexistent/")

    assert response.status == 404


@pytest.mark.asyncio
async def test_query_string_preserved(django_asgi_app):
    response, payload = await get_json(django_asgi_app, "/echo-query/?foo=bar&baz=qux")

    assert response.status == 200
    assert payload == {"foo": "bar", "baz": "qux"}


@pytest.mark.asyncio
async def test_path_basic(django_asgi_app):
    response = await fetch(django_asgi_app, "/hello/")

    assert response.status == 200
