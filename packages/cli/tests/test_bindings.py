"""Tests for Cloudflare bindings (KV, R2, D1, etc.) running against a live pywrangler dev server.

The worker at bindings-test/src/worker.py exposes /run-tests/{suite} endpoints that execute
binding tests inside workerd and return JSON results. This file starts the dev server, calls
those endpoints, and maps each in-worker test to a pytest test case.

To add a new binding: create src/<binding>_test.py in bindings-test/, register it in
worker.py's ALL_TESTS, then add a TestXxx class below.
"""

import shutil
import socket
import subprocess
import time
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

import pytest
import requests

TEST_DIR: Path = Path(__file__).parent
BINDINGS_TEST_DIR: Path = TEST_DIR / "bindings-test"
WORKERS_PY: Path = TEST_DIR.parent
WORKERS_RUNTIME_SDK: Path = WORKERS_PY.parent / "runtime-sdk" / "src"

DEV_STARTUP_TIMEOUT: int = 120
DEV_POLL_INTERVAL: float = 0.5


class BindingTestResult(TypedDict):
    status: Literal["passed", "failed", "error"]
    error: NotRequired[str]
    traceback: NotRequired[str]


SuiteResults = dict[str, BindingTestResult]


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_ready(process: subprocess.Popen[str], base_url: str) -> None:
    """Poll the /health endpoint until the dev server is accepting requests."""
    deadline = time.time() + DEV_STARTUP_TIMEOUT
    while time.time() < deadline:
        if process.poll() is not None:
            stdout = process.stdout.read() if process.stdout else ""
            pytest.fail(
                f"pywrangler dev exited early with code {process.returncode}\n"
                f"stdout: {stdout}"
            )
        try:
            resp = requests.get(f"{base_url}/health", timeout=2)
            if resp.ok:
                return
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(DEV_POLL_INTERVAL)

    process.kill()
    pytest.fail(f"pywrangler dev did not become ready within {DEV_STARTUP_TIMEOUT}s")


@pytest.fixture(scope="module")
def dev_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[str]:
    """Start a pywrangler dev server on a free port and yield its base URL."""
    tmp_path = tmp_path_factory.mktemp("bindings_test")
    target = tmp_path / "bindings-test"
    shutil.copytree(BINDINGS_TEST_DIR, target)

    subprocess.run(
        ["uv", "run", "--with", WORKERS_PY, "pywrangler", "sync"],
        cwd=target,
        check=True,
    )

    shutil.copytree(WORKERS_RUNTIME_SDK, target / "python_modules", dirs_exist_ok=True)

    port: int = _get_free_port()
    base_url: str = f"http://127.0.0.1:{port}"

    process = subprocess.Popen(
        [
            "uv",
            "run",
            "--with",
            WORKERS_PY,
            "pywrangler",
            "dev",
            "--port",
            str(port),
            "--persist-to",
            str(tmp_path / "state"),
        ],
        cwd=target,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    _wait_for_ready(process, base_url)
    yield base_url

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _run_suite(dev_server: str, suite_name: str) -> SuiteResults:
    """Call /run-tests/{suite} and return the per-test results dict."""
    resp = requests.get(f"{dev_server}/run-tests/{suite_name}", timeout=60)
    assert resp.ok, f"Suite '{suite_name}' returned {resp.status_code}: {resp.text}"
    return resp.json()


def _make_test(suite: str, name: str) -> Callable:
    """Generate a pytest method that fetches suite results and asserts a single test passed."""

    def test_fn(self: Any, dev_server: str) -> None:
        results: SuiteResults = _run_suite(dev_server, suite)
        result: BindingTestResult | None = results.get(name)
        assert result is not None, f"Test {suite}::{name} not found in results"
        if result["status"] == "failed":
            pytest.fail(result["error"])
        elif result["status"] == "error":
            pytest.fail(f"{result['error']}\n{result.get('traceback', '')}")

    test_fn.__name__ = f"test_{name}"
    return test_fn


KV_TESTS: list[str] = [
    "test_put_and_get",
    # TODO: add more tests for KV
]


class TestKV:
    """KV Namespace binding tests — exercised via /run-tests/kv."""

    pass


for _test_name in KV_TESTS:
    setattr(TestKV, f"test_{_test_name}", _make_test("kv", _test_name))
