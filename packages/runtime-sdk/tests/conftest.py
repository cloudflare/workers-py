"""Shared fixtures and helpers for the host-side test suite."""

from pathlib import Path
from typing import Any

import pytest
from testlib.host import (
    COMPAT_CONFIGS,
    CompatConfig,
    dev_server,
)
from testlib.host import (
    register_in_worker_suites as register_testlib_suites,
)

__all__ = ["dev_server"]


TEST_DIR: Path = Path(__file__).parent

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
    return 120


def register_in_worker_suites(
    namespace: dict[str, Any],
    src_dir: Path,
    marks: dict[str, pytest.MarkDecorator] | None = None,
) -> None:
    register_testlib_suites(
        namespace,
        src_dir,
        marks=marks,
        class_name=str.upper,
    )
