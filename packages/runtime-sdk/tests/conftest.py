"""Shared fixtures and helpers for the host-side test suite."""

import os
import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from testlib.host import (
    COMPAT_CONFIGS,
    CompatConfig,
    configure_compatibility,
)
from testlib.host import (
    dev_server as run_dev_server,
)
from testlib.host import (
    register_in_worker_suites as register_testlib_suites,
)

TEST_DIR: Path = Path(__file__).parent
WORKERS_PY: Path = TEST_DIR.parent.parent / "cli"
WORKERS_RUNTIME_SDK: Path = TEST_DIR.parent / "src"
TESTLIB: Path = TEST_DIR.parent.parent / "testlib"

DEV_STARTUP_TIMEOUT: int = 120
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


@pytest.fixture(scope="session", autouse=True)
def build_testlib():
    subprocess.run(["uv", "build"], cwd=TESTLIB, check=True)


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
    shutil.copytree(TESTLIB, tmp_path / "testlib")
    env = os.environ | {"_PYODIDE_EXTRA_MOUNTS": str(tmp_path)}

    wrangler_jsonc = target / "wrangler.jsonc"
    configure_compatibility(wrangler_jsonc, compat_config)

    pywrangler_cmd = ["uv", "run", "--no-project", "--with", WORKERS_PY, "pywrangler"]

    subprocess.run(
        [*pywrangler_cmd, "sync"],
        cwd=target,
        check=True,
        env=env,
    )

    shutil.copytree(WORKERS_RUNTIME_SDK, target / "python_modules", dirs_exist_ok=True)

    with run_dev_server(
        target,
        tmp_path,
        env,
        pywrangler_cmd,
        startup_timeout=DEV_STARTUP_TIMEOUT,
        readiness_path="/health",
        require_success=True,
        log_name="dev.log",
    ) as (base_url, _):
        yield base_url


def register_in_worker_suites(
    namespace: dict[str, Any],
    src_dir: Path,
    marks: dict[str, pytest.MarkDecorator] | None = None,
) -> None:
    register_testlib_suites(namespace, src_dir, marks=marks, class_name=str.upper)
