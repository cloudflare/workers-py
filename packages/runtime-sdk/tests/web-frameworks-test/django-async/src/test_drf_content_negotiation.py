import json

import pytest
from _client import post_form, post_json


@pytest.mark.asyncio
async def test_content_negotiation_cases(django_asgi_app):
    json_data = {"name": "widget", "quantity": 2}
    response = await post_json(django_asgi_app, "/drf/content/", json_data)
    payload = json.loads(await response.text())

    assert response.status == 200
    assert payload == {"content_type": "application/json", "data": json_data}
    assert "application/json" in (response.headers.get("Content-Type") or "")

    response = await post_form(
        django_asgi_app,
        "/drf/content/",
        "name=widget&quantity=2",
    )
    payload = json.loads(await response.text())

    assert response.status == 200
    assert payload["content_type"] == "application/x-www-form-urlencoded"
    assert payload["data"]["name"] == "widget"
    assert payload["data"]["quantity"] == "2"

    response = await post_json(django_asgi_app, "/drf/content/", {"ping": "pong"})

    assert response.status == 200
    assert "application/json" in (response.headers.get("Content-Type") or "")

    response = await post_form(
        django_asgi_app,
        "/drf/content/",
        "<root></root>",
        headers={"Content-Type": "text/xml"},
    )

    assert response.status == 415
