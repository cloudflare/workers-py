"""Tests across the FastAPI, Pyodide, and Workers runtime boundaries."""

import asyncio
import gzip
import hashlib
import json

import pytest
from _client import fetch, fetch_chunks, read_json
from worker import reset_platform_concurrency


@pytest.mark.asyncio
async def test_chunked_js_stream_preserves_utf8_and_boundaries(fastapi_app):
    """A JS ReadableStream survives the JS-to-Python ASGI receive bridge."""
    value = {
        "message": "worker \u0063\u0061\u0066\u00e9 \U0001f680",
        "items": [1, 2, 3],
    }
    body = json.dumps(value, ensure_ascii=False).encode()
    emoji = "\U0001f680".encode()
    emoji_start = body.index(emoji)
    cuts = [7, emoji_start + 1, emoji_start + 3, len(body) - 2]
    chunks = []
    start = 0
    for end in cuts + [len(body)]:
        chunks.append(body[start:end])
        start = end

    resp = await fetch_chunks(
        fastapi_app,
        "/platform/chunked-json",
        chunks,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    data = await read_json(resp)
    assert data["chunk_sizes"] == [len(chunk) for chunk in chunks]
    assert data["sha256"] == hashlib.sha256(body).hexdigest()
    assert data["data"] == value


@pytest.mark.asyncio
async def test_concurrent_requests_keep_bindings_and_data_isolated(fastapi_app):
    """Interleaved requests retain their own env, headers, and bodies."""
    reset_platform_concurrency()

    async def request(marker):
        resp = await fetch(
            fastapi_app,
            "/platform/concurrent-env",
            env={"marker": marker},
            method="POST",
            headers={"X-Request-Marker": marker},
            body=f"body-{marker}",
        )
        assert resp.status == 200
        return await read_json(resp)

    first, second = await asyncio.wait_for(
        asyncio.gather(request("first"), request("second")), timeout=5
    )
    assert first == {
        "binding": "first",
        "header": "first",
        "body": "body-first",
    }
    assert second == {
        "binding": "second",
        "header": "second",
        "body": "body-second",
    }


@pytest.mark.asyncio
async def test_multiple_set_cookie_headers_survive_fastapi(fastapi_app):
    """FastAPI's separate Set-Cookie headers remain distinct through JS Headers."""
    resp = await fetch(fastapi_app, "/platform/multiple-cookies")
    assert resp.status == 200
    cookies = list(resp.headers.getSetCookie())
    assert len(cookies) == 3
    assert cookies[0].startswith("first=1;")
    assert cookies[1].startswith("second=two;")
    assert cookies[2].startswith("dated=3;")
    assert "Wed, 21 Oct 2037 07:28:00 GMT" in cookies[2]


@pytest.mark.asyncio
async def test_gzip_middleware_preserves_binary_body(fastapi_app):
    """GZipMiddleware compresses binary data streamed through a JS Response."""
    expected = bytes(range(256)) * 32
    resp = await fetch(
        fastapi_app,
        "/platform/gzip-binary",
        headers={"Accept-Encoding": "gzip"},
    )
    assert resp.status == 200
    assert resp.headers.get("content-encoding") == "gzip"
    assert gzip.decompress((await resp.bytes()).to_bytes()) == expected
