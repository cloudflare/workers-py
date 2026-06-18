import pytest
from workers._workers import _BindingWrapper


@pytest.mark.asyncio
async def test_vectorize_is_wrapped(env):
    # Vectorize requires remote database even in local development environment
    # so we cannot test it in this unittest
    # Here, we just make sure it is wrapped properly with our bindings wrapper
    assert isinstance(env.VECTORIZE, _BindingWrapper)
