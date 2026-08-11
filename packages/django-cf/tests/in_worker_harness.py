"""Helpers for django-cf suites that execute pytest inside workerd."""

# pyright: reportMissingImports=false, reportMissingModuleSource=false

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
PACKAGE_DIR: Path = TEST_DIR.parent
WORKERS_PY: Path = PACKAGE_DIR.parent / "cli"
WORKERS_RUNTIME_SDK: Path = PACKAGE_DIR.parent / "runtime-sdk" / "src"
DJANGO_CF_SRC: Path = PACKAGE_DIR / "django_cf"

DEV_STARTUP_TIMEOUT: int = 120
DEV_POLL_INTERVAL: float = 0.5
SUITE_CONNECT_TIMEOUT: int = 10
SUITE_READ_TIMEOUT: int = 300


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
        extra_compat_flags=["python_workers_20260610", "experimental"],
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
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_ready(
    process: subprocess.Popen[bytes], base_url: str, log_path: Path
) -> None:
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
    raise NotImplementedError(
        "override the `worker_project_dir` fixture in your test module"
    )


@pytest.fixture(scope="module")
def dev_server(
    tmp_path_factory: pytest.TempPathFactory,
    worker_project_dir: Path,
    compat_config: CompatConfig,
) -> Generator[str]:
    tmp_path = tmp_path_factory.mktemp(f"{worker_project_dir.name}_dev")
    target = tmp_path / worker_project_dir.name
    shutil.copytree(
        worker_project_dir,
        target,
        ignore=shutil.ignore_patterns(
            ".venv", ".venv-workers", ".wrangler", "__pycache__", "node_modules"
        ),
    )
    env = os.environ | {"_PYODIDE_EXTRA_MOUNTS": str(tmp_path)}

    wrangler_jsonc = target / "wrangler.jsonc"
    replace_compat_date(wrangler_jsonc, compat_config.compat_date)
    inject_compat_flags(wrangler_jsonc, compat_config.extra_compat_flags)

    pywrangler_cmd = [
        "uv",
        "run",
        "--frozen",
        "--no-project",
        "--with",
        str(WORKERS_PY),
        "pywrangler",
    ]

    subprocess.run(
        [*pywrangler_cmd, "sync"],
        cwd=target,
        check=True,
        env=env,
    )

    shutil.copytree(WORKERS_RUNTIME_SDK, target / "python_modules", dirs_exist_ok=True)
    shutil.copytree(
        DJANGO_CF_SRC,
        target / "python_modules" / "django_cf",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )

    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"

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
        assert result is not None, (
            f"Test {suite}::{test_name} not found in results; "
            f"available keys: {sorted(results)}"
        )
        if result["status"] == "skipped":
            pytest.skip(result.get("reason", ""))
        elif result["status"] == "failed":
            pytest.fail(result["error"])
        elif result["status"] == "error":
            pytest.fail(f"{result['error']}\n{result.get('traceback', '')}")

    test_fn.__name__ = f"test_{test_name}"
    return test_fn


def make_suite_class(suite: str, tests: list[str]) -> type:
    return type(
        f"Test{suite.upper()}",
        (),
        {f"test_{name}": _make_test(suite, name) for name in tests},
    )


def _normalize_test_name(*parts: str) -> str:
    normalized = []
    for part in parts:
        normalized.append(part[len("test_") :] if part.startswith("test_") else part)
    return "__".join(normalized)


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
                    names.append(_normalize_test_name(node.name, child.name))
    return names


def discover_suites(src_dir: Path) -> dict[str, list[str]]:
    return {
        module_path.stem[len("test_") :]: discover_test_names(module_path)
        for module_path in sorted(src_dir.glob("test_*.py"))
    }


def register_in_worker_suites(namespace: dict[str, Any], src_dir: Path) -> None:
    for suite, test_names in discover_suites(src_dir).items():
        suite_cls = make_suite_class(suite, test_names)
        namespace[suite_cls.__name__] = suite_cls
