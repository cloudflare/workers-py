import pytest
from _client import get_json


@pytest.mark.asyncio
async def test_sync_to_async(django_asgi_app):
    response, payload = await get_json(django_asgi_app, "/async/sync-to-async/")

    assert response.status == 200
    assert payload["result"] == "sync result"


@pytest.mark.asyncio
async def test_async_iterator(django_asgi_app):
    response, payload = await get_json(django_asgi_app, "/async/async-iter/")

    assert response.status == 200
    assert payload["items"]
    assert payload["items"] == [0, 1, 2, 3, 4]
