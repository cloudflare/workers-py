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
    process.wait()
    pytest.fail(f"pywrangler dev did not become ready within {DEV_STARTUP_TIMEOUT}s")


@pytest.fixture(scope="module")
def dev_server(tmp_path_factory: Any) -> Generator[str]:
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
        process.wait()


_test_suite_cache: dict[str, SuiteResults] = {}


def _get_test_results(dev_server: str, suite: str) -> SuiteResults:
    if suite not in _test_suite_cache:
        resp = requests.get(f"{dev_server}/run-tests/{suite}", timeout=60)
        assert resp.ok, f"Suite '{suite}' returned {resp.status_code}: {resp.text}"
        _test_suite_cache[suite] = resp.json()
    return _test_suite_cache[suite]


def _make_test(suite: str, test_name: str) -> Callable:
    def test_fn(self: Any, dev_server: str) -> None:
        results = _get_test_results(dev_server, suite)
        result: BindingTestResult | None = results.get(test_name)
        assert result is not None, f"Test {suite}::{test_name} not found in results"
        if result["status"] == "failed":
            pytest.fail(result["error"])
        elif result["status"] == "error":
            pytest.fail(f"{result['error']}\n{result.get('traceback', '')}")

    test_fn.__name__ = f"test_{test_name}"
    return test_fn


def binding_suite(suite: str, tests: list[str]) -> type:
    """Register a binding test suite: creates a test class with one method per test."""
    return type(
        f"Test{suite.upper()}",
        (),
        {f"test_{name}": _make_test(suite, name) for name in tests},
    )


TestKV = binding_suite(
    "kv",
    [
        "put_and_get_text",
        "get_nonexistent",
        "put_and_get_json",
        "put_overwrite",
        "put_empty_value",
        "delete",
        "delete_nonexistent",
        "put_with_metadata",
        "get_with_metadata_nonexistent",
        "put_with_expiration_ttl",
        "list_basic",
        "list_with_prefix",
        "list_with_limit_and_cursor",
        "list_empty_prefix",
        "list_with_metadata",
    ],
)

TestR2 = binding_suite(
    "r2",
    [
        "put_and_get_text",
        "put_and_get_json",
        "put_with_http_metadata",
        "put_with_custom_metadata",
        "head_object",
        "get_nonexistent",
        "head_nonexistent",
        "delete_single",
        "delete_multiple",
        "list_basic",
        "list_with_prefix",
        "list_with_limit_and_cursor",
        "list_with_delimiter",
        "overwrite_object",
        "put_empty_body",
        "get_range_offset_length",
        "get_range_suffix",
        "r2object_properties",
        "multipart_upload",
        "multipart_abort",
    ],
)

TestD1 = binding_suite(
    "d1",
    [
        "insert_and_select_via_run",
        "all_returns_results",
        "first_returns_single_row",
        "first_with_column_name",
        "first_on_empty_result",
        "raw_returns_arrays",
        "raw_with_column_names",
        "bind_null",
        "bind_integer",
        "bind_float",
        "bind_string",
        "bind_boolean",
        "bind_multiple_parameters",
        "exec_create_and_query",
        "exec_multiple_statements",
        "batch_multiple_inserts",
        "run_metadata_fields",
        "update_row",
        "delete_row",
        "invalid_sql_raises_error",
    ],
)
