"""Tests for Cloudflare bindings (KV, R2, D1, etc.) running against a live pywrangler dev server.

The worker at bindings-test/src/worker.py exposes /run-tests/{suite} endpoints that execute
binding tests inside workerd and return JSON results.

The in-worker tests are ordinary pytest modules (src/test_<binding>.py); worker.py runs
pytest against them and returns per-test results.

To add a new binding: create src/test_<binding>.py in bindings-test/ with pytest tests
and add any required binding to wrangler.jsonc.

The hyperdrive suites are opt-in: they need a MySQL and a PostgreSQL server on
localhost, so they are skipped unless you run with ``-m hyperdrive``. See
.github/workflows/tests.yml for the exact database configuration they expect.
"""

from pathlib import Path

import pytest
from conftest import register_in_worker_suites

BINDINGS_TEST_DIR: Path = Path(__file__).parent / "bindings-test"
BINDINGS_SRC_DIR: Path = BINDINGS_TEST_DIR / "src"

SUITE_MARKS: dict[str, pytest.MarkDecorator] = {
    "hyperdrive_postgresql": pytest.mark.hyperdrive,
    "hyperdrive_mysql": pytest.mark.hyperdrive,
}


@pytest.fixture(scope="module")
def worker_project_dir() -> Path:
    return BINDINGS_TEST_DIR


register_in_worker_suites(globals(), BINDINGS_SRC_DIR, marks=SUITE_MARKS)
