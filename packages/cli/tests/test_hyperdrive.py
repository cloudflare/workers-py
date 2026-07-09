"""Tests for Hyperdrive database connectivity.

These tests require running database instances. They are disabled locally by default
because the database setup is non-trivial. In CI, databases are provided via Docker services.

To run locally:

    1. Start MySQL and PostgreSQL (e.g. via Docker):

        docker run -d --name test-mysql -p 3306:3306 \
            -e MYSQL_ROOT_PASSWORD=rootpass \
            -e MYSQL_USER=testuser \
            -e MYSQL_PASSWORD=testpass \
            -e MYSQL_DATABASE=testdb \
            mysql:8.0 --default-authentication-plugin=mysql_native_password

        docker run -d --name test-postgres -p 5432:5432 \
            -e POSTGRES_USER=testuser \
            -e POSTGRES_PASSWORD=testpass \
            -e POSTGRES_DB=testdb \
            -e POSTGRES_HOST_AUTH_METHOD=md5 \
            -e POSTGRES_INITDB_ARGS="--auth-host=md5" \
            postgres:16

    2. Run the tests:

        uv run pytest tests/test_hyperdrive.py -v

    3. Clean up:

        docker rm -f test-mysql test-postgres
"""

import ast
import functools
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any, Literal, TypedDict

import pytest
import requests
from conftest import COMPAT_CONFIGS, inject_compat_flags, replace_compat_date

TEST_DIR: Path = Path(__file__).parent
HYPERDRIVE_TEST_DIR: Path = TEST_DIR / "hyperdrive-test"
HYPERDRIVE_SRC_DIR: Path = HYPERDRIVE_TEST_DIR / "src"
WORKERS_PY: Path = TEST_DIR.parent
WORKERS_RUNTIME_SDK: Path = WORKERS_PY.parent / "runtime-sdk" / "src"

DEV_STARTUP_TIMEOUT: int = 120
DEV_POLL_INTERVAL: float = 0.5

COMPAT_CONFIGS_SOCKET_SUPPORT = [c for c in COMPAT_CONFIGS if c.compat_date not in  ("2025-09-01", "2026-01-01")]


class HyperdriveTestResult(TypedDict):
    status: Literal["passed", "failed", "error", "skipped"]
    error: str
    traceback: str
    reason: str


SuiteResults = dict[str, HyperdriveTestResult]


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_ready(process: subprocess.Popen[str], base_url: str) -> None:
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


@pytest.fixture(
    scope="module",
    params=COMPAT_CONFIGS_SOCKET_SUPPORT,
    ids=[c.python_version for c in COMPAT_CONFIGS_SOCKET_SUPPORT],
)
def compat_config(request: pytest.FixtureRequest) -> CompatConfig:
    return request.param


@pytest.fixture(scope="module")
def dev_server(
    tmp_path_factory: pytest.TempPathFactory, compat_config: CompatConfig
) -> Generator[str]:
    tmp_path = tmp_path_factory.mktemp("hyperdrive_test")
    target = tmp_path / "hyperdrive-test"
    shutil.copytree(HYPERDRIVE_TEST_DIR, target)
    env = os.environ | {"_PYODIDE_EXTRA_MOUNTS": str(tmp_path)}

    wrangler_jsonc = target / "wrangler.jsonc"
    replace_compat_date(wrangler_jsonc, compat_config.compat_date)
    inject_compat_flags(wrangler_jsonc, compat_config.extra_compat_flags)

    subprocess.run(
        ["uv", "run", "--with", WORKERS_PY, "pywrangler", "sync"],
        cwd=target,
        check=True,
        env=env,
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
        env=env,
    )

    _wait_for_ready(process, base_url)
    yield base_url

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@functools.cache
def _get_test_results(dev_server: str, suite: str) -> SuiteResults:
    resp = requests.get(f"{dev_server}/run-tests/{suite}", timeout=60)
    assert resp.ok, f"Suite '{suite}' returned {resp.status_code}: {resp.text}"
    return resp.json()


def _make_test(suite: str, test_name: str) -> Callable:
    def test_fn(self: Any, dev_server: str) -> None:
        results = _get_test_results(dev_server, suite)
        result: HyperdriveTestResult | None = results.get(test_name)
        assert result is not None, f"Test {suite}::{test_name} not found in results"
        if result["status"] == "skipped":
            pytest.skip(result.get("reason", ""))
        elif result["status"] == "failed":
            pytest.fail(result["error"])
        elif result["status"] == "error":
            pytest.fail(f"{result['error']}\n{result.get('traceback', '')}")

    test_fn.__name__ = f"test_{test_name}"
    return test_fn


def binding_suite(suite: str, tests: list[str]) -> type:
    return type(
        f"Test{suite.upper()}",
        (),
        {f"test_{name}": _make_test(suite, name) for name in tests},
    )


def _discover_test_names(module_path: Path) -> list[str]:
    tree = ast.parse(module_path.read_text())
    return [
        node.name[len("test_") :]
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    ]


def _discover_suites() -> dict[str, list[str]]:
    return {
        module_path.stem[len("test_") :]: _discover_test_names(module_path)
        for module_path in sorted(HYPERDRIVE_SRC_DIR.glob("test_*.py"))
    }


for _suite, _test_names in _discover_suites().items():
    _suite_cls = binding_suite(_suite, _test_names)
    globals()[_suite_cls.__name__] = _suite_cls
