"""Host-side helpers for tests that run pytest inside workerd."""

import ast
import contextlib
import functools
import os
import signal
import socket
import subprocess
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict

import pytest
import requests

SUITE_CONNECT_TIMEOUT = 10
SUITE_READ_TIMEOUT = 300


@dataclass(frozen=True)
class CompatConfig:
    compat_date: str
    python_version: str
    extra_compat_flags: list[str] = field(default_factory=list)


COMPAT_CONFIGS = [
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
        # TODO: remove these when 3.14 is stable and enabled by date.
        extra_compat_flags=["python_workers_314", "experimental"],
    ),
]


def configure_compatibility(file: Path, config: CompatConfig) -> None:
    content = file.read_text().replace("%COMPAT_DATE", config.compat_date)
    for flag in config.extra_compat_flags:
        content = content.replace('"python_workers"', f'"python_workers", "{flag}"')
    file.write_text(content)


class InWorkerTestResult(TypedDict):
    status: Literal["passed", "failed", "error", "skipped"]
    error: str
    traceback: str
    reason: str


SuiteResults = dict[str, InWorkerTestResult]


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _fail(log_path: Path, message: str) -> None:
    pytest.fail(
        f"{message}\n\n--- pywrangler dev log ---\n"
        f"{log_path.read_text(errors='replace')}"
    )


def wait_for_ready(  # noqa: PLR0913
    process: subprocess.Popen[bytes],
    base_url: str,
    log_path: Path,
    *,
    timeout: int,
    path: str = "",
    require_success: bool = False,
    poll_interval: float = 0.5,
) -> None:
    """Block until the worker responds according to the configured policy."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _fail(
                log_path, f"pywrangler dev exited early with code {process.returncode}"
            )
        try:
            response = requests.get(f"{base_url}{path}", timeout=5)
            if not require_success or response.ok:
                return
        except requests.RequestException:
            pass
        time.sleep(poll_interval)

    _fail(log_path, f"pywrangler dev was not ready within {timeout}s")


def _terminate(process: subprocess.Popen[bytes], timeout: int) -> None:
    if process.poll() is not None:
        return
    group = os.getpgid(process.pid)
    os.killpg(group, signal.SIGTERM)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(group, signal.SIGKILL)
        process.wait()


@contextlib.contextmanager
def dev_server(
    target: Path,
    tmp_path: Path,
    env: dict[str, str],
    pywrangler: list[str],
    *,
    startup_timeout: int,
    readiness_path: str = "",
    require_success: bool = False,
    teardown_timeout: int = 10,
    log_name: str | None = None,
) -> Generator[tuple[str, Path]]:
    """Run ``pywrangler dev`` and yield its base URL and log path."""
    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = tmp_path / (log_name or f"{target.name}-dev.log")

    with log_path.open("w") as log_file:
        process = subprocess.Popen(
            [
                *pywrangler,
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
            start_new_session=True,
        )
        try:
            wait_for_ready(
                process,
                base_url,
                log_path,
                timeout=startup_timeout,
                path=readiness_path,
                require_success=require_success,
            )
            yield base_url, log_path
        finally:
            _terminate(process, teardown_timeout)


@functools.cache
def get_suite_results(server: str, suite: str) -> SuiteResults | str:
    try:
        response = requests.get(
            f"{server}/run-tests/{suite}",
            timeout=(SUITE_CONNECT_TIMEOUT, SUITE_READ_TIMEOUT),
        )
    except requests.RequestException as error:
        return f"Suite '{suite}' request failed: {error}"
    if not response.ok:
        return f"Suite '{suite}' returned {response.status_code}: {response.text}"
    return response.json()


def _make_test(suite: str, test_name: str) -> Callable:
    def test_fn(self: Any, dev_server: str) -> None:
        results = get_suite_results(dev_server, suite)
        if isinstance(results, str):
            pytest.fail(results)
        result = results.get(test_name)
        assert result is not None, (
            f"Test {suite}::{test_name} not found in results; "
            f"available keys: {sorted(results)}"
        )
        if result["status"] == "skipped":
            pytest.skip(result.get("reason", ""))
        if result["status"] == "failed":
            pytest.fail(result["error"])
        if result["status"] == "error":
            pytest.fail(f"{result['error']}\n{result.get('traceback', '')}")

    test_fn.__name__ = f"test_{test_name}"
    return test_fn


def _normalize_test_name(*parts: str) -> str:
    return "__".join(part.removeprefix("test_") for part in parts)


def discover_test_names(module_path: Path) -> list[str]:
    tree = ast.parse(module_path.read_text())
    names = []
    for node in tree.body:
        if isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef
        ) and node.name.startswith("test_"):
            names.append(_normalize_test_name(node.name))
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(
                    child, ast.FunctionDef | ast.AsyncFunctionDef
                ) and child.name.startswith("test_"):
                    names.append(_normalize_test_name(node.name, child.name))  # noqa: PERF401
    return names


def register_in_worker_suites(
    namespace: dict[str, Any],
    src_dir: Path,
    *,
    marks: dict[str, pytest.MarkDecorator] | None = None,
    class_name: Callable[[str], str] | None = None,
) -> None:
    """Expose each in-worker test as an individual host-side pytest test."""
    for module_path in sorted(src_dir.glob("test_*.py")):
        suite = module_path.stem[len("test_") :]
        generated_class_name = (
            class_name(suite)
            if class_name
            else "".join(part.title() for part in suite.split("_"))
        )
        suite_cls = type(
            f"Test{generated_class_name}",
            (),
            {
                f"test_{name}": _make_test(suite, name)
                for name in discover_test_names(module_path)
            },
        )
        if marks and suite in marks:
            suite_cls = marks[suite](suite_cls)
        namespace[suite_cls.__name__] = suite_cls
