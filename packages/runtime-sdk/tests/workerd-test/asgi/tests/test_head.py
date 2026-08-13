import pytest

import asgi
from workers import Request, env


class _HeadBodyDrainApp:
    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            return
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"content-length", b"11"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"hello ", "more_body": True})
        await send({"type": "http.response.body", "body": b"world"})


@pytest.mark.asyncio
async def test_head_response_body_is_drained_and_suppressed():
    app = _HeadBodyDrainApp()

    get_response = await asgi.fetch(
        app, Request("http://example.com/head-body", method="GET"), env
    )
    assert get_response.status == 200
    assert get_response.headers["content-type"] == "text/plain"
    assert get_response.headers["content-length"] == "11"
    assert await get_response.text() == "hello world"

    head_response = await asgi.fetch(
        app, Request("http://example.com/head-body", method="HEAD"), env
    )
    assert head_response.status == 200
    assert head_response.headers["content-type"] == "text/plain"
    assert head_response.headers["content-length"] == "11"
    assert await head_response.text() == ""
