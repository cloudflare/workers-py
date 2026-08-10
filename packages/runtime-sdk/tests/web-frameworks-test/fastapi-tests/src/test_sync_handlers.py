"""Tests for FastAPI features that rely on anyio.to_thread.run_sync.

The workers runtime is single-threaded, so ``anyio.to_thread.run_sync`` is
patched to run the callable inline.  Without the patch every test in this file
would fail with ``RuntimeError: can't start new thread``.

Covered call-sites:
- Sync ``def`` route handlers (``starlette.routing`` / ``fastapi.routing``)
- Sync dependencies (``fastapi.dependencies.utils``)
- Sync ``BackgroundTask`` (``starlette.background``)
- Sync-iterator ``StreamingResponse`` (``starlette.concurrency.iterate_in_threadpool``)
- ``UploadFile.read`` (``starlette.datastructures``)
"""

import pytest
from _client import build_multipart, fetch, get_json, read_json

# -- sync route handlers -----------------------------------------------------


@pytest.mark.asyncio
async def test_sync_handler_returns_json(fastapi_app):
    """A plain ``def`` route handler returns a JSON response."""
    resp, data = await get_json(fastapi_app, "/sync/hello")
    assert resp.status == 200
    assert data["message"] == "sync hello"


@pytest.mark.asyncio
async def test_sync_post_handler(fastapi_app):
    """A sync POST handler receives the request and responds."""
    resp = await fetch(fastapi_app, "/sync/echo", method="POST", body="hi")
    assert resp.status == 200
    data = await read_json(resp)
    assert data["method"] == "POST"


# -- sync dependency ----------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_dependency(fastapi_app):
    """An async handler that depends on a sync ``def`` dependency."""
    resp, data = await get_json(fastapi_app, "/sync/dep")
    assert resp.status == 200
    assert data["greeting"] == "hello from sync dep"


# -- sync background task -----------------------------------------------------


@pytest.mark.asyncio
async def test_sync_background_task(fastapi_app):
    """A sync function passed to ``BackgroundTask`` runs to completion."""
    resp, data = await get_json(fastapi_app, "/sync/background/run")
    assert resp.status == 200
    assert data["submitted"] is True

    # The background task runs inline (patched), so by the time the response
    # is fully sent the side-effect should already be visible.
    resp2, data2 = await get_json(fastapi_app, "/sync/background/check")
    assert resp2.status == 200
    assert data2["bg_ran"] is True


# -- sync-iterator streaming response ----------------------------------------


@pytest.mark.asyncio
async def test_sync_streaming_response(fastapi_app):
    """StreamingResponse backed by a sync generator delivers all chunks."""
    resp = await fetch(fastapi_app, "/sync/stream")
    assert resp.status == 200
    body = await resp.text()
    for i in range(5):
        assert f"chunk-{i}" in body


@pytest.mark.asyncio
async def test_sync_streaming_content_type(fastapi_app):
    """StreamingResponse preserves the declared media type."""
    resp = await fetch(fastapi_app, "/sync/stream")
    assert resp.status == 200
    assert "text/plain" in resp.headers.get("content-type")


# -- file upload (UploadFile) -------------------------------------------------


@pytest.mark.asyncio
async def test_single_file_upload(fastapi_app):
    """A single file upload is received and its content is echoed back."""
    body, content_type = build_multipart([("file", "greet.txt", "hello world")])
    resp = await fetch(
        fastapi_app,
        "/upload/single",
        method="POST",
        headers={"Content-Type": content_type},
        body=body,
    )
    assert resp.status == 200
    data = await read_json(resp)
    assert data["filename"] == "greet.txt"
    assert data["size"] > 0
    assert "hello world" in data["text"]


@pytest.mark.asyncio
async def test_multiple_file_upload(fastapi_app):
    """Multiple files are received and their metadata is echoed back."""
    body, content_type = build_multipart(
        [
            ("files", "one.txt", "first"),
            ("files", "two.txt", "second"),
        ]
    )
    resp = await fetch(
        fastapi_app,
        "/upload/multiple",
        method="POST",
        headers={"Content-Type": content_type},
        body=body,
    )
    assert resp.status == 200
    data = await read_json(resp)
    assert len(data) == 2
    assert [f["filename"] for f in data] == ["one.txt", "two.txt"]
    assert all(f["size"] > 0 for f in data)
