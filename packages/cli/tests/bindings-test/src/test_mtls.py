import pytest
from workers._workers import _FetcherWrapper

# cannot test mTLS locally so we just check the binding is properly wrapped

@pytest.mark.asyncio
async def test_is_fetcher_wrapper(env):
    assert isinstance(env.MY_CERT, _FetcherWrapper)


@pytest.mark.asyncio
async def test_has_fetch(env):
    assert callable(env.MY_CERT.fetch)
