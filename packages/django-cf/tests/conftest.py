"""Host-side fixtures that serve the test workers with ``pywrangler dev``."""

# pyright: reportMissingImports=false, reportMissingModuleSource=false

import os
import shutil
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
import requests
from testlib.host import (
    COMPAT_CONFIGS,
    GENERATED_FILE_PATTERN,
    CompatConfig,
    dev_server,
    pywrangler_sync,
    run_dev_server,
)
from testlib.host import (
    register_in_worker_suites as register_testlib_suites,
)

__all__ = ["dev_server"]

TEST_DIR: Path = Path(__file__).parent
PACKAGE_DIR: Path = TEST_DIR.parent
DJANGO_CF_SRC: Path = PACKAGE_DIR / "django_cf"

D1_PROJECT: Path = PACKAGE_DIR / "templates" / "d1"
DURABLE_OBJECTS_PROJECT: Path = PACKAGE_DIR / "templates" / "durable-objects"
R2_PROJECT: Path = TEST_DIR / "servers" / "r2"

DEV_STARTUP_TIMEOUT: int = 240
SEED_TIMEOUT: int = 180


@dataclass(frozen=True)
class DevServer:
    base_url: str


def _fail(log_path: Path, message: str) -> None:
    pytest.fail(
        f"{message}\n\n--- pywrangler dev log ---\n{log_path.read_text(errors='replace')}"
    )


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
    shutil.copytree(project_dir, target, ignore=GENERATED_FILE_PATTERN)

    env = os.environ | {"WORKERS_CI": "1"}
    pywrangler_sync(target, env)

    # These are deployable example apps, so their pyproject.toml depends on the
    # released django-cf from PyPI. Tests must exercise the working tree instead.
    vendored = target / "python_modules" / "django_cf"
    shutil.rmtree(vendored, ignore_errors=True)
    shutil.copytree(
        DJANGO_CF_SRC, vendored, ignore=shutil.ignore_patterns("__pycache__")
    )

    with run_dev_server(
        target,
        tmp_path,
        env,
        startup_timeout=DEV_STARTUP_TIMEOUT,
    ) as (base_url, log_path):
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
def dev_startup_timeout():
    return DEV_STARTUP_TIMEOUT


def register_in_worker_suites(namespace: dict, src_dir: Path) -> None:
    register_testlib_suites(namespace, src_dir, source_roots=[PACKAGE_DIR])
