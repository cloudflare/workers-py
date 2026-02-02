import logging
import os
import shutil
import subprocess
from pathlib import Path
from textwrap import dedent
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

import pywrangler.sync as pywrangler_sync
import pywrangler.utils as pywrangler_utils

# Import the full module so we can patch constants
from pywrangler.cli import app


# Helper function to check if a package is installed in a site-packages directory
def is_package_installed(site_packages_path, package_name):
    """Check if a package is installed in the given site-packages directory.

    Args:
        site_packages_path: Path to the site-packages directory
        package_name: Name of the package to check for

    Returns:
        bool: True if the package is found, False otherwise
    """
    # Normalize package name (lowercase, remove dashes)
    package_name_normalized = package_name.lower().replace("-", "_")

    matches = list(site_packages_path.glob(f"*{package_name_normalized}*"))
    if matches:
        print(f"Found {package_name} as: {matches}")
        return True

    # If we get here, nothing was found
    print(f"Could not find {package_name} in {site_packages_path}")
    print(
        f"Contents of site-packages: {[p.name for p in site_packages_path.iterdir()]}"
    )
    return False


@pytest.fixture
def test_dir(monkeypatch):
    test_dir = Path(__file__).parent / "test_workspace"
    shutil.rmtree(test_dir, ignore_errors=True)
    (test_dir / "src").mkdir(parents=True)
    monkeypatch.setattr(
        pywrangler_utils, "find_pyproject_toml", lambda: test_dir / "pyproject.toml"
    )

    try:
        yield test_dir.absolute()
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def create_test_pyproject(test_dir: Path, dependencies=None):
    """Create a test pyproject.toml file with given dependencies."""
    if dependencies is None:
        dependencies = ["requests==2.28.1", "pydantic>=1.9.0,<2.0.0"]

    content = dedent(f"""
        [build-system]
        requires = ["setuptools>=61.0"]
        build-backend = "setuptools.build_meta"

        [project]
        name = "test-project"
        version = "0.1.0"
        description = "Test Project"
        requires-python = ">=3.8"
        dependencies = [
            {",".join([f'"{dep}"' for dep in dependencies])}
        ]
    """)
    (test_dir / "pyproject.toml").write_text(content)
    return dependencies


def create_test_wrangler_jsonc(
    test_dir: Path, main_path="src/worker.py", python_version="3.12"
):
    """Create a test wrangler.jsonc file with the given main path and Python version."""
    compat_flags = ["python_workers"]
    if python_version == "3.13":
        compat_flags.append("python_workers_20250116")

    compat_flags_str = ", ".join([f'"{flag}"' for flag in compat_flags])

    content = f"""
    /**
     * For more details on how to configure Wrangler, refer to:
     * https://developers.cloudflare.com/workers/wrangler/configuration/
     */
    {{
        // Name of the worker
        "name": "test-worker",

        // Main script to run
        "main": "{main_path}",

        // Compatibility date
        "compatibility_date": "2023-10-30",

        // Compatibility flags
        "compatibility_flags": [{compat_flags_str}]
    }}
    """
    (test_dir / "wrangler.jsonc").write_text(content)


def create_test_wrangler_toml(
    test_dir, main_path="dist/worker.js", python_version="3.12"
):
    """Create a test wrangler.toml file with the given main path and Python version."""
    compat_flags = ["python_workers"]
    if python_version == "3.13":
        compat_flags.append("python_workers_20250116")

    compat_flags_str = ", ".join([f'"{flag}"' for flag in compat_flags])

    content = dedent(f"""
        # Name of the worker
        name = "test-worker-toml"

        # Main script to run
        main = "{main_path}"

        # Compatibility date
        compatibility_date = "2023-10-30"

        # Compatibility flags
        compatibility_flags = [{compat_flags_str}]
    """)
    (test_dir / "wrangler.toml").write_text(content)


