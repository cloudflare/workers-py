"""Tests for web framework compatibility running against a live pywrangler dev server.

To add a new framework: create a subdirectory under web-frameworks-test/ with
worker.py, wrangler.jsonc, pyproject.toml, and test_*.py files.

Python 3.12 (Pyodide 0.26.0a2) is excluded. The in-worker pytest suite drives
async tests via ``loop.run_until_complete``, which is a no-op on Pyodide 0.26.0a2
(no ``run_sync``/JSPI): async tests return unawaited futures and report false
passes. Pyodide 0.28.2+ (Python 3.13 and later) implement ``run_until_complete``
via ``run_sync``, so the tests genuinely run. Any current or future non-3.12
compat date in ``COMPAT_DATES`` is exercised automatically.
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from conftest import (
    COMPAT_DATES,
    TEST_DIR,
    discover_suites,
    start_dev_server,
    suite_class,
)

WEB_FRAMEWORKS_DIR: Path = TEST_DIR / "web-frameworks-test"
DJANGO_ASYNC_DIR: Path = WEB_FRAMEWORKS_DIR / "django-async"
DJANGO_ASYNC_SRC_DIR: Path = DJANGO_ASYNC_DIR / "src"

# Django Async handler heavily uses `run_until_complete`,
# which is not supported in Pyodide 0.26.0a2 (no run_sync).
# So we only test Python 3.13 and upper here.
ASYNC_COMPAT_DATES = [d for d in COMPAT_DATES if d != "2025-09-01"]


@pytest.fixture(scope="module", params=ASYNC_COMPAT_DATES)
def compat_date(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture(scope="module")
def dev_server(
    tmp_path_factory: pytest.TempPathFactory, compat_date: str
) -> Generator[str]:
    yield from start_dev_server(
        DJANGO_ASYNC_DIR, tmp_path_factory, compat_date, "django_async_test"
    )


for _suite, _test_names in discover_suites(DJANGO_ASYNC_SRC_DIR).items():
    _suite_cls = suite_class(_suite, _test_names)
    globals()[_suite_cls.__name__] = _suite_cls
