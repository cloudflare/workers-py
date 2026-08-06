"""Host-side fixtures that serve the test workers with ``pywrangler dev``.

Ported from ``packages/runtime-sdk/tests/conftest.py``. Unlike that copy, the
servers run in uv *project* mode: each worker's ``wrangler.jsonc`` declares a
``build.command`` that shells out to ``python manage.py collectstatic``, which
needs the project's own virtualenv on PATH. ``uv run --no-project`` would leave
Django unimportable and the build would fail before the worker starts.
"""

import os
import shutil
import signal
import socket
import subprocess
import time
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
import requests

TEST_DIR: Path = Path(__file__).parent
PACKAGE_DIR: Path = TEST_DIR.parent
WORKERS_PY: Path = PACKAGE_DIR.parent / "cli"
DJANGO_CF_SRC: Path = PACKAGE_DIR / "django_cf"

D1_PROJECT: Path = PACKAGE_DIR / "templates" / "d1"
DURABLE_OBJECTS_PROJECT: Path = PACKAGE_DIR / "templates" / "durable-objects"
R2_PROJECT: Path = TEST_DIR / "servers" / "r2"

DEV_STARTUP_TIMEOUT: int = 240
DEV_POLL_INTERVAL: float = 0.5
SEED_TIMEOUT: int = 180
TEARDOWN_TIMEOUT: int = 10

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


def _fail(process: subprocess.Popen[bytes], log_path: Path, message: str) -> None:
    _terminate(process)
    pytest.fail(
        f"{message}\n\n--- pywrangler dev log ---\n{log_path.read_text(errors='replace')}"
    )


def _wait_for_ready(
    process: subprocess.Popen[bytes], base_url: str, log_path: Path
) -> None:
    deadline = time.monotonic() + DEV_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _fail(
                process,
                log_path,
                f"pywrangler dev exited early with code {process.returncode}",
            )
        try:
            requests.get(base_url, timeout=5)
            return
        except requests.RequestException:
            time.sleep(DEV_POLL_INTERVAL)

    _fail(
        process, log_path, f"pywrangler dev was not ready within {DEV_STARTUP_TIMEOUT}s"
    )


def _seed(base_url: str, process: subprocess.Popen[bytes], log_path: Path) -> None:
    for endpoint in ("__run_migrations__", "__create_admin__"):
        try:
            response = requests.get(f"{base_url}/{endpoint}/", timeout=SEED_TIMEOUT)
        except requests.RequestException as error:
            _fail(process, log_path, f"GET /{endpoint}/ failed: {error}")
        if response.status_code != 200:
            _fail(
                process,
                log_path,
                f"GET /{endpoint}/ returned {response.status_code}: {response.text[:2000]}",
            )
        payload = response.json()
        if payload.get("status") == "error":
            _fail(
                process,
                log_path,
                f"GET /{endpoint}/ reported: {payload.get('message')}",
            )


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

    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = tmp_path / f"{project_dir.name}-dev.log"

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
            _seed(base_url, process, log_path)
            yield DevServer(base_url)
        finally:
            _terminate(process)


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