@pytest.mark.parametrize(
    "dependencies",
    [
        ["click"],  # Simple single dependency
        ["fastapi", "numpy"],
        [],  # Empty dependency list
    ],
)
def test_sync_command_integration(dependencies, test_dir):
    """Test the sync command with real commands running on the system."""
    # Create a test pyproject.toml with dependencies
    test_deps = create_test_pyproject(test_dir, dependencies)

    # Create a test wrangler.jsonc file
    create_test_wrangler_jsonc(test_dir, "src/worker.py")

    # Get the absolute path to the package root
    # Run the pywrangler CLI directly using uvx
    print("\nRunning pywrangler sync...")
    sync_cmd = ["uv", "run", "pywrangler", "sync"]

    result = subprocess.run(
        sync_cmd, capture_output=True, text=True, cwd=test_dir, check=False
    )
    print(f"\nCommand output:\n{result.stdout}")
    if result.stderr:
        print(f"Command errors:\n{result.stderr}")

    # Check that the command succeeded
    assert result.returncode == 0, (
        f"Script failed with output: {result.stdout}\nErrors: {result.stderr}"
    )

    # Verify the python_modules directory has the expected packages
    TEST_SRC_VENDOR = test_dir / "python_modules"
    if test_deps:
        assert TEST_SRC_VENDOR.exists(), (
            f"python_modules directory was not created at {TEST_SRC_VENDOR}"
        )

        for pkg in dependencies:
            assert is_package_installed(TEST_SRC_VENDOR, pkg), (
                f"Package {pkg} was not installed in {TEST_SRC_VENDOR}"
            )

    # If no dependencies, vendor dir might still be created but should be empty
    elif TEST_SRC_VENDOR.exists() and TEST_SRC_VENDOR.is_dir():
        # Allow for empty directories like __pycache__ that might be created
        assert all(
            d.name.startswith("__") for d in TEST_SRC_VENDOR.iterdir() if d.is_dir()
        ), (
            f"python_modules directory should be empty of packages but contains: {list(TEST_SRC_VENDOR.iterdir())}"
        )

    # Verify that pyvenv.cfg is created only when there are dependencies
    if test_deps:
        assert (TEST_SRC_VENDOR / "pyvenv.cfg").exists(), (
            f"pyvenv.cfg was not created in {TEST_SRC_VENDOR}"
        )

    # Check .venv-workers directory exists and has the expected packages
    TEST_VENV_WORKERS = test_dir / ".venv-workers"
    assert TEST_VENV_WORKERS.exists(), (
        f".venv-workers directory was not created at {TEST_VENV_WORKERS}"
    )

    # Check that packages were installed in .venv-workers
    if os.name == "nt":
        site_packages_path = TEST_VENV_WORKERS / "Lib" / "site-packages"
    else:
        site_packages_path = TEST_VENV_WORKERS / "lib" / "python3.12" / "site-packages"
    assert site_packages_path.exists(), (
        "site-packages directory does not exist in .venv-workers"
    )

    # Check that pyodide-py is installed (should always be installed, even if no deps are specified)
    assert is_package_installed(site_packages_path, "pyodide-py"), (
        "pyodide-py package was not installed in .venv-workers"
    )

    # Check that all dependencies from pyproject.toml are installed
    for dep in dependencies:
        assert is_package_installed(site_packages_path, dep), (
            f"Package {dep} was not installed in .venv-workers"
        )


def test_sync_command_handles_missing_pyproject():
    """Test that the sync command correctly handles a missing pyproject.toml file."""
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a wrangler config but don't create pyproject.toml file
        wrangler_jsonc = temp_path / "wrangler.jsonc"
        wrangler_jsonc.write_text("""
        {
            "name": "test-worker",
            "main": "src/worker.py",
            "compatibility_date": "2023-10-30",
            "compatibility_flags": ["python_workers"]
        }
        """)

        assert not (temp_path / "pyproject.toml").exists()

        # Run pywrangler sync from the temp directory (should fail)
        sync_cmd = ["uv", "run", "pywrangler", "sync"]

        result = subprocess.run(
            sync_cmd, capture_output=True, text=True, cwd=temp_path, check=False
        )

        # Check that the command failed with the expected error
        assert result.returncode != 0

        # Check that the error was logged
        assert "pyproject.toml not found" in result.stdout


@patch.object(pywrangler_sync, "is_sync_needed", lambda: False)
@patch.object(pywrangler_sync, "install_requirements")
def test_sync_command_with_unchanged_timestamps(
    mock_install_requirements, test_dir, caplog
):
    """Test that the sync command skips sync when timestamps indicate no change."""

    # Create the pyproject.toml file
    create_test_pyproject(test_dir)

    # Create a wrangler.jsonc file
    create_test_wrangler_jsonc(test_dir)

    # Use the Click test runner to invoke the command
    runner = CliRunner()
    result = runner.invoke(app, ["sync"])

    # Check that the command succeeded
    assert result.exit_code == 0

    # Verify that none of the sync functions were called
    mock_install_requirements.assert_not_called()


