"""FastAPI lifecycle tests targeting the Workers ASGI streaming boundary."""

import asyncio

import pytest
from _client import fetch, get_json
from worker import (
    _platform_events,
    _platform_shutdown_complete,
    reset_platform_events,
)


@pytest.mark.asyncio
async def test_lifespan_state_reaches_request(fastapi_app):
    """State yielded by FastAPI's lifespan context is copied to HTTP scopes."""
    resp, data = await get_json(fastapi_app, "/platform/lifespan-state")
    assert resp.status == 200
    assert data == {"available": True, "closed": False}


@pytest.mark.asyncio
async def test_stream_finishes_before_cleanup_and_shutdown(fastapi_app):
    """Streaming, background work, and dependency cleanup precede shutdown."""
    reset_platform_events()

    resp = await asyncio.wait_for(
        fetch(fastapi_app, "/platform/lifecycle-stream"), timeout=5
    )
    assert resp.status == 200
    assert await asyncio.wait_for(resp.text(), timeout=5) == (
        "chunk-0\nchunk-1\nchunk-2\n"
    )
    await asyncio.wait_for(_platform_shutdown_complete.wait(), timeout=5)

    assert _platform_events == [
        "lifespan-startup",
        "dependency-open",
        "handler",
        "chunk-0",
        "chunk-1",
        "chunk-2",
        "background-task",
        "dependency-close",
        "lifespan-shutdown",
    ]
