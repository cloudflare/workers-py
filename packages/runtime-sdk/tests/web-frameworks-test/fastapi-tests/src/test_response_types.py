"""Tests for FastAPI response types and request object access.

Exercises different response classes (JSON, HTML, PlainText, Redirect,
StreamingResponse), cookie setting/reading, header extraction, request URL
access, and null-body status codes.  These are relevant for Pyodide/Workers
because:

- Each response type takes a different path through the ASGI adapter
  (``asgi.py`` ``process_request``): single-chunk bodies, streaming via
  ``TransformStream``, and null-body statuses (204/304) each have distinct
  branches.
- ``RedirectResponse`` (3xx + Location header) tests that the adapter does
  not interfere with redirect semantics.
- Cookie and header extraction validates that ``request_to_scope()`` builds
  the ASGI scope ``headers`` list correctly from the Workers ``Request``.
- Async streaming tests the ``TransformStream`` path that is unique to the
  Workers ASGI adapter.
"""

import pytest
from _client import fetch, get_json

# -- JSON with custom status code --------------------------------------------


@pytest.mark.asyncio
async def test_json_response_201(fastapi_app):
    """A route with status_code=201 returns 201 and the JSON body."""
    resp, data = await get_json(fastapi_app, "/responses/json-201")
    assert resp.status == 201
    assert data["created"] is True
    assert data["id"] == 42


# -- HTMLResponse ------------------------------------------------------------


@pytest.mark.asyncio
async def test_html_response(fastapi_app):
    """HTMLResponse returns text/html content type and HTML body."""
    resp = await fetch(fastapi_app, "/responses/html")
    assert resp.status == 200
    assert "text/html" in resp.headers.get("content-type")
    body = await resp.text()
    assert "<h1>Hello Workers</h1>" in body


# -- PlainTextResponse -------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_text_response(fastapi_app):
    """PlainTextResponse returns text/plain content type."""
    resp = await fetch(fastapi_app, "/responses/plain-text")
    assert resp.status == 200
    assert "text/plain" in resp.headers.get("content-type")
    body = await resp.text()
    assert body == "just plain text"


# -- RedirectResponse --------------------------------------------------------


@pytest.mark.asyncio
async def test_redirect_response(fastapi_app):
    """RedirectResponse returns a 307 with a Location header."""
    resp = await fetch(fastapi_app, "/responses/redirect")
    assert resp.status == 307
    location = resp.headers.get("location")
    assert location is not None
    assert "/api/hello" in location


# -- Async StreamingResponse -------------------------------------------------


@pytest.mark.asyncio
async def test_async_streaming_response(fastapi_app):
    """StreamingResponse backed by an async generator delivers all chunks."""
    resp = await fetch(fastapi_app, "/responses/async-stream")
    assert resp.status == 200
    body = await resp.text()
    for i in range(5):
        assert f"async-chunk-{i}" in body


@pytest.mark.asyncio
async def test_async_streaming_content_type(fastapi_app):
    """Async StreamingResponse preserves the declared media type."""
    resp = await fetch(fastapi_app, "/responses/async-stream")
    assert resp.status == 200
    assert "text/plain" in resp.headers.get("content-type")


# -- Cookies -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_cookie(fastapi_app):
    """Response.set_cookie emits a Set-Cookie header."""
    resp = await fetch(fastapi_app, "/responses/set-cookie")
    assert resp.status == 200
    set_cookie = resp.headers.get("set-cookie")
    assert set_cookie is not None
    assert "session_id=abc123" in set_cookie
    assert "httponly" in set_cookie.lower()


@pytest.mark.asyncio
async def test_read_cookie(fastapi_app):
    """A Cookie() parameter reads the cookie value from the request."""
    resp, data = await get_json(
        fastapi_app,
        "/responses/read-cookie",
        headers={"Cookie": "session_id=xyz789"},
    )
    assert resp.status == 200
    assert data["session_id"] == "xyz789"


@pytest.mark.asyncio
async def test_read_cookie_missing(fastapi_app):
    """A missing cookie returns the default value (None)."""
    resp, data = await get_json(fastapi_app, "/responses/read-cookie")
    assert resp.status == 200
    assert data["session_id"] is None


# -- Headers -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_header(fastapi_app):
    """A Header() parameter reads a custom header from the request."""
    resp, data = await get_json(
        fastapi_app,
        "/responses/read-header",
        headers={"X-Custom-Token": "secret-value"},
    )
    assert resp.status == 200
    assert data["x_custom_token"] == "secret-value"


@pytest.mark.asyncio
async def test_read_header_missing(fastapi_app):
    """A missing header returns the default value (None)."""
    resp, data = await get_json(fastapi_app, "/responses/read-header")
    assert resp.status == 200
    assert data["x_custom_token"] is None


@pytest.mark.asyncio
async def test_custom_response_headers(fastapi_app):
    """Custom headers set on a Response are present in the HTTP response."""
    resp = await fetch(fastapi_app, "/responses/custom-headers")
    assert resp.status == 200
    assert resp.headers.get("x-request-id") == "req-12345"
    assert resp.headers.get("x-ratelimit-remaining") == "99"


# -- Request URL access ------------------------------------------------------


@pytest.mark.asyncio
async def test_request_url_path(fastapi_app):
    """request.url.path reflects the actual request path."""
    resp, data = await get_json(fastapi_app, "/responses/request-url?foo=bar")
    assert resp.status == 200
    assert data["path"] == "/responses/request-url"
    assert "foo=bar" in data["query"]
    assert data["method"] == "GET"


# -- 204 No Content (null-body status) ---------------------------------------


@pytest.mark.asyncio
async def test_no_content_204(fastapi_app):
    """A 204 response has no body (null-body status in the ASGI adapter)."""
    resp = await fetch(fastapi_app, "/responses/no-content")
    assert resp.status == 204
    body = await resp.text()
    assert body == ""
