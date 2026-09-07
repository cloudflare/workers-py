"""Tests for Flask running against a live pywrangler dev server."""

from pathlib import Path

import pytest
from conftest import COMPAT_CONFIGS, CompatConfig, register_in_worker_suites

WEB_FRAMEWORKS_DIR = Path(__file__).parent / "web-frameworks-test" / "flask-tests"
WEB_FRAMEWORKS_SRC_DIR = WEB_FRAMEWORKS_DIR / "src"


@pytest.fixture(scope="module")
def worker_project_dir() -> Path:
    return WEB_FRAMEWORKS_DIR


@pytest.fixture(
    scope="module",
    params=COMPAT_CONFIGS,
    ids=[config.python_version for config in COMPAT_CONFIGS],
)
def compat_config(request: pytest.FixtureRequest) -> CompatConfig:
    return request.param


register_in_worker_suites(globals(), WEB_FRAMEWORKS_SRC_DIR)
