"""Host-side fixtures that serve the test workers with ``pywrangler dev``."""

# pyright: reportMissingImports=false, reportMissingModuleSource=false

import os
import shutil
import subprocess
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
import requests
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
PACKAGE_DIR: Path = TEST_DIR.parent
WORKERS_PY: Path = PACKAGE_DIR.parent / "cli"
WORKERS_RUNTIME_SDK: Path = PACKAGE_DIR.parent / "runtime-sdk" / "src"
TESTLIB: Path = PACKAGE_DIR.parent / "testlib"
DJANGO_CF_SRC: Path = PACKAGE_DIR / "django_cf"

D1_PROJECT: Path = PACKAGE_DIR / "templates" / "d1"
DURABLE_OBJECTS_PROJECT: Path = PACKAGE_DIR / "templates" / "durable-objects"
R2_PROJECT: Path = TEST_DIR / "servers" / "r2"
IN_WORKER_PROJECT: Path = TEST_DIR / "in_worker" / "worker"

DEV_STARTUP_TIMEOUT: int = 240
SEED_TIMEOUT: int = 180
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

    with run_dev_server(
        target,
        tmp_path,
        env,
        pywrangler,
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
def dev_server(
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
    shutil.copytree(TESTLIB, tmp_path / "testlib", ignore=GENERATED)

    wrangler_jsonc = target / "wrangler.jsonc"
    configure_compatibility(wrangler_jsonc, compat_config)

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

    with run_dev_server(
        target,
        tmp_path,
        env,
        pywrangler,
        startup_timeout=DEV_STARTUP_TIMEOUT,
    ) as (base_url, _):
        yield base_url


def register_in_worker_suites(namespace: dict, src_dir: Path) -> None:
    register_testlib_suites(namespace, src_dir)