@patch.object(pywrangler_sync, "is_sync_needed", lambda: True)
@patch.object(pywrangler_sync, "install_requirements")
def test_sync_command_with_changed_timestamps(
    mock_install_requirements, test_dir, caplog
):
    """Test that the sync command runs when timestamps indicate changes."""
    # Create the pyproject.toml file
    create_test_pyproject(test_dir)

    # Create a wrangler.jsonc file
    create_test_wrangler_jsonc(test_dir)

    # Use the Click test runner to invoke the command
    runner = CliRunner()
    result = runner.invoke(app, ["sync"])

    # Check that the command succeeded
    assert result.exit_code == 0

    # Verify that all the sync functions were called
    mock_install_requirements.assert_called_once()


@patch.object(pywrangler_sync, "is_sync_needed", lambda: False)
@patch.object(pywrangler_sync, "install_requirements")
def test_sync_command_with_force_flag(mock_install_requirements, test_dir, caplog):
    """Test that the sync command runs when the --force flag is used, regardless of timestamps."""
    create_test_pyproject(test_dir)
    create_test_wrangler_jsonc(test_dir)

    # Use the Click test runner to invoke the command with --force
    runner = CliRunner()
    result = runner.invoke(app, ["sync", "--force"])

    # Check that the command succeeded
    assert result.exit_code == 0

    # Verify that all the sync functions were called despite the timestamp check
    mock_install_requirements.assert_called_once()


def test_sync_command_handles_missing_wrangler_config(test_dir, caplog):
    """Test that the sync command correctly handles missing wrangler configuration files."""
    # Create a pyproject.toml file but don't create wrangler config files
    create_test_pyproject(test_dir)
    assert (test_dir / "pyproject.toml").exists()
    assert not (test_dir / "wrangler.jsonc").exists()
    assert not (test_dir / "wrangler.toml").exists()

    # Use the Click test runner to invoke the command
    runner = CliRunner()
    result = runner.invoke(app, ["sync"])

    # Check that the command failed with the expected error
    assert result.exit_code != 0

    # Check that the error was logged - looking for messages about missing wrangler config
    assert "wrangler.jsonc" in caplog.text
    assert "not found" in caplog.text


def test_debug_flag(test_dir, caplog):
    """Test that the --debug flag enables debug output."""
    create_test_pyproject(test_dir)
    create_test_wrangler_jsonc(test_dir)

    # Run the command with --debug flag
    runner = CliRunner()
    runner.invoke(app, ["--debug", "sync"])

    # Check that debug logs were generated
    debug_logs = [
        record for record in caplog.records if record.levelno == logging.DEBUG
    ]

    # Verify that debug logs are present
    assert len(debug_logs) > 0, "No debug logs were produced when using --debug flag"


@patch("pywrangler.cli._proxy_to_wrangler")
@patch("sys.argv", ["pywrangler", "unknown_command", "--some-flag", "value"])
def test_proxy_to_wrangler_unknown_command(mock_proxy_to_wrangler):
    """Test that unknown commands are proxied to wrangler."""
    runner = CliRunner()
    result = runner.invoke(app, ["unknown_command", "--some-flag", "value"])

    # Should exit with 0 (from mocked process)
    assert result.exit_code == 0

    # Verify _proxy_to_wrangler was called with correct arguments
    mock_proxy_to_wrangler.assert_called_once_with(
        "unknown_command", ["--some-flag", "value"]
    )


@patch("pywrangler.utils.check_wrangler_version")
@patch("pywrangler.cli._proxy_to_wrangler")
@patch("pywrangler.cli.sync")
@patch("sys.argv", ["pywrangler", "dev", "--local"])
def test_proxy_auto_sync_commands(
    mock_sync_command, mock_proxy_to_wrangler, mock_check_wrangler_version
):
    """Test that dev, publish, and deploy commands automatically run sync first."""
    runner = CliRunner()

    # Test dev command
    result = runner.invoke(app, ["dev", "--local"])
    assert result.exit_code == 0

    # Verify sync was called
    mock_sync_command.assert_called_once()

    # Verify _proxy_to_wrangler was called with correct arguments
    mock_proxy_to_wrangler.assert_called_once_with("dev", ["--local"])


