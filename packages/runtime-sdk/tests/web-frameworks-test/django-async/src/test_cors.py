import pytest
from _client import fetch

ORIGIN_HEADER = "Access-Control-Allow-Origin"
CREDENTIALS_HEADER = "Access-Control-Allow-Credentials"


@pytest.mark.asyncio
async def test_cors_allowed_origins(django_asgi_app):
    cases = (
        ("OPTIONS", "http://localhost:3000", True),
        ("GET", "https://example.com", False),
        ("GET", "https://sub.example.com", False),
        ("GET", "http://localhost:3000", True),
    )
    for method, origin, with_credentials in cases:
        headers = {"Origin": origin}
        if method == "OPTIONS":
            headers["Access-Control-Request-Method"] = "GET"
        response = await fetch(
            django_asgi_app, "/hello/", method=method, headers=headers
        )

        assert response.headers.get(ORIGIN_HEADER) == origin
        if with_credentials:
            assert response.headers.get(CREDENTIALS_HEADER) == "true"


@pytest.mark.asyncio
async def test_cors_disallowed_origin(django_asgi_app):
    response = await fetch(
        django_asgi_app,
        "/hello/",
        method="OPTIONS",
        headers={"Origin": "http://evil.com", "Access-Control-Request-Method": "GET"},
    )

    assert not response.headers.has(ORIGIN_HEADER)


@pytest.mark.asyncio
async def test_cors_no_origin_no_headers(django_asgi_app):
    response = await fetch(django_asgi_app, "/hello/")

    assert not response.headers.has(ORIGIN_HEADER)
    assert not response.headers.has(CREDENTIALS_HEADER)
