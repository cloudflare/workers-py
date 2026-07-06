"""Tests for Cloudflare bindings (KV, R2, D1, etc.) running against a live pywrangler dev server.

The worker at bindings-test/src/worker.py exposes /run-tests/{suite} endpoints that execute
binding tests inside workerd and return JSON results. This file starts the dev server, calls
those endpoints, and maps each in-worker test to a pytest test case.

The in-worker tests are ordinary pytest modules (src/test_<binding>.py); worker.py runs
pytest against them and returns per-test results.

To add a new binding: create src/test_<binding>.py in bindings-test/ with pytest tests
and add any required binding to wrangler.jsonc.
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

BINDINGS_TEST_DIR: Path = TEST_DIR / "bindings-test"
BINDINGS_SRC_DIR: Path = BINDINGS_TEST_DIR / "src"


@pytest.fixture(scope="module", params=COMPAT_DATES)
def compat_date(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture(scope="module")
def dev_server(
    tmp_path_factory: pytest.TempPathFactory, compat_date: str
) -> Generator[str]:
    yield from start_dev_server(
        BINDINGS_TEST_DIR, tmp_path_factory, compat_date, "bindings_test"
    )


# Generate a TestXxx class per discovered suite so each in-worker test surfaces
# as its own pytest case without manual registration.
for _suite, _test_names in discover_suites(BINDINGS_SRC_DIR).items():
    _suite_cls = suite_class(_suite, _test_names)
    globals()[_suite_cls.__name__] = _suite_cls