@patch("pywrangler.cli.subprocess.run")
def test_proxy_to_wrangler_handles_subprocess_error(mock_subprocess_run):
    """Test that subprocess errors are handled gracefully."""
    # Mock subprocess.run to raise FileNotFoundError
    mock_subprocess_run.side_effect = FileNotFoundError()

    runner = CliRunner()
    result = runner.invoke(app, ["unknown_command"])

    # Should exit with 1 (error code)
    assert result.exit_code == 1

    # Verify the error was attempted to be called
    mock_subprocess_run.assert_called_once_with(
        ["npx", "--yes", "wrangler", "unknown_command"],
        check=False,
        cwd=Path("."),
        env=None,
        text=True,
        encoding="utf-8",
    )


def test_sync_command_finds_pyproject_in_parent_directory(test_dir):
    """Test that the sync command can find pyproject.toml in a parent directory."""
    # Create pyproject.toml in the test directory (parent)
    create_test_pyproject(test_dir, ["click"])
    create_test_wrangler_jsonc(test_dir, "src/worker.py")

    # Create a subdirectory and change to it
    subdir = test_dir / "subproject"
    subdir.mkdir()

    # Run the pywrangler CLI from the subdirectory
    sync_cmd = ["uv", "run", "pywrangler", "sync"]

    result = subprocess.run(
        sync_cmd, capture_output=True, text=True, cwd=subdir, check=False
    )
    print(f"\nCommand output:\n{result.stdout}")
    if result.stderr:
        print(f"Command errors:\n{result.stderr}")

    # Check that the command succeeded
    assert result.returncode == 0, (
        f"Script failed with output: {result.stdout}\nErrors: {result.stderr}"
    )

    # Verify the vendor directory was created in the parent directory (where pyproject.toml is)
    TEST_SRC_VENDOR = test_dir / "python_modules"
    assert TEST_SRC_VENDOR.exists(), (
        f"python_modules directory was not created at {TEST_SRC_VENDOR}"
    )

    # Verify the .venv-workers directory was created in the parent directory
    TEST_VENV_WORKERS = test_dir / ".venv-workers"
    assert TEST_VENV_WORKERS.exists(), (
        f".venv-workers directory was not created at {TEST_VENV_WORKERS}"
    )


def test_sync_recreates_venv_on_python_version_mismatch(test_dir):
    """
    Test that the sync command recreates the venv if the Python version
    mismatches, using real system commands.
    """
    # Create initial files in the clean test directory
    create_test_pyproject(test_dir)

    sync_cmd = ["uv", "run", "pywrangler", "sync"]
    venv_path = test_dir / ".venv-workers"

    # First run: Create venv with Python 3.12 (using basic python_workers flag)
    print("\nRunning sync to create venv with Python 3.12...")
    create_test_wrangler_jsonc(test_dir, python_version="3.12")
    result1 = subprocess.run(
        sync_cmd, capture_output=True, text=True, cwd=test_dir, check=False
    )

    assert result1.returncode == 0, (
        f"First sync failed: {result1.stdout}\n{result1.stderr}"
    )
    assert venv_path.exists(), "Venv was not created on the first run."
    initial_mtime = venv_path.stat().st_mtime

    # Second run: Recreate venv with Python 3.13 (using python_workers_20250116 flag)
    print("\nRunning sync to recreate venv with Python 3.13...")
    create_test_pyproject(test_dir)
    create_test_wrangler_jsonc(test_dir, python_version="3.13")
    result2 = subprocess.run(sync_cmd, text=True, cwd=test_dir, check=False)

    assert result2.returncode == 0, (
        f"Second sync failed: {result2.stdout}\n{result2.stderr}"
    )
    assert venv_path.exists(), "Venv was not recreated."
    final_mtime = venv_path.stat().st_mtime

    # Check that the venv was actually modified
    assert final_mtime > initial_mtime, "Venv modification time did not change."

    # Verify the python version in the new venv is 3.13.
    python_exe = venv_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    version_result = subprocess.run(
        [python_exe, "--version"],
        capture_output=True,
        text=True,
        cwd=test_dir,
        check=False,
    )
    assert "3.13" in version_result.stdout, (
        f"Python version is not 3.13: {version_result.stdout}"
    )


