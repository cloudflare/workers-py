import pytest
from _client import fetch, post_json


@pytest.mark.asyncio
async def test_middleware_headers(django_asgi_app):
    for path in ("/hello/", "/echo-method/"):
        response = await fetch(django_asgi_app, path)

        assert response.status == 200
        assert response.headers.get("X-Custom-Middleware") == "applied"

    response = await fetch(django_asgi_app, "/hello/")

    assert response.status == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") is not None
    content_length = response.headers.get("Content-Length")
    assert content_length is None or int(content_length) >= 0


@pytest.mark.asyncio
async def test_session_middleware_cookie(django_asgi_app):
    response = await post_json(django_asgi_app, "/session/set/", {"color": "blue"})

    assert response.status == 200
    assert response.headers.get("Set-Cookie") is not None
