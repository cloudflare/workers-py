import pytest
from _client import get_json


@pytest.mark.asyncio
async def test_paginator_basic_pages(django_asgi_app):
    for page, expected in (
        (1, {"has_next": True, "has_previous": False}),
        (3, {"has_next": True, "has_previous": True}),
        (5, {"has_next": False, "has_previous": True}),
    ):
        response, payload = await get_json(django_asgi_app, f"/paginate/?page={page}")

        assert response.status == 200
        assert len(payload["items"]) == 10
        assert payload["num_pages"] == 5
        for key, value in expected.items():
            assert payload[key] is value


@pytest.mark.asyncio
async def test_paginator_invalid_page(django_asgi_app):
    response, payload = await get_json(django_asgi_app, "/paginate/?page=abc")

    assert response.status == 200
    assert payload["page"] == 1
    assert len(payload["items"]) == 10


@pytest.mark.asyncio
async def test_paginator_out_of_range(django_asgi_app):
    response, payload = await get_json(django_asgi_app, "/paginate/?page=999")

    assert response.status == 200
    assert payload["page"] == payload["num_pages"] == 5
    assert payload["has_next"] is False
