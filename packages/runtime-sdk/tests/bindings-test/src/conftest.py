# pyright: reportMissingImports=false
import uuid

import pytest

from workers import env as _env


@pytest.fixture
def env():
    return _env


def unique_table_name() -> str:
    """Unique per call"""
    return f"test_{uuid.uuid4().hex[:10]}"
