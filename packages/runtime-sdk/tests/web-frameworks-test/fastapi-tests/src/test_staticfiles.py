"""Tests for FastAPI's native static file APIs (StaticFiles and FileResponse).

Unlike ``test_assets.py``, which proxies to the Workers Assets binding, these
tests exercise Starlette's own filesystem-backed static file serving against
files bundled into the worker under ``src/static/``.
"""

import pytest
from _client import fetch, get_json, read_json


@pytest.mark.asyncio
async def test_staticfiles_serves_text(fastapi_app):
    """Mounted StaticFiles app serves a bundled text file."""
    resp = await fetch(fastapi_app, "/static/hello.txt")
    assert resp.status == 200
    text = await resp.text()
    assert "Hello from StaticFiles" in text


@pytest.mark.asyncio
async def test_staticfiles_serves_html(fastapi_app):
    """Mounted StaticFiles app serves a bundled HTML file."""
    resp = await fetch(fastapi_app, "/static/index.html")
    assert resp.status == 200
    text = await resp.text()
    assert "Hello from StaticFiles" in text
    assert "<!doctype html>" in text.lower()


@pytest.mark.asyncio
async def test_staticfiles_guesses_content_type(fastapi_app):
    """StaticFiles infers the content type from the file extension."""
    resp = await fetch(fastapi_app, "/static/app.css")
    assert resp.status == 200
    assert "css" in resp.headers.get("content-type")


@pytest.mark.asyncio
async def test_staticfiles_serves_json(fastapi_app):
    """StaticFiles serves a JSON file that is parseable and correctly typed."""
    resp = await fetch(fastapi_app, "/static/data.json")
    assert resp.status == 200
    assert "application/json" in resp.headers.get("content-type")
    data = await read_json(resp)
    assert data["source"] == "staticfiles"
    assert data["number"] == 7


@pytest.mark.asyncio
async def test_staticfiles_sets_content_length(fastapi_app):
    """StaticFiles reports the on-disk size and sends exactly that many bytes."""
    resp = await fetch(fastapi_app, "/static/hello.txt")
    assert resp.status == 200
    content_length = resp.headers.get("content-length")
    assert content_length is not None
    body = (await resp.text()).encode()
    assert len(body) == int(content_length)


@pytest.mark.asyncio
async def test_staticfiles_sets_validators(fastapi_app):
    """StaticFiles derives etag and last-modified headers from the file stat."""
    resp = await fetch(fastapi_app, "/static/hello.txt")
    assert resp.status == 200
    assert resp.headers.get("etag")
    assert resp.headers.get("last-modified")


@pytest.mark.asyncio
async def test_staticfiles_honours_if_none_match(fastapi_app):
    """A conditional request matching the etag gets a 304 with no body."""
    first = await fetch(fastapi_app, "/static/hello.txt")
    etag = first.headers.get("etag")
    assert etag

    second = await fetch(
        fastapi_app, "/static/hello.txt", headers={"if-none-match": etag}
    )
    assert second.status == 304
    assert await second.text() == ""


@pytest.mark.asyncio
async def test_staticfiles_missing_file_returns_404(fastapi_app):
    """StaticFiles returns 404 for a file that is not bundled."""
    resp = await fetch(fastapi_app, "/static/nonexistent.txt")
    assert resp.status == 404


@pytest.mark.asyncio
async def test_file_response_serves_file(fastapi_app):
    """A route returning FileResponse streams the bundled file."""
    resp = await fetch(fastapi_app, "/native-file")
    assert resp.status == 200
    assert "text/plain" in resp.headers.get("content-type")
    text = await resp.text()
    assert "Hello from StaticFiles" in text


@pytest.mark.asyncio
async def test_file_response_sets_content_length(fastapi_app):
    """FileResponse reports the on-disk size and sends exactly that many bytes."""
    resp = await fetch(fastapi_app, "/native-file")
    assert resp.status == 200
    content_length = resp.headers.get("content-length")
    assert content_length is not None
    body = (await resp.text()).encode()
    assert len(body) == int(content_length)


@pytest.mark.asyncio
async def test_api_route_still_works(fastapi_app, env):
    """API routes are unaffected by the StaticFiles mount."""
    resp, data = await get_json(fastapi_app, "/api/hello", env=env)
    assert resp.status == 200
    assert data["message"] == "Hello from FastAPI"
