import pytest


@pytest.mark.asyncio
async def test_has_id(env):
    assert isinstance(env.VERSION.id, str)
    assert len(env.VERSION.id) > 0


@pytest.mark.asyncio
async def test_has_tag(env):
    assert isinstance(env.VERSION.tag, str)


@pytest.mark.asyncio
async def test_has_timestamp(env):
    assert env.VERSION.timestamp is not None
