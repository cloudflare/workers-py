# pyright: reportMissingImports=false, reportMissingModuleSource=false

from pathlib import Path

import pytest
import requests

from tests.in_worker_harness import register_in_worker_suites

IN_WORKER_DIR: Path = Path(__file__).parent / "worker"
IN_WORKER_SRC_DIR: Path = IN_WORKER_DIR / "src"


@pytest.fixture(scope="module")
def worker_project_dir() -> Path:
    return IN_WORKER_DIR


register_in_worker_suites(globals(), IN_WORKER_SRC_DIR)


def test_wsgi_header_transformation(dev_server: str) -> None:
    response = requests.get(
        f"{dev_server}/wsgi/headers",
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


def test_wsgi_reads_request_body(dev_server: str) -> None:
    response = requests.post(
        f"{dev_server}/wsgi/body",
        headers={"content-type": "text/plain"},
        data=b"request-body",
        timeout=10,
    )

    assert response.status_code == 200
    assert response.text == "request-body"
