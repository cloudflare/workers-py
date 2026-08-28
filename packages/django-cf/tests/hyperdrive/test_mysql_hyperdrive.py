r"""Host-side mirror of the Hyperdrive suite that runs inside workerd.

Opt-in: needs a MySQL 8 server on 127.0.0.1:3306 and is skipped unless the run
asks for it explicitly.

    docker run --rm -d --name workers-py-mysql-probe \
      -e MYSQL_ROOT_PASSWORD=rootpass -e MYSQL_DATABASE=testdb \
      -e MYSQL_USER=testuser -e MYSQL_PASSWORD=testpass \
      -p 3306:3306 mysql:8.4

    uv run --frozen pytest -m mysql tests
"""

# pyright: reportMissingImports=false, reportMissingModuleSource=false

from collections.abc import Generator
from pathlib import Path

import pytest

from tests.conftest import register_in_worker_suites

MYSQL_SRC_DIR: Path = Path(__file__).parent / "worker" / "src"

pytestmark = pytest.mark.hyperdrive


@pytest.fixture(scope="module")
def in_worker_server(mysql_hyperdrive_server: str) -> Generator[str]:
    """Name the generated cases expect; this suite has its own worker project."""
    yield mysql_hyperdrive_server


register_in_worker_suites(globals(), MYSQL_SRC_DIR)
