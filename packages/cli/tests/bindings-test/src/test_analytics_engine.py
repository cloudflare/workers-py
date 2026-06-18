import pytest
from workers._workers import _BindingWrapper


@pytest.mark.asyncio
async def test_is_wrapped(env):
    assert isinstance(env.ANALYTICS, _BindingWrapper)


@pytest.mark.asyncio
async def test_write_data_point_blobs_and_doubles(env):
    env.ANALYTICS.writeDataPoint({
        "blobs": ["blob1", "blob2"],
        "doubles": [1.0, 2.5],
        "indexes": ["idx"],
    })


@pytest.mark.asyncio
async def test_write_data_point_empty(env):
    env.ANALYTICS.writeDataPoint({})
