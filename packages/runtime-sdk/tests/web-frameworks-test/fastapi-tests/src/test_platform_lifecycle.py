"""FastAPI lifespan state tests targeting the Workers ASGI boundary."""

import pytest
from _client import get_json


@pytest.mark.asyncio
async def test_lifespan_state_reaches_request(fastapi_app):
    """State yielded by FastAPI's lifespan context is copied to HTTP scopes."""
    resp, data = await get_json(fastapi_app, "/platform/lifespan-state")
    assert resp.status == 200
    assert data == {"available": True, "closed": False}
