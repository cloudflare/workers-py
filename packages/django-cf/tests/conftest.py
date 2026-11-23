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
    GENERATED_FILE_PATTERN,
    compat_config,
    dev_server,
    fail_with_log,
    pywrangler_sync,
    run_dev_server,
    worker_project_dir,
)

# Re-export fixtures so pytest discovers them
__all__ = ["compat_config", "dev_server", "worker_project_dir"]

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


def _seed(base_url: str, log_path: Path) -> None:
    for endpoint in ("__run_migrations__", "__create_admin__"):
        try:
            response = requests.get(f"{base_url}/{endpoint}/", timeout=SEED_TIMEOUT)
        except requests.RequestException as error:
            fail_with_log(log_path, f"GET /{endpoint}/ failed: {error}")
        else:
            if response.status_code != 200:
                fail_with_log(
                    log_path,
                    f"GET /{endpoint}/ returned {response.status_code}: {response.text[:2000]}",
                )
            payload = response.json()
            if payload.get("status") == "error":
                fail_with_log(
                    log_path, f"GET /{endpoint}/ reported: {payload.get('message')}"
                )


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


@pytest.fixture(scope="module")
def dev_startup_timeout() -> int:
    return DEV_STARTUP_TIMEOUT
