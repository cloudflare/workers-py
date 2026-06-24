import pytest
from workers._workers import _FetcherWrapper


@pytest.mark.asyncio
async def test_is_fetcher_wrapper(env):
    assert isinstance(env.ASSETS, _FetcherWrapper)


@pytest.mark.asyncio
async def test_fetch_text_file(env):
    resp = await env.ASSETS.fetch("https://assets.local/hello.txt")
    text = await resp.text()
    assert text.strip() == "hello from static assets"


@pytest.mark.asyncio
async def test_fetch_json_file(env):
    resp = await env.ASSETS.fetch("https://assets.local/data.json")
    data = await resp.json()
    assert data["key"] == "value"
    assert data["number"] == 42


@pytest.mark.asyncio
async def test_fetch_returns_404_for_missing(env):
    resp = await env.ASSETS.fetch("https://assets.local/nonexistent.txt")
    assert resp.status == 404


@pytest.mark.asyncio
async def test_fetch_content_type(env):
    resp = await env.ASSETS.fetch("https://assets.local/data.json")
    assert "application/json" in resp.headers.get("content-type")
