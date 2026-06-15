# pyright: reportMissingImports=false

import pytest
from workers import env as _env


@pytest.fixture
def env():
    return _env
