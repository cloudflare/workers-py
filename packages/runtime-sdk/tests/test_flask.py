"""Tests for Flask running against a live pywrangler dev server."""

from pathlib import Path

import pytest
from testlib.host import register_in_worker_suites

WEB_FRAMEWORKS_DIR = Path(__file__).parent / "web-frameworks-test" / "flask-tests"
WEB_FRAMEWORKS_SRC_DIR = WEB_FRAMEWORKS_DIR / "src"


@pytest.fixture(scope="module")
def worker_project_dir() -> Path:
    return WEB_FRAMEWORKS_DIR


register_in_worker_suites(globals(), WEB_FRAMEWORKS_SRC_DIR)
