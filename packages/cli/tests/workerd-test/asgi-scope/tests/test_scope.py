import asyncio
import json

import pytest
from workers import env

TIMEOUT_S = 5


async def _scope(path, **kwargs):
    response = await asyncio.wait_for(
        env.SELF.fetch(f"http://example.com{path}", **kwargs), TIMEOUT_S
    )
    return json.loads(await response.text())


@pytest.mark.asyncio
async def test_scope_path_is_percent_decoded():
    scope = await _scope("/files/hello%20world")
    assert scope["path"] == "/files/hello world"


@pytest.mark.asyncio
async def test_scope_exposes_raw_path():
    scope = await _scope("/files/hello%20world")
    assert scope["raw_path"] == "/files/hello%20world"
