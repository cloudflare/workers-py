import json

import pytest
from _client import get_json, post_json


@pytest.mark.asyncio
async def test_serializer_and_nested_cases(django_asgi_app):
    serializer_cases = [
        (
            {"name": "widget", "price": 9.99, "quantity": 3},
            True,
            lambda payload: (
                payload["data"]["name"] == "widget"
                and float(payload["data"]["price"]) == pytest.approx(9.99)
                and payload["data"]["quantity"] == 3
            ),
        ),
        (
            {"name": "widget"},
            False,
            lambda payload: "price" in payload["errors"]
            and "quantity" in payload["errors"],
        ),
        (
            {"name": "invalid", "price": 9.99, "quantity": 1},
            False,
            lambda payload: "name" in payload["errors"],
        ),
        (
            {"name": "bulk", "price": 1500, "quantity": 200},
            False,
            lambda payload: "bulk order too large" in str(payload["errors"]).lower(),
        ),
    ]

    for data, valid, check in serializer_cases:
        response = await post_json(django_asgi_app, "/drf/serializer/", data)
        payload = json.loads(await response.text())
        assert payload["valid"] is valid
        assert check(payload)

    response, payload = await get_json(django_asgi_app, "/drf/serializer/")
    assert response.status == 200
    assert "name" in payload
    assert "price" in payload
    assert "quantity" in payload

    nested_cases = [
        (
            {"customer_name": "Alice", "items": [{"product": "A", "quantity": 2}]},
            True,
            lambda payload: payload["data"]["customer_name"] == "Alice"
            and payload["data"]["items"][0]["product"] == "A"
            and payload["data"]["items"][0]["quantity"] == 2,
        ),
        (
            {"customer_name": "Bob", "items": []},
            False,
            lambda payload: "items" in payload["errors"],
        ),
    ]

    for data, valid, check in nested_cases:
        response = await post_json(django_asgi_app, "/drf/nested/", data)
        payload = json.loads(await response.text())
        assert payload["valid"] is valid
        assert check(payload)
