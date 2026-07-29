import pytest
from _client import get_json, post_json, read_json


@pytest.mark.asyncio
async def test_cache_set_and_get(django_asgi_app):
    response = await post_json(
        django_asgi_app, "/cache/set/", {"key": "k1", "value": "v1"}
    )
    assert response.status == 200
    assert await read_json(response) == {"cached": True, "key": "k1", "value": "v1"}

    response, payload = await get_json(django_asgi_app, "/cache/get/?key=k1")
    assert response.status == 200
    assert payload == {"key": "k1", "value": "v1"}


@pytest.mark.asyncio
async def test_cache_delete_and_missing(django_asgi_app):
    await post_json(
        django_asgi_app, "/cache/set/", {"key": "delete-key", "value": "delete-value"}
    )
    response, payload = await get_json(django_asgi_app, "/cache/delete/?key=delete-key")
    assert response.status == 200
    assert payload == {"deleted": True, "key": "delete-key"}

    response, payload = await get_json(django_asgi_app, "/cache/get/?key=delete-key")
    assert response.status == 200
    assert payload == {"key": "delete-key", "value": None}

    response, payload = await get_json(django_asgi_app, "/cache/get/?key=nonexistent")
    assert response.status == 200
    assert payload == {"key": "nonexistent", "value": None}


@pytest.mark.asyncio
async def test_cache_clear(django_asgi_app):
    for key, value in (("clear-key-1", "value-1"), ("clear-key-2", "value-2")):
        await post_json(django_asgi_app, "/cache/set/", {"key": key, "value": value})

    response, payload = await get_json(django_asgi_app, "/cache/clear/")
    assert response.status == 200
    assert payload["cleared"] is True

    for key in ("clear-key-1", "clear-key-2"):
        response, payload = await get_json(django_asgi_app, f"/cache/get/?key={key}")
        assert response.status == 200
        assert payload == {"key": key, "value": None}


@pytest.mark.asyncio
async def test_cache_overwrite(django_asgi_app):
    await post_json(
        django_asgi_app, "/cache/set/", {"key": "overwrite-key", "value": "value-1"}
    )
    await post_json(
        django_asgi_app, "/cache/set/", {"key": "overwrite-key", "value": "value-2"}
    )

    response, payload = await get_json(django_asgi_app, "/cache/get/?key=overwrite-key")
    assert response.status == 200
    assert payload == {"key": "overwrite-key", "value": "value-2"}
