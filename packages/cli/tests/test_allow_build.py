"""Tests for the ``--allow-build`` override

By default pywrangler resolves and installs the worker environment with
``--no-build`` so only prebuilt wheels are used. This is because building a
Pyodide binary wheel will fail.

The ``allow-build`` override drops ``--no-build`` so source distributions and
local directory sources can be built.
"""

from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import pywrangler.resolve as pywrangler_resolve
import pywrangler.sync as pywrangler_sync
import pywrangler.utils as pywrangler_utils
from pywrangler.cli import app
from pywrangler.resolve import InstallPlan


@pytest.fixture
def project(monkeypatch, tmp_path):
    """A minimal project dir with pyproject.toml + wrangler.jsonc discoverable."""
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        pywrangler_utils, "find_pyproject_toml", lambda: tmp_path / "pyproject.toml"
    )
    (tmp_path / "wrangler.jsonc").write_text(
        dedent("""
        {
            "name": "test-worker",
            "main": "src/worker.py",
            "compatibility_date": "2023-10-30",
            "compatibility_flags": ["python_workers"]
        }
        """)
    )
    return tmp_path


def write_pyproject(project: Path, allow_build: bool | None = None) -> None:
    tool_section = ""
    if allow_build is not None:
        tool_section = dedent(f"""
            [tool.pywrangler]
            allow-build = {str(allow_build).lower()}
        """)
    (project / "pyproject.toml").write_text(
        dedent("""
        [project]
        name = "test-project"
        version = "0.1.0"
        requires-python = ">=3.12"
        dependencies = ["click"]
        """)
        + tool_section
    )


# ---------------------------------------------------------------------------
# Flag / config propagation into sync()
# ---------------------------------------------------------------------------


def _invoke_sync_capturing_allow_build(project: Path, args: list[str]):
    """Invoke `pywrangler <args>` with all heavy steps mocked out.

    Returns (result, resolve_mock, install_mock) so callers can assert on the
    ``allow_build`` value threaded into resolve/install.
    """
    plan = MagicMock()
    plan.requirements = [("click", "8.0.0")]

    with (
        patch.object(pywrangler_sync, "is_sync_needed", lambda: True),
        patch.object(pywrangler_sync, "check_wrangler_config"),
        patch.object(pywrangler_sync, "create_workers_venv"),
        patch.object(pywrangler_sync, "create_pyodide_venv"),
        patch.object(
            pywrangler_sync, "resolve_requirements", return_value=plan
        ) as resolve_mock,
        patch.object(pywrangler_sync, "install_requirements") as install_mock,
    ):
        runner = CliRunner()
        result = runner.invoke(app, args)
    return result, resolve_mock, install_mock


def test_allow_build_flag_enables_build(project):
    write_pyproject(project)
    result, resolve_mock, install_mock = _invoke_sync_capturing_allow_build(
        project, ["sync", "--allow-build"]
    )
    assert result.exit_code == 0, result.output
    assert resolve_mock.call_args.kwargs["allow_build"] is True
    assert install_mock.call_args.kwargs["allow_build"] is True


def test_default_disables_build(project):
    write_pyproject(project)  # no [tool.pywrangler]
    result, resolve_mock, install_mock = _invoke_sync_capturing_allow_build(
        project, ["sync"]
    )
    assert result.exit_code == 0, result.output
    assert resolve_mock.call_args.kwargs["allow_build"] is False
    assert install_mock.call_args.kwargs["allow_build"] is False


def test_no_allow_build_flag_disables_build(project):
    # Even if pyproject enables it, an explicit --no-allow-build wins.
    write_pyproject(project, allow_build=True)
    result, resolve_mock, install_mock = _invoke_sync_capturing_allow_build(
        project, ["sync", "--no-allow-build"]
    )
    assert result.exit_code == 0, result.output
    assert resolve_mock.call_args.kwargs["allow_build"] is False
    assert install_mock.call_args.kwargs["allow_build"] is False


def test_pyproject_config_enables_build(project):
    # No CLI flag -> fall back to [tool.pywrangler] allow-build.
    write_pyproject(project, allow_build=True)
    result, resolve_mock, install_mock = _invoke_sync_capturing_allow_build(
        project, ["sync"]
    )
    assert result.exit_code == 0, result.output
    assert resolve_mock.call_args.kwargs["allow_build"] is True
    assert install_mock.call_args.kwargs["allow_build"] is True


