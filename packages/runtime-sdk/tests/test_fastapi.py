"""Tests for FastAPI running against a live pywrangler dev server.

Python 3.12 (Pyodide 0.26.0a2) is excluded. The in-worker pytest suite drives
async tests via ``loop.run_until_complete``, which is a no-op on Pyodide 0.26.0a2
(no ``run_sync``/JSPI): async tests return unawaited futures and report false
passes.
"""

from pathlib import Path

import pytest
from testlib.host import (
    COMPAT_CONFIGS,
    compat_config_fixture,
    register_in_worker_suites,
)

WEB_FRAMEWORKS_DIR: Path = (
    Path(__file__).parent / "web-frameworks-test" / "fastapi-tests"
)
WEB_FRAMEWORKS_SRC_DIR: Path = WEB_FRAMEWORKS_DIR / "src"


@pytest.fixture(scope="module")
def worker_project_dir() -> Path:
    return WEB_FRAMEWORKS_DIR


# Exclude Python 3.12 (Pyodide 0.26.0a2) for async tests.
compat_config = compat_config_fixture(
    [c for c in COMPAT_CONFIGS if c.python_version != "3.12"]
)


register_in_worker_suites(globals(), WEB_FRAMEWORKS_SRC_DIR)
