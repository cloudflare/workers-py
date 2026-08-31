"""Shared fixtures and helpers for the host-side test suite."""

import ast
import functools
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict

import pytest
import requests

TEST_DIR: Path = Path(__file__).parent
WORKERS_PY: Path = TEST_DIR.parent.parent / "cli"
WORKERS_RUNTIME_SDK: Path = TEST_DIR.parent / "src"

DEV_STARTUP_TIMEOUT: int = 120
DEV_POLL_INTERVAL: float = 0.5
SUITE_CONNECT_TIMEOUT: int = 10
SUITE_READ_TIMEOUT: int = 300

OPT_IN_MARKERS: tuple[str, ...] = ("hyperdrive",)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip opt-in suites unless the run explicitly asks for them via ``-m``."""
    markexpr: str = config.getoption("markexpr")
    for marker in OPT_IN_MARKERS:
        if marker in markexpr:
            continue
        skip = pytest.mark.skip(reason=f"needs local services; run with -m {marker}")
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)


@dataclass(frozen=True)
class CompatConfig:
    compat_date: str
    python_version: str
    extra_compat_flags: list[str] = field(default_factory=list)


COMPAT_CONFIGS: list[CompatConfig] = [
    CompatConfig(
        compat_date="2025-09-01",
        python_version="3.12",
        extra_compat_flags=[
            "enable_python_external_sdk",
            "python_process_pth_files",
            "python_request_headers_preserve_commas",
        ],
    ),
    CompatConfig(
        compat_date="2026-01-01",
        python_version="3.13",
        extra_compat_flags=[
            "enable_python_external_sdk",
            "python_process_pth_files",
            "python_request_headers_preserve_commas",
        ],
    ),
    CompatConfig(
        compat_date="2026-07-01",
        python_version="3.14",
        # TODO: remove these when 3.14 is stable, and enabled by date
        extra_compat_flags=["python_workers_314", "experimental"],
    ),
]


def replace_compat_date(file: Path, compat_date: str) -> None:
    file.write_text(file.read_text().replace("%COMPAT_DATE", compat_date))


def inject_compat_flags(file: Path, extra_flags: list[str]) -> None:
    if not extra_flags:
        return
    content = file.read_text()
    for flag in extra_flags:
        content = content.replace('"python_workers"', f'"python_workers", "{flag}"')
    file.write_text(content)


class InWorkerTestResult(TypedDict):
    status: Literal["passed", "failed", "error", "skipped"]
    error: str
    traceback: str
    reason: str


SuiteResults = dict[str, InWorkerTestResult]


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_ready(
    process: subprocess.Popen[bytes], base_url: str, log_path: Path
) -> None:
    """Poll the /health endpoint until the dev server is accepting requests."""
    deadline = time.time() + DEV_STARTUP_TIMEOUT
    while time.time() < deadline:
        if process.poll() is not None:
            pytest.fail(
                f"pywrangler dev exited early with code {process.returncode}\n"
                f"stdout: {log_path.read_text(errors='replace')}"
            )
        try:
            resp = requests.get(f"{base_url}/health", timeout=2)
            if resp.ok:
                return
        except (requests.ConnectionError, requests.Timeout):
            pass
        time.sleep(DEV_POLL_INTERVAL)

    process.kill()
    process.wait()
    pytest.fail(f"pywrangler dev did not become ready within {DEV_STARTUP_TIMEOUT}s")


@pytest.fixture(
    scope="module",
    params=COMPAT_CONFIGS,
    ids=[c.python_version for c in COMPAT_CONFIGS],
)
def compat_config(request: pytest.FixtureRequest) -> CompatConfig:
    return request.param


@pytest.fixture(scope="module")
def worker_project_dir() -> Path:
    """Worker project the `dev_server` fixture should serve.

    Test modules using `dev_server` must override this fixture.
    """
    raise NotImplementedError(
        "override the `worker_project_dir` fixture in your test module"
    )


@pytest.fixture(scope="module")
def dev_server(
    tmp_path_factory: pytest.TempPathFactory,
    worker_project_dir: Path,
    compat_config: CompatConfig,
) -> Generator[str]:
    """Start a pywrangler dev server on a free port and yield its base URL."""
    tmp_path = tmp_path_factory.mktemp(f"{worker_project_dir.name}_dev")
    target = tmp_path / worker_project_dir.name
    shutil.copytree(worker_project_dir, target, ignore=shutil.ignore_patterns(".venv"))
    env = os.environ | {"_PYODIDE_EXTRA_MOUNTS": str(tmp_path)}

    wrangler_jsonc = target / "wrangler.jsonc"
    replace_compat_date(wrangler_jsonc, compat_config.compat_date)
    inject_compat_flags(wrangler_jsonc, compat_config.extra_compat_flags)

    pywrangler_cmd = ["uv", "run", "--no-project", "--with", WORKERS_PY, "pywrangler"]

    subprocess.run(
        [*pywrangler_cmd, "sync"],
        cwd=target,
        check=True,
        env=env,
    )

    shutil.copytree(WORKERS_RUNTIME_SDK, target / "python_modules", dirs_exist_ok=True)

    port: int = get_free_port()
    base_url: str = f"http://127.0.0.1:{port}"

    log_path = tmp_path / "dev.log"
    with log_path.open("w") as log_file:
        process = subprocess.Popen(
            [
                *pywrangler_cmd,
                "dev",
                "--port",
                str(port),
                "--persist-to",
                str(tmp_path / "state"),
            ],
            cwd=target,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
        )

        wait_for_ready(process, base_url, log_path)
        yield base_url

        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@functools.cache
def get_suite_results(dev_server: str, suite: str) -> SuiteResults | str:
    try:
        resp = requests.get(
            f"{dev_server}/run-tests/{suite}",
            timeout=(SUITE_CONNECT_TIMEOUT, SUITE_READ_TIMEOUT),
        )
    except requests.RequestException as error:
        return f"Suite '{suite}' request failed: {error}"
    if not resp.ok:
        return f"Suite '{suite}' returned {resp.status_code}: {resp.text}"
    return resp.json()


def _make_test(suite: str, test_name: str) -> Callable:
    def test_fn(self: Any, dev_server: str) -> None:
        results = get_suite_results(dev_server, suite)
        if isinstance(results, str):
            pytest.fail(results)
            return
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


def make_suite_class(suite: str, tests: list[str]) -> type:
    """Build a test class with one method per in-worker test of `suite`."""
    return type(
        f"Test{suite.upper()}",
        (),
        {f"test_{name}": _make_test(suite, name) for name in tests},
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
    """Map each ``test_<suite>.py`` module in `src_dir` to its discovered test names."""
    return {
        module_path.stem[len("test_") :]: discover_test_names(module_path)
        for module_path in sorted(src_dir.glob("test_*.py"))
    }


def register_in_worker_suites(
    namespace: dict[str, Any],
    src_dir: Path,
    marks: dict[str, pytest.MarkDecorator] | None = None,
) -> None:
    """Define a ``TestXxx`` class in `namespace` for every suite found in `src_dir`.

    Call with ``globals()`` from a test module so each in-worker test surfaces as
    its own pytest case without manual registration. `marks` applies a marker to
    the class generated for the suite of the same name.
    """
    for suite, test_names in discover_suites(src_dir).items():
        suite_cls = make_suite_class(suite, test_names)
        if marks and suite in marks:
            suite_cls = marks[suite](suite_cls)
        namespace[suite_cls.__name__] = suite_cls
