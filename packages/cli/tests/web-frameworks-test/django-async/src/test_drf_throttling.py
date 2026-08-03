import json

import pytest
from _client import fetch


@pytest.mark.asyncio
async def test_throttle_behavior(django_asgi_app):
    await fetch(django_asgi_app, "/cache/clear/")
    responses = [await fetch(django_asgi_app, "/drf/throttled/") for _ in range(4)]
    payload = json.loads(await responses[3].text())

    assert [response.status for response in responses[:3]] == [200, 200, 200]
    assert responses[3].status == 429
    assert responses[3].headers.get("Retry-After")
    assert "detail" in payload
