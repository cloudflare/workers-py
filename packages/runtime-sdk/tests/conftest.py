"""Shared fixtures and helpers for the host-side test suite."""

import pytest
from testlib.host import (
    compat_config,
    dev_server,
    dev_startup_timeout,
    worker_project_dir,
)

# Re-export fixtures so pytest discovers them
__all__ = ["compat_config", "dev_server", "dev_startup_timeout", "worker_project_dir"]

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
