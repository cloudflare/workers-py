import json

import pytest
from _client import get_json


@pytest.mark.asyncio
async def test_signal_send_and_data_received(django_asgi_app):
    response, payload = await get_json(django_asgi_app, "/signals/send/")

    assert response.status == 200
    assert payload["sent"] is True
    assert payload["received"]
    assert any("test" in json.dumps(item) for item in payload["received"])


@pytest.mark.asyncio
async def test_signal_robust(django_asgi_app):
    response, payload = await get_json(django_asgi_app, "/signals/robust/")

    assert response.status == 200
    assert payload["sent"] is True
    assert payload["results"]


@pytest.mark.asyncio
async def test_signal_multiple_calls(django_asgi_app):
    first_response, first_payload = await get_json(django_asgi_app, "/signals/send/")
    second_response, second_payload = await get_json(django_asgi_app, "/signals/send/")

    assert first_response.status == 200
    assert second_response.status == 200
    assert len(second_payload["received"]) >= len(first_payload["received"])
