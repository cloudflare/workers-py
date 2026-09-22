# pyright: reportAttributeAccessIssue=false, reportMissingImports=false

"""Stock Django database backends running through Hyperdrive in workerd."""

from pathlib import Path

import pytest
from conftest import COMPAT_CONFIGS, CompatConfig, register_in_worker_suites

DJANGO_DATABASES_DIR: Path = (
    Path(__file__).parent / "web-frameworks-test" / "django-databases"
)
DJANGO_DATABASES_SRC_DIR: Path = DJANGO_DATABASES_DIR / "src"
PYTHON_314_CONFIGS = [
    config for config in COMPAT_CONFIGS if config.python_version == "3.14"
]
SUITE_MARKS: dict[str, pytest.MarkDecorator] = {
    "postgresql": pytest.mark.hyperdrive,
    "mysql": pytest.mark.hyperdrive,
}


@pytest.fixture(scope="module")
def worker_project_dir() -> Path:
    return DJANGO_DATABASES_DIR


@pytest.fixture(
    scope="module",
    params=PYTHON_314_CONFIGS,
    ids=[config.python_version for config in PYTHON_314_CONFIGS],
)
def compat_config(request: pytest.FixtureRequest) -> CompatConfig:
    return request.param


register_in_worker_suites(globals(), DJANGO_DATABASES_SRC_DIR, marks=SUITE_MARKS)
