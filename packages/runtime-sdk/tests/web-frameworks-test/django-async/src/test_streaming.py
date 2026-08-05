import pytest
from _client import fetch


@pytest.mark.asyncio
async def test_streaming_generators(django_asgi_app):
    for path in ("/stream/async-gen/", "/stream/sync-gen/"):
        response = await fetch(django_asgi_app, path)
        body = await response.text()

        assert response.status == 200
        for index in range(5):
            assert f"chunk-{index}" in body


@pytest.mark.asyncio
async def test_streaming_content_type(django_asgi_app):
    response = await fetch(django_asgi_app, "/stream/async-gen/")

    assert response.status == 200
    assert response.headers.get("Content-Type") is not None
    assert response.headers.get("Content-Type").startswith("text/plain")
