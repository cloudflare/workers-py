import pytest
from workers._workers import _BindingWrapper


@pytest.mark.asyncio
async def test_is_wrapped(env):
    assert isinstance(env.RATE_LIMITER, _BindingWrapper)


@pytest.mark.asyncio
async def test_limit_success(env):
    result = await env.RATE_LIMITER.limit({"key": "test-key"})
    assert result.success is True