def test_cli_flag_overrides_pyproject_config(project):
    # pyproject says false, CLI flag says true -> CLI wins.
    write_pyproject(project, allow_build=False)
    result, resolve_mock, _ = _invoke_sync_capturing_allow_build(
        project, ["sync", "--allow-build"]
    )
    assert result.exit_code == 0, result.output
    assert resolve_mock.call_args.kwargs["allow_build"] is True


# ---------------------------------------------------------------------------
# Command construction: --no-build toggling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("allow_build", [True, False])
def test_compile_lockfile_no_build_toggle(tmp_path, allow_build):
    lockfile = tmp_path / "pylock.toml"
    with (
        patch.object(pywrangler_resolve, "run_command") as mock_run,
        patch.object(pywrangler_resolve, "get_project_root", return_value=tmp_path),
        patch.object(
            pywrangler_resolve, "get_uv_pyodide_interp_name", return_value="python3.12"
        ),
        patch.object(
            pywrangler_resolve, "get_pyodide_index", return_value="https://index"
        ),
    ):
        pywrangler_resolve._compile_lockfile(
            ["click"], lockfile, allow_build=allow_build
        )

    cmd = mock_run.call_args.args[0]
    assert ("--no-build" in cmd) is (not allow_build)


def _run_vendor_install(tmp_path, plan, allow_build):
    """Run _install_requirements_to_vendor with fs/network mocked; return the cmd."""
    pyodide_venv = tmp_path / "pyodide-venv"
    site_packages = pyodide_venv / "lib" / "python3.12" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    plan.lockfile = tmp_path / "pylock.toml"

    with (
        patch.object(
            pywrangler_sync,
            "get_vendor_modules_path",
            return_value=tmp_path / "python_modules",
        ),
        patch.object(pywrangler_sync, "get_project_root", return_value=tmp_path),
        patch.object(pywrangler_sync, "get_python_version", return_value="3.12"),
        patch.object(
            pywrangler_sync, "get_pyodide_venv_path", return_value=pyodide_venv
        ),
        patch.object(pywrangler_sync, "_write_sync_token"),
        patch.object(pywrangler_sync, "run_command") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        err = pywrangler_sync._install_requirements_to_vendor(
            plan, allow_build=allow_build
        )

    assert err is None
    return mock_run.call_args.args[0]


def test_vendor_install_no_build_by_default(tmp_path):
    plan = MagicMock()
    plan.requirements = [("click", "8.0.0")]
    plan.local_packages = []
    cmd = _run_vendor_install(tmp_path, plan, allow_build=False)
    assert "--no-build" in cmd
    assert "--refresh-package" not in cmd


def test_vendor_install_allow_build_omits_no_build_and_refreshes_local(tmp_path):
    plan = MagicMock()
    plan.requirements = [("click", "8.0.0")]
    plan.local_packages = ["my-local-sdk"]
    cmd = _run_vendor_install(tmp_path, plan, allow_build=True)
    assert "--no-build" not in cmd
    # Local sources are refreshed so edits to the checkout are rebuilt.
    assert "--refresh-package" in cmd
    assert "my-local-sdk" in cmd
    # The refresh flag immediately precedes the package name.
    idx = cmd.index("--refresh-package")
    assert cmd[idx + 1] == "my-local-sdk"


# ---------------------------------------------------------------------------
# InstallPlan.local_packages detection
# ---------------------------------------------------------------------------


def test_install_plan_detects_local_sources(tmp_path):
    lockfile = tmp_path / "pylock.toml"
    lockfile.write_text(
        dedent("""
        lock-version = "1.0"
        created-by = "uv"

        [[packages]]
        name = "flask"
        version = "3.1.3"
        wheels = [{ url = "https://example.invalid/flask.whl" }]

        [[packages]]
        name = "webtypy"
        version = "0.1.7"
        sdist = { url = "https://example.invalid/webtypy.tar.gz" }

        [[packages]]
        name = "dir-sdk"
        directory = { path = "/home/dev/checkout/sdk" }

        [[packages]]
        name = "wheel-sdk"
        version = "1.0.0"
        archive = { path = "/home/dev/dist/wheel_sdk-1.0.0-py3-none-any.whl" }
        """)
    )

    plan = InstallPlan(lockfile)

    # Local (path-based) sources are flagged...
    assert set(plan.local_packages) == {"dir-sdk", "wheel-sdk"}
    # ...while registry wheels / sdists (url-based) are not.
    assert "flask" not in plan.local_packages
    assert "webtypy" not in plan.local_packages

    # Packages with a version still populate requirements; the versionless
    # directory source is skipped there (it has no pinned version).
    req_names = {name for name, _ in plan.requirements}
    assert {"flask", "webtypy", "wheel-sdk"} <= req_names
    assert "dir-sdk" not in req_names
