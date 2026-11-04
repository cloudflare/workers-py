import asyncio

import js
import pytest
from flask import (
    Flask,
    Response,
    has_request_context,
    request,
    stream_with_context,
)

from workers import wsgi

app = Flask(__name__)
# Request values whose stream_with_context generator has run its cleanup.
closed: list[str] = []


@app.get("/stream")
def stream():
    @stream_with_context
    def body():
        value = request.args["value"]
        try:
            yield "flask:"
            yield request.args["value"]
        finally:
            closed.append(value)

    return Response(body(), content_type="text/plain")


async def fetch(value):
    req = js.Request.new(f"http://example.com/stream?value={value}")
    return await wsgi.fetch(app, req, {})


@pytest.fixture(autouse=True)
def clear_closed():
    closed.clear()


@pytest.mark.asyncio
async def test_stream_with_context():
    response = await fetch("stream-body")
    assert response.status == 200
    # The request context pushed while priming the body must stay in the
    # response's own context instead of leaking into the caller's.
    assert not has_request_context()
    assert await response.text() == "flask:stream-body"
    assert closed == ["stream-body"]


@pytest.mark.asyncio
async def test_concurrent_stream_with_context():
    responses = await asyncio.gather(fetch("first"), fetch("second"))
    bodies = await asyncio.gather(*(response.text() for response in responses))
    assert bodies == ["flask:first", "flask:second"]
    assert sorted(closed) == ["first", "second"]


@pytest.mark.asyncio
async def test_cancelled_stream_with_context():
    response = await fetch("cancel")
    reader = response.body.getReader()
    first = await reader.read()
    assert first.value.to_bytes() == b"flask:"
    await reader.cancel()
    assert closed == ["cancel"]
