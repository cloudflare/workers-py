"""Host-side fixtures that serve the test workers with ``pywrangler dev``.

TODO: reduce the duplication between this file and packages/runtime-sdk/tests/conftest.py
"""

# pyright: reportMissingImports=false, reportMissingModuleSource=false

import ast
import contextlib
import functools
import os
import shutil
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

TEST_DIR: Path = Path(__file__).parent
PACKAGE_DIR: Path = TEST_DIR.parent
WORKERS_PY: Path = PACKAGE_DIR.parent / "cli"
WORKERS_RUNTIME_SDK: Path = PACKAGE_DIR.parent / "runtime-sdk" / "src"
DJANGO_CF_SRC: Path = PACKAGE_DIR / "django_cf"

D1_PROJECT: Path = PACKAGE_DIR / "templates" / "d1"
DURABLE_OBJECTS_PROJECT: Path = PACKAGE_DIR / "templates" / "durable-objects"
R2_PROJECT: Path = TEST_DIR / "servers" / "r2"
IN_WORKER_PROJECT: Path = TEST_DIR / "in_worker" / "worker"

DEV_STARTUP_TIMEOUT: int = 240
DEV_POLL_INTERVAL: float = 0.5
SEED_TIMEOUT: int = 180
TEARDOWN_TIMEOUT: int = 10
SUITE_CONNECT_TIMEOUT: int = 10
SUITE_READ_TIMEOUT: int = 300

GENERATED = shutil.ignore_patterns(
    ".venv",
    ".venv-workers",
    ".wrangler",
    "__pycache__",
    "node_modules",
    "python_modules",
    "staticfiles",
)


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
        extra_compat_flags=["python_workers_20260610", "experimental"],
    ),
]


