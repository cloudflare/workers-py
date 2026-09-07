"""Tests for FastAPI running against a live pywrangler dev server.

Python 3.12 (Pyodide 0.26.0a2) is excluded. The in-worker pytest suite drives
async tests via ``loop.run_until_complete``, which is a no-op on Pyodide 0.26.0a2
(no ``run_sync``/JSPI): async tests return unawaited futures and report false
passes.
"""

from pathlib import Path

import pytest
from conftest import COMPAT_CONFIGS, CompatConfig, register_in_worker_suites

WEB_FRAMEWORKS_DIR: Path = (
    Path(__file__).parent / "web-frameworks-test" / "fastapi-tests"
)
WEB_FRAMEWORKS_SRC_DIR: Path = WEB_FRAMEWORKS_DIR / "src"


@pytest.fixture(scope="module")
def worker_project_dir() -> Path:
    return WEB_FRAMEWORKS_DIR


# Exclude Python 3.12 (Pyodide 0.26.0a2) for async tests.
FASTAPI_COMPAT_CONFIGS = [
    c for c in COMPAT_CONFIGS if c.python_version not in ("3.12",)
]


@pytest.fixture(
    scope="module",
    params=FASTAPI_COMPAT_CONFIGS,
    ids=[c.python_version for c in FASTAPI_COMPAT_CONFIGS],
)
def compat_config(request: pytest.FixtureRequest) -> CompatConfig:
    return request.param


register_in_worker_suites(globals(), WEB_FRAMEWORKS_SRC_DIR)