# Wrangler version check tests
@patch("pywrangler.utils.run_command")
def test_check_wrangler_version_sufficient(mock_run_command):
    """Test that check_wrangler_version passes with sufficient version."""
    from pywrangler.utils import check_wrangler_version

    # Mock successful wrangler version output
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "wrangler 4.42.1"
    mock_run_command.return_value = mock_result

    # Should not raise an exception
    check_wrangler_version()

    # Verify the command was called correctly
    mock_run_command.assert_called_once_with(
        ["npx", "--yes", "wrangler", "--version"], capture_output=True, check=False
    )


@patch("pywrangler.utils.run_command")
def test_check_wrangler_version_insufficient(mock_run_command):
    """Test that check_wrangler_version fails with insufficient version."""
    from pywrangler.utils import check_wrangler_version

    # Mock wrangler version output with old version
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "⛅️ wrangler 4.40.0"
    mock_run_command.return_value = mock_result

    # Should raise SystemExit
    import click

    with pytest.raises(click.exceptions.Exit):
        check_wrangler_version()


# Tests for PYWRANGLER_LOG environment variable


def test_env_var_debug_level(test_dir, monkeypatch, caplog):
    monkeypatch.setenv("PYWRANGLER_LOG", "debug")
    create_test_pyproject(test_dir)
    create_test_wrangler_jsonc(test_dir)

    # Need to reimport to pick up env var change
    import importlib

    import pywrangler.utils

    importlib.reload(pywrangler.utils)

    from pywrangler.utils import setup_logging

    level = setup_logging()
    assert level == logging.DEBUG


def test_env_var_error_level(test_dir, monkeypatch):
    """Test that PYWRANGLER_LOG=error sets ERROR level."""
    monkeypatch.setenv("PYWRANGLER_LOG", "error")

    import importlib

    import pywrangler.utils

    importlib.reload(pywrangler.utils)

    from pywrangler.utils import setup_logging

    level = setup_logging()
    assert level == logging.ERROR


def test_env_var_case_insensitive(test_dir, monkeypatch):
    """Test that PYWRANGLER_LOG is case-insensitive."""
    monkeypatch.setenv("PYWRANGLER_LOG", "DEBUG")

    import importlib

    import pywrangler.utils

    importlib.reload(pywrangler.utils)

    from pywrangler.utils import setup_logging

    level = setup_logging()
    assert level == logging.DEBUG


def test_debug_flag_overrides_env(test_dir, monkeypatch, caplog):
    """Test that --debug flag overrides PYWRANGLER_LOG=error."""
    monkeypatch.setenv("PYWRANGLER_LOG", "error")
    create_test_pyproject(test_dir)
    create_test_wrangler_jsonc(test_dir)

    runner = CliRunner()
    runner.invoke(app, ["--debug", "sync"])

    debug_logs = [
        record for record in caplog.records if record.levelno == logging.DEBUG
    ]
    assert len(debug_logs) > 0, "--debug flag should override PYWRANGLER_LOG=error"


def test_env_var_invalid(test_dir, monkeypatch, capsys):
    """Test that invalid PYWRANGLER_LOG value produces warning."""
    monkeypatch.setenv("PYWRANGLER_LOG", "invalid_value")

    import importlib

    import pywrangler.utils

    importlib.reload(pywrangler.utils)

    from pywrangler.utils import setup_logging

    level = setup_logging()

    captured = capsys.readouterr()
    assert "Warning" in captured.err
    assert "invalid_value" in captured.err
    assert level == logging.INFO


def test_startup_banner(test_dir, monkeypatch):
    """Test that debug output contains version, platform, and working directory."""
    monkeypatch.setenv("PYWRANGLER_LOG", "debug")
    create_test_pyproject(test_dir)
    create_test_wrangler_jsonc(test_dir)

    import importlib

    import pywrangler.utils

    importlib.reload(pywrangler.utils)

    from pywrangler.utils import _get_pywrangler_version, log_startup_info

    # Verify the functions exist and return expected content
    version = _get_pywrangler_version()
    assert version is not None

    # Verify log_startup_info can be called without error
    # The actual logging is tested via integration in test_debug_flag
    log_startup_info()