@dataclass(frozen=True)
class DevServer:
    base_url: str


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    # `pywrangler dev` spawns npx -> wrangler -> workerd; signalling the group
    # is the only way to avoid orphaning workerd.
    group = os.getpgid(process.pid)
    os.killpg(group, signal.SIGTERM)
    try:
        process.wait(timeout=TEARDOWN_TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(group, signal.SIGKILL)
        process.wait()


def _fail(log_path: Path, message: str) -> None:
    # Callers run inside `_dev_server`, whose finally block stops the worker.
    pytest.fail(
        f"{message}\n\n--- pywrangler dev log ---\n{log_path.read_text(errors='replace')}"
    )


def _wait_for_ready(
    process: subprocess.Popen[bytes], base_url: str, log_path: Path
) -> None:
    """Block until the worker answers.

    Any status counts: a 404 still proves workerd loaded the script and is
    routing requests.
    """
    deadline = time.monotonic() + DEV_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _fail(
                log_path, f"pywrangler dev exited early with code {process.returncode}"
            )
        try:
            requests.get(base_url, timeout=5)
            return
        except requests.RequestException:
            time.sleep(DEV_POLL_INTERVAL)

    _fail(log_path, f"pywrangler dev was not ready within {DEV_STARTUP_TIMEOUT}s")


@contextlib.contextmanager
def _dev_server(
    target: Path, tmp_path: Path, env: dict[str, str], pywrangler: list[str]
) -> Generator[tuple[str, Path]]:
    """Run `pywrangler dev` on a free port, yielding its base URL and log path."""
    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = tmp_path / f"{target.name}-dev.log"

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
            _wait_for_ready(process, base_url, log_path)
            yield base_url, log_path
        finally:
            _terminate(process)


def _seed(base_url: str, log_path: Path) -> None:
    for endpoint in ("__run_migrations__", "__create_admin__"):
        try:
            response = requests.get(f"{base_url}/{endpoint}/", timeout=SEED_TIMEOUT)
        except requests.RequestException as error:
            _fail(log_path, f"GET /{endpoint}/ failed: {error}")
        else:
            if response.status_code != 200:
                _fail(
                    log_path,
                    f"GET /{endpoint}/ returned {response.status_code}: {response.text[:2000]}",
                )
            payload = response.json()
            if payload.get("status") == "error":
                _fail(log_path, f"GET /{endpoint}/ reported: {payload.get('message')}")


def _serve(project_dir: Path, tmp_path: Path) -> Generator[DevServer]:
    target = tmp_path / project_dir.name
    shutil.copytree(project_dir, target, ignore=GENERATED)

    pywrangler = ["uv", "run", "--with", str(WORKERS_PY), "pywrangler"]
    env = os.environ | {"WORKERS_CI": "1"}

    sync = subprocess.run(
        [*pywrangler, "sync"],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if sync.returncode != 0:
        pytest.fail(
            f"pywrangler sync failed for {project_dir.name}\n{sync.stdout}\n{sync.stderr}"
        )

    # `sync` vendors the released django-cf from PyPI; tests must exercise the
    # working tree instead.
    vendored = target / "python_modules" / "django_cf"
    shutil.rmtree(vendored, ignore_errors=True)
    shutil.copytree(
        DJANGO_CF_SRC, vendored, ignore=shutil.ignore_patterns("__pycache__")
    )

    with _dev_server(target, tmp_path, env, pywrangler) as (base_url, log_path):
        _seed(base_url, log_path)
        yield DevServer(base_url)


@pytest.fixture(scope="session")
def d1_web_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[DevServer]:
    yield from _serve(D1_PROJECT, tmp_path_factory.mktemp("d1"))


@pytest.fixture(scope="session")
def durable_objects_web_server(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[DevServer]:
    yield from _serve(
        DURABLE_OBJECTS_PROJECT, tmp_path_factory.mktemp("durable_objects")
    )


@pytest.fixture(scope="session")
def r2_web_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[DevServer]:
    yield from _serve(R2_PROJECT, tmp_path_factory.mktemp("r2"))


def replace_compat_date(file: Path, compat_date: str) -> None:
    file.write_text(file.read_text().replace("%COMPAT_DATE", compat_date))


def inject_compat_flags(file: Path, extra_flags: list[str]) -> None:
    if not extra_flags:
        return
    content = file.read_text()
    for flag in extra_flags:
        content = content.replace('"python_workers"', f'"python_workers", "{flag}"')
    file.write_text(content)


@pytest.fixture(
    scope="module",
    params=COMPAT_CONFIGS,
    ids=[c.python_version for c in COMPAT_CONFIGS],
)
def compat_config(request: pytest.FixtureRequest) -> CompatConfig:
    return request.param


@pytest.fixture(scope="module")
def in_worker_server(
    tmp_path_factory: pytest.TempPathFactory, compat_config: CompatConfig
) -> Generator[str]:
    """Serve ``tests/in_worker/worker``, once per compat config.

    Unlike the app fixtures above, this one runs ``uv run --no-project`` and
    vendors the runtime SDK and django-cf working trees by hand: the worker has
    no Django project to build, it only needs the two libraries importable.
    """
    tmp_path = tmp_path_factory.mktemp("in_worker")
    target = tmp_path / IN_WORKER_PROJECT.name
    shutil.copytree(IN_WORKER_PROJECT, target, ignore=GENERATED)

    wrangler_jsonc = target / "wrangler.jsonc"
    replace_compat_date(wrangler_jsonc, compat_config.compat_date)
    inject_compat_flags(wrangler_jsonc, compat_config.extra_compat_flags)

    pywrangler = [
        "uv",
        "run",
        "--frozen",
        "--no-project",
        "--with",
        str(WORKERS_PY),
        "pywrangler",
    ]
    env = os.environ | {"_PYODIDE_EXTRA_MOUNTS": str(tmp_path)}

    subprocess.run([*pywrangler, "sync"], cwd=target, check=True, env=env)

    shutil.copytree(WORKERS_RUNTIME_SDK, target / "python_modules", dirs_exist_ok=True)
    shutil.copytree(
        DJANGO_CF_SRC,
        target / "python_modules" / "django_cf",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )

    with _dev_server(target, tmp_path, env, pywrangler) as (base_url, _):
        yield base_url


class InWorkerTestResult(TypedDict):
    status: Literal["passed", "failed", "error", "skipped"]
    error: str
    traceback: str
    reason: str


SuiteResults = dict[str, InWorkerTestResult]


@functools.cache
def get_suite_results(in_worker_server: str, suite: str) -> SuiteResults | str:
    try:
        resp = requests.get(
            f"{in_worker_server}/run-tests/{suite}",
            timeout=(SUITE_CONNECT_TIMEOUT, SUITE_READ_TIMEOUT),
        )
    except requests.RequestException as error:
        return f"Suite '{suite}' request failed: {error}"
    if not resp.ok:
        return f"Suite '{suite}' returned {resp.status_code}: {resp.text}"
    return resp.json()


def _make_test(suite: str, test_name: str) -> Callable:
    def test_fn(self: Any, in_worker_server: str) -> None:
        results = get_suite_results(in_worker_server, suite)
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
    camel = "".join(part.title() for part in suite.split("_"))
    return type(
        f"Test{camel}",
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
