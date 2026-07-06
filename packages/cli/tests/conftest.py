# Compat dates used to parametrize workerd and bindings integration tests.
# Each date exercises a different Python version inside the worker runtime:
#   - "2025-09-01" -> Python 3.12 (before the 2025-09-29 cutover)
#   - "2026-01-01" -> Python 3.13 (after the 2025-09-29 cutover)
# TODO: use compat flag instead of compat date

import ast
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

COMPAT_DATES: list[str] = ["2025-09-01", "2026-01-01"]

TEST_DIR: Path = Path(__file__).parent
WORKERS_PY: Path = TEST_DIR.parent
WORKERS_RUNTIME_SDK: Path = WORKERS_PY.parent / "runtime-sdk" / "src"

DEV_STARTUP_TIMEOUT: int = 120
DEV_POLL_INTERVAL: float = 0.5


class InWorkerTestResult(TypedDict):
    status: Literal["passed", "failed", "error", "skipped"]
    error: str
    traceback: str
    reason: str


SuiteResults = dict[str, InWorkerTestResult]


def replace_compat_date(file: Path, compat_date: str) -> None:
    file.write_text(file.read_text().replace("%COMPAT_DATE", compat_date))


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_ready(process: subprocess.Popen[str], base_url: str) -> None:
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


def start_dev_server(
    test_project_dir: Path,
    tmp_path_factory: pytest.TempPathFactory,
    compat_date: str,
    tmp_dir_prefix: str = "dev_server",
) -> Generator[str]:
    """Copy a test project, sync packages, start pywrangler dev, yield base URL."""
    tmp_path = tmp_path_factory.mktemp(tmp_dir_prefix)
    target = tmp_path / test_project_dir.name
    shutil.copytree(test_project_dir, target)
    env = os.environ | {"_PYODIDE_EXTRA_MOUNTS": str(tmp_path)}

    replace_compat_date(target / "wrangler.jsonc", compat_date)

    subprocess.run(
        ["uv", "run", "--with", WORKERS_PY, "pywrangler", "sync"],
        cwd=target,
        check=True,
        env=env,
    )

    shutil.copytree(WORKERS_RUNTIME_SDK, target / "python_modules", dirs_exist_ok=True)

    port: int = get_free_port()
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

    wait_for_ready(process, base_url)
    yield base_url

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


_suite_cache: dict[tuple[str, str], "SuiteResults | str"] = {}


def get_test_results(dev_server: str, suite: str) -> SuiteResults:
    key = (dev_server, suite)
    if key not in _suite_cache:
        try:
            resp = requests.get(f"{dev_server}/run-tests/{suite}", timeout=30)
            _suite_cache[key] = (
                resp.json()
                if resp.ok
                else f"Suite '{suite}' returned {resp.status_code}: {resp.text}"
            )
        except (requests.ConnectionError, requests.Timeout) as e:
            _suite_cache[key] = f"Suite '{suite}' request failed: {e}"
    cached = _suite_cache[key]
    if isinstance(cached, str):
        pytest.fail(cached)
    return cached


def make_test(suite: str, test_name: str) -> Callable:
    def test_fn(self: Any, dev_server: str) -> None:
        results = get_test_results(dev_server, suite)
        result: InWorkerTestResult | None = results.get(test_name)
        assert result is not None, f"Test {suite}::{test_name} not found in results"
        if result["status"] == "skipped":
            pytest.skip(result.get("reason", ""))
        elif result["status"] == "failed":
            pytest.fail(result["error"])
        elif result["status"] == "error":
            pytest.fail(f"{result['error']}\n{result.get('traceback', '')}")

    test_fn.__name__ = f"test_{test_name}"
    return test_fn


def suite_class(suite: str, tests: list[str]) -> type:
    """Create a test class with one method per in-worker test."""
    return type(
        f"Test{suite.upper()}",
        (),
        {f"test_{name}": make_test(suite, name) for name in tests},
    )


def discover_test_names(module_path: Path) -> list[str]:
    """Return the suite-relative names of test functions defined in a module.

    Parses the source statically (no import) and strips the ``test_`` prefix so
    the names match the keys returned by the in-worker ResultCollector.
    """
    tree = ast.parse(module_path.read_text())
    return [
        node.name[len("test_") :]
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    ]


def discover_suites(src_dir: Path) -> dict[str, list[str]]:
    """Map each ``test_<suite>.py`` module to its discovered test names."""
    return {
        module_path.stem[len("test_") :]: discover_test_names(module_path)
        for module_path in sorted(src_dir.glob("test_*.py"))
    }
