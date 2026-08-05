import pytest
from _client import fetch, is_wsgi


def _streaming_paths(app):
    if is_wsgi(app):
        return ("/stream/sync-gen/",)
    return ("/stream/async-gen/", "/stream/sync-gen/")


@pytest.mark.asyncio
async def test_streaming_generators(django_app):
    for path in _streaming_paths(django_app):
        response = await fetch(django_app, path)
        body = await response.text()

        assert response.status == 200
        for index in range(5):
            assert f"chunk-{index}" in body


@pytest.mark.asyncio
async def test_streaming_content_type(django_app):
    response = await fetch(django_app, _streaming_paths(django_app)[0])

    assert response.status == 200
    assert response.headers.get("Content-Type") is not None
    assert response.headers.get("Content-Type").startswith("text/plain")
