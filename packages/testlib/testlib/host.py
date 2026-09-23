"""Host-side helpers for tests that run pytest inside workerd."""

import ast
import contextlib
import functools
import os
import signal
import socket
import subprocess
import time
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

import pytest
import requests

from .tracebacks import WorkerException, load_exception

SUITE_CONNECT_TIMEOUT = 10
SUITE_READ_TIMEOUT = 300

# The monorepo's `packages/` directory.
PACKAGES: Path = Path(__file__).parents[2]
WORKERS_PY: Path = PACKAGES / "cli"
WORKERS_RUNTIME_SDK: Path = PACKAGES / "runtime-sdk/src"
PY_WRANGLER_CMD: list[str] = [
    "uv",
    "run",
    "--no-project",
    "--with",
    str(WORKERS_PY),
    "pywrangler",
]


def link_packages(tmp_path: Path) -> Path:
    """Symlink the monorepo's ``packages/`` directory into *tmp_path*.

    Worker test projects are copied to ``tmp_path/<name>`` before being synced,
    so their ``[tool.uv.sources]`` entries refer to the working-tree checkouts
    as ``../packages/<package>``. This makes those paths resolve, so
    ``pywrangler sync`` builds and vendors the local testlib, runtime-sdk and
    django-cf instead of the PyPI releases.
    """
    link = tmp_path / "packages"
    link.symlink_to(PACKAGES, target_is_directory=True)
    return link


def pywrangler_sync(cwd: Path, env: dict[str, str]) -> None:
    """Run ``pywrangler sync`` in *cwd*, failing the test with its output on error."""
    result = subprocess.run(
        [*PY_WRANGLER_CMD, "sync"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            f"pywrangler sync failed in {cwd}\n{result.stdout}\n{result.stderr}"
        )


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
    exception: NotRequired[WorkerException]


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
                *PY_WRANGLER_CMD,
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


def _make_test(
    suite: str, result_key: str, name: str, source_roots: Sequence[Path] = ()
) -> Callable:
    """Build a host test method that reports the in-worker result *result_key*."""

    def test_fn(self: Any, dev_server: str) -> None:
        # Hide this frame: the interesting traceback is the one from the worker.
        __tracebackhide__ = True
        results = get_suite_results(dev_server, suite)
        if isinstance(results, str):
            pytest.fail(results)
        result = results.get(result_key)
        assert result is not None, (
            f"Test {suite}::{result_key} not found in results; "
            f"available keys: {sorted(results)}"
        )
        if result["status"] == "skipped":
            pytest.skip(result.get("reason", ""))
        if result["status"] not in ("failed", "error"):
            return
        exception = result.get("exception")
        if exception is None:
            pytest.fail(f"{result['error']}\n{result.get('traceback', '')}".rstrip())
        exc = load_exception(exception, [*source_roots, WORKERS_RUNTIME_SDK])
        when = exception.get("when", "call")
        if when != "call":
            exc.add_note(f"raised in the worker during test {when}")
        raise exc

    test_fn.__name__ = name
    return test_fn


def _result_key(*parts: str) -> str:
    """Key under which ``ResultCollector`` (worker side) records a test.

    Must stay in sync with ``testlib.entrypoint.ResultCollector._key``.
    """
    return "__".join(part.removeprefix("test_") for part in parts)


def _is_test_def(node: ast.AST) -> bool:
    return isinstance(
        node, ast.FunctionDef | ast.AsyncFunctionDef
    ) and node.name.startswith("test_")


def discover_tests(module_path: Path) -> list[tuple[str | None, str]]:
    """Return ``(class_name, function_name)`` for each test in *module_path*.

    ``class_name`` is ``None`` for module-level test functions.
    """
    tree = ast.parse(module_path.read_text())
    tests: list[tuple[str | None, str]] = []
    for node in tree.body:
        if _is_test_def(node):
            tests.append((None, node.name))
        elif isinstance(node, ast.ClassDef):
            tests.extend(
                (node.name, child.name) for child in node.body if _is_test_def(child)
            )
    return tests


def _make_suite_class(
    module_path: Path, suite: str, source_roots: Sequence[Path]
) -> type:
    """Build a host class mirroring the structure of the in-worker test module.

    Module-level in-worker tests become methods; in-worker test classes become
    nested classes with the same names, so the host node IDs mirror the
    in-worker ones (``test_kv.py::TestFoo::test_bar``) and ``-k`` expressions
    select the same tests on both sides.
    """
    # ``__test__ = True`` makes pytest collect the class even though its name
    # (``test_kv.py``) doesn't match ``python_classes``.
    members: dict[str, Any] = {"__test__": True}
    nested: dict[str, dict[str, Any]] = {}
    for class_name, function_name in discover_tests(module_path):
        if class_name is None:
            key = _result_key(function_name)
            members[function_name] = _make_test(suite, key, function_name, source_roots)
        else:
            key = _result_key(class_name, function_name)
            nested.setdefault(class_name, {"__test__": True})[function_name] = (
                _make_test(suite, key, function_name, source_roots)
            )
    for class_name, class_members in nested.items():
        members[class_name] = type(class_name, (), class_members)
    return type(module_path.name, (), members)


def register_in_worker_suites(
    namespace: dict[str, Any],
    src_dir: Path,
    *,
    marks: dict[str, pytest.MarkDecorator] | None = None,
    source_roots: Sequence[Path] = (),
) -> None:
    """Expose each in-worker test as an individual host-side pytest test.

    Each ``test_<suite>.py`` in *src_dir* is registered in *namespace* under
    its file name, so host node IDs mirror the in-worker ones, e.g.
    ``tests/test_bindings.py::test_kv.py::test_get[3.12]`` for the in-worker
    ``test_kv.py::test_get``.

    ``source_roots`` lists extra host directories (besides ``src_dir``) that
    hold copies of code running inside the worker, e.g. a package's source
    tree that gets vendored into ``python_modules``. Traceback frames from
    the worker are remapped onto them so pytest can show source lines.
    """
    roots = (src_dir, *source_roots)
    for module_path in sorted(src_dir.glob("test_*.py")):
        suite = module_path.stem[len("test_") :]
        suite_cls = _make_suite_class(module_path, suite, roots)
        if marks and suite in marks:
            suite_cls = marks[suite](suite_cls)
        namespace[module_path.name] = suite_cls
