"""Tests for serving static files through a FastAPI frontend route backed by Workers Assets."""

import pytest
from _client import fetch, get_json


@pytest.mark.asyncio
async def test_serves_index_html(fastapi_app, env):
    """Frontend route serves index.html from Workers Assets."""
    resp = await fetch(fastapi_app, "/index.html", env=env)
    assert resp.status == 200
    text = await resp.text()
    assert "Hello from static assets" in text
    assert "<!doctype html>" in text.lower()


@pytest.mark.asyncio
async def test_serves_css(fastapi_app, env):
    """Frontend route serves CSS with correct content type."""
    resp = await fetch(fastapi_app, "/style.css", env=env)
    assert resp.status == 200
    text = await resp.text()
    assert "font-family" in text
    content_type = resp.headers.get("content-type")
    assert "css" in content_type


@pytest.mark.asyncio
async def test_serves_json(fastapi_app, env):
    """Frontend route serves JSON file and it is parseable."""
    resp, data = await get_json(fastapi_app, "/data.json", env=env)
    assert resp.status == 200
    assert data["key"] == "value"
    assert data["number"] == 42


@pytest.mark.asyncio
async def test_serves_json_content_type(fastapi_app, env):
    """Frontend route serves JSON with correct content type."""
    resp = await fetch(fastapi_app, "/data.json", env=env)
    assert resp.status == 200
    assert "application/json" in resp.headers.get("content-type")


@pytest.mark.asyncio
async def test_missing_asset_returns_404(fastapi_app, env):
    """Frontend route returns 404 for nonexistent static files."""
    resp = await fetch(fastapi_app, "/nonexistent.txt", env=env)
    assert resp.status == 404


@pytest.mark.asyncio
async def test_api_route_still_works(fastapi_app, env):
    """API routes take priority over the frontend catch-all."""
    resp, data = await get_json(fastapi_app, "/api/hello", env=env)
    assert resp.status == 200
    assert data["message"] == "Hello from FastAPI"


@pytest.mark.asyncio
async def test_health_endpoint(fastapi_app, env):
    """Health endpoint works through FastAPI."""
    resp, data = await get_json(fastapi_app, "/health", env=env)
    assert resp.status == 200
    assert data["ok"] is True
