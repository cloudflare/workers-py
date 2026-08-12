"""Mirrors of the pytest suites that run inside workerd, plus WSGI round-trips.

Python 3.12 (Pyodide 0.26.0a2) is excluded from the matrix. That runtime has no
JSPI, so ``pyodide.ffi.run_sync`` is missing and every R2Storage test skips
itself; what remains duplicates the 3.13 and 3.14 runs at a third of the
suite's wall clock.
"""

# pyright: reportMissingImports=false, reportMissingModuleSource=false

from pathlib import Path

import pytest
import requests

from tests.conftest import COMPAT_CONFIGS, CompatConfig, register_in_worker_suites

IN_WORKER_SRC_DIR: Path = Path(__file__).parent / "worker" / "src"

MATRIX: list[CompatConfig] = [c for c in COMPAT_CONFIGS if c.python_version != "3.12"]


@pytest.fixture(
    scope="module",
    params=MATRIX,
    ids=[c.python_version for c in MATRIX],
)
def compat_config(request: pytest.FixtureRequest) -> CompatConfig:
    return request.param


register_in_worker_suites(globals(), IN_WORKER_SRC_DIR)


def test_wsgi_header_transformation(in_worker_server: str) -> None:
    response = requests.get(
        f"{in_worker_server}/wsgi/headers",
        headers={
            "cf-access-jwt-assertion": "jwt-token",
            "x-custom-header": "custom-value",
            "content-type": "text/plain",
        },
        timeout=10,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cf_access"] == "jwt-token"
    assert payload["custom"] == "custom-value"
    assert payload["content_type"] == "text/plain"


def test_wsgi_reads_request_body(in_worker_server: str) -> None:
    response = requests.post(
        f"{in_worker_server}/wsgi/body",
        headers={"content-type": "text/plain"},
        data=b"request-body",
        timeout=10,
    )

    assert response.status_code == 200
    assert response.text == "request-body"
