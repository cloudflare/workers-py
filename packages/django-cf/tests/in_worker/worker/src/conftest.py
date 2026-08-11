# pyright: reportMissingImports=false

import pytest
from django.core.cache import cache
from workers import env as _env


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


@pytest.fixture
def env():
    return _env
