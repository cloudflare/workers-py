import pytest
from _client import fetch, get_json


@pytest.mark.asyncio
async def test_error_handlers(django_asgi_app):
    for path, status in (
        ("/trigger-404/", 404),
        ("/trigger-403/", 403),
        ("/trigger-400/", 400),
        ("/trigger-500/", 500),
    ):
        response, payload = await get_json(django_asgi_app, path)

        assert response.status == status
        assert isinstance(payload, dict)
        assert payload


@pytest.mark.asyncio
async def test_unmatched_404(django_asgi_app):
    response = await fetch(django_asgi_app, "/nonexistent-path-xyz/")

    assert response.status == 404


@pytest.mark.asyncio
async def test_error_response_is_json(django_asgi_app):
    response = await fetch(django_asgi_app, "/trigger-404/")

    assert response.status == 404
    assert "application/json" in (response.headers.get("Content-Type") or "")
