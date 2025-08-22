import logging
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch
from textwrap import dedent

import pytest
from click.testing import CliRunner

# Import the full module so we can patch constants
from pywrangler.cli import app
import pywrangler.sync as pywrangler_sync


# Define test fixtures and constants
TEST_DIR = Path(__file__).parent / "test_workspace"
TEST_PYPROJECT = TEST_DIR / "pyproject.toml"
TEST_WRANGLER_JSONC = TEST_DIR / "wrangler.jsonc"
TEST_WRANGLER_TOML = TEST_DIR / "wrangler.toml"


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
def clean_test_dir():
    """Create a clean test directory for each test."""
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir(parents=True)
    (TEST_DIR / "src").mkdir()
    yield TEST_DIR
    # Cleanup after tests
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)


def create_test_pyproject(dependencies=None):
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
    TEST_PYPROJECT.write_text(content)
    return dependencies


def create_test_wrangler_jsonc(main_path="src/worker.py"):
    """Create a test wrangler.jsonc file with the given main path."""
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
        "compatibility_date": "2023-10-30"
    }}
    """
    TEST_WRANGLER_JSONC.write_text(content)


def create_test_wrangler_toml(main_path="dist/worker.js"):
    """Create a test wrangler.toml file with the given main path."""
    content = dedent(f"""
        # Name of the worker
        name = "test-worker-toml"

        # Main script to run
        main = "{main_path}"

        # Compatibility date
        compatibility_date = "2023-10-30"
    """)
    TEST_WRANGLER_TOML.write_text(content)


@pytest.mark.parametrize(
    "dependencies",
    [
        ["click"],  # Simple single dependency
        ["fastapi", "numpy"],
        [],  # Empty dependency list
    ],
)
def test_sync_command_integration(dependencies, clean_test_dir):
    """Test the sync command with real commands running on the system."""
    # Create a test pyproject.toml with dependencies
    test_deps = create_test_pyproject(dependencies)

    # Create a test wrangler.jsonc file
    create_test_wrangler_jsonc("src/worker.py")

    # Save the current directory
    original_dir = os.getcwd()

    try:
        # Change to the test directory
        os.chdir(TEST_DIR)

        # Get the absolute path to the package root
        project_root = Path(original_dir)

        # Run the pywrangler CLI directly using uvx
        print("\nRunning pywrangler sync...")
        sync_cmd = ["uvx", "--from", str(project_root), "pywrangler", "sync"]

        result = subprocess.run(sync_cmd, capture_output=True, text=True)
        print(f"\nCommand output:\n{result.stdout}")
        if result.stderr:
            print(f"Command errors:\n{result.stderr}")

    finally:
        # Change back to the original directory
        os.chdir(original_dir)

    # Check that the command succeeded
    assert result.returncode == 0, (
        f"Script failed with output: {result.stdout}\nErrors: {result.stderr}"
    )

    # Verify the python_modules directory has the expected packages
    TEST_SRC_VENDOR = TEST_DIR / "python_modules"
    if test_deps:
        assert TEST_SRC_VENDOR.exists(), (
            f"python_modules directory was not created at {TEST_SRC_VENDOR}"
        )

        for pkg in dependencies:
            assert is_package_installed(TEST_SRC_VENDOR, pkg), (
                f"Package {pkg} was not installed in {TEST_SRC_VENDOR}"
            )

    else:
        # If no dependencies, vendor dir might still be created but should be empty
        if TEST_SRC_VENDOR.exists() and TEST_SRC_VENDOR.is_dir():
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
    TEST_VENV_WORKERS = TEST_DIR / ".venv-workers"
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

    # Check that webtypy and pyodide-py are installed (should always be installed, even if no deps are specified)
    assert is_package_installed(site_packages_path, "webtypy"), (
        "webtypy package was not installed in .venv-workers"
    )
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

        # Don't create pyproject.toml file
        assert not (temp_path / "pyproject.toml").exists()

        # Save original directory
        original_dir = os.getcwd()

        try:
            # Change to temp directory
            os.chdir(temp_path)

            # Get the absolute path to the package root
            project_root = Path(original_dir)

            # Run pywrangler sync from the temp directory (should fail)
            sync_cmd = ["uvx", "--from", str(project_root), "pywrangler", "sync"]

            result = subprocess.run(sync_cmd, capture_output=True, text=True)

        finally:
            # Change back to original directory
            os.chdir(original_dir)

        # Check that the command failed with the expected error
        assert result.returncode != 0

        # Check that the error was logged
        assert "pyproject.toml not found" in result.stdout


@patch.object(pywrangler_sync, "is_sync_needed")
@patch.object(pywrangler_sync, "install_requirements")
def test_sync_command_with_unchanged_timestamps(
    mock_install_requirements, mock_is_sync_needed, clean_test_dir, caplog
):
    """Test that the sync command skips sync when timestamps indicate no change."""

    # Create the pyproject.toml file
    create_test_pyproject()

    # Create a wrangler.jsonc file
    create_test_wrangler_jsonc()

    # Mock is_sync_needed to return False (no sync needed)
    mock_is_sync_needed.return_value = False

    # Use the Click test runner to invoke the command
    runner = CliRunner()
    result = runner.invoke(app, ["sync"])

    # Check that the command succeeded
    assert result.exit_code == 0

    # Verify that none of the sync functions were called
    mock_install_requirements.assert_not_called()


@patch.object(pywrangler_sync, "PROJECT_ROOT", TEST_DIR)
@patch.object(pywrangler_sync, "is_sync_needed")
@patch.object(pywrangler_sync, "install_requirements")
def test_sync_command_with_changed_timestamps(
    mock_install_requirements, mock_is_sync_needed, clean_test_dir, caplog
):
    """Test that the sync command runs when timestamps indicate changes."""
    # Create the pyproject.toml file
    create_test_pyproject()

    # Create a wrangler.jsonc file
    create_test_wrangler_jsonc()

    # Mock is_sync_needed to return True (sync needed)
    mock_is_sync_needed.return_value = True

    # Use the Click test runner to invoke the command
    runner = CliRunner()
    result = runner.invoke(app, ["sync"])

    # Check that the command succeeded
    assert result.exit_code == 0

    # Verify that all the sync functions were called
    mock_install_requirements.assert_called_once()


@patch.object(pywrangler_sync, "PROJECT_ROOT", TEST_DIR)
@patch.object(pywrangler_sync, "is_sync_needed")
@patch.object(pywrangler_sync, "install_requirements")
def test_sync_command_with_force_flag(
    mock_install_requirements, mock_is_sync_needed, clean_test_dir, caplog
):
    """Test that the sync command runs when the --force flag is used, regardless of timestamps."""
    # Create the pyproject.toml file
    create_test_pyproject()

    # Create a wrangler.jsonc file
    create_test_wrangler_jsonc()

    # Mock is_sync_needed to return False (no sync needed)
    # This should be ignored due to the --force flag
    mock_is_sync_needed.return_value = False

    # Use the Click test runner to invoke the command with --force
    runner = CliRunner()
    result = runner.invoke(app, ["sync", "--force"])

    # Check that the command succeeded
    assert result.exit_code == 0

    # Verify that all the sync functions were called despite the timestamp check
    mock_install_requirements.assert_called_once()


@patch.object(pywrangler_sync, "PROJECT_ROOT", TEST_DIR)
@patch.object(pywrangler_sync, "PYPROJECT_TOML_PATH", TEST_PYPROJECT)
def test_sync_command_handles_missing_wrangler_config(clean_test_dir, caplog):
    """Test that the sync command correctly handles missing wrangler configuration files."""
    # Create a pyproject.toml file but don't create wrangler config files
    create_test_pyproject()
    assert TEST_PYPROJECT.exists()
    assert not TEST_WRANGLER_JSONC.exists()
    assert not (TEST_DIR / "wrangler.toml").exists()

    # Use the Click test runner to invoke the command
    runner = CliRunner()
    result = runner.invoke(app, ["sync"])

    # Check that the command failed with the expected error
    assert result.exit_code != 0

    # Check that the error was logged - looking for messages about missing wrangler config
    assert "wrangler.jsonc" in caplog.text
    assert "not found" in caplog.text


@patch.object(pywrangler_sync, "PROJECT_ROOT", TEST_DIR)
@patch.object(pywrangler_sync, "PYPROJECT_TOML_PATH", TEST_PYPROJECT)
def test_debug_flag(clean_test_dir, caplog):
    """Test that the --debug flag enables debug output."""
    # Create the pyproject.toml file
    create_test_pyproject()

    # Create a wrangler.jsonc file
    create_test_wrangler_jsonc()

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


@patch("pywrangler.cli._proxy_to_wrangler")
@patch("pywrangler.cli.sync_command")
@patch("sys.argv", ["pywrangler", "dev", "--local"])
def test_proxy_auto_sync_commands(mock_sync_command, mock_proxy_to_wrangler):
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
        ["npx", "--yes", "wrangler", "unknown_command"], check=False, cwd="."
    )


def test_sync_command_finds_pyproject_in_parent_directory(clean_test_dir):
    """Test that the sync command can find pyproject.toml in a parent directory."""
    # Create pyproject.toml in the test directory (parent)
    create_test_pyproject(["click"])
    create_test_wrangler_jsonc("src/worker.py")

    # Create a subdirectory and change to it
    subdir = TEST_DIR / "subproject"
    subdir.mkdir()

    # Save the original directory
    original_dir = os.getcwd()

    try:
        # Change to the subdirectory
        os.chdir(subdir)

        # Get the absolute path to the package root
        project_root = Path(original_dir)

        # Run the pywrangler CLI from the subdirectory
        sync_cmd = ["uvx", "--from", str(project_root), "pywrangler", "sync"]

        result = subprocess.run(sync_cmd, capture_output=True, text=True)
        print(f"\nCommand output:\n{result.stdout}")
        if result.stderr:
            print(f"Command errors:\n{result.stderr}")

    finally:
        # Change back to the original directory
        os.chdir(original_dir)

    # Check that the command succeeded
    assert result.returncode == 0, (
        f"Script failed with output: {result.stdout}\nErrors: {result.stderr}"
    )

    # Verify the vendor directory was created in the parent directory (where pyproject.toml is)
    TEST_SRC_VENDOR = TEST_DIR / "python_modules"
    assert TEST_SRC_VENDOR.exists(), (
        f"python_modules directory was not created at {TEST_SRC_VENDOR}"
    )

    # Verify the .venv-workers directory was created in the parent directory
    TEST_VENV_WORKERS = TEST_DIR / ".venv-workers"
    assert TEST_VENV_WORKERS.exists(), (
        f".venv-workers directory was not created at {TEST_VENV_WORKERS}"
    )


def test_sync_recreates_venv_on_python_version_mismatch(clean_test_dir):
    """
    Test that the sync command recreates the venv if the Python version
    mismatches, using real system commands.
    """
    # Create initial files in the clean test directory
    create_test_pyproject([])
    create_test_wrangler_jsonc()

    original_dir = os.getcwd()
    try:
        os.chdir(clean_test_dir)
        project_root = Path(original_dir)
        sync_cmd = ["uvx", "--from", str(project_root), "pywrangler", "sync"]
        venv_path = clean_test_dir / ".venv-workers"

        # First run: Create venv with Python 3.12
        print("\nRunning sync to create venv with Python 3.12...")
        env = os.environ.copy()
        env["_PYWRANGLER_PYTHON_VERSION"] = "3.12"
        result1 = subprocess.run(sync_cmd, capture_output=True, text=True, env=env)

        assert result1.returncode == 0, (
            f"First sync failed: {result1.stdout}\n{result1.stderr}"
        )
        assert venv_path.exists(), "Venv was not created on the first run."
        initial_mtime = venv_path.stat().st_mtime

        # Second run: Recreate venv with Python 3.13
        print("\nRunning sync to recreate venv with Python 3.13...")
        env["_PYWRANGLER_PYTHON_VERSION"] = "3.13"
        result2 = subprocess.run(sync_cmd, capture_output=True, text=True, env=env)

        assert result2.returncode == 0, (
            f"Second sync failed: {result2.stdout}\n{result2.stderr}"
        )
        assert venv_path.exists(), "Venv was not recreated."
        final_mtime = venv_path.stat().st_mtime

        # Check that the venv was actually modified
        assert final_mtime > initial_mtime, "Venv modification time did not change."

        # Verify the python version in the new venv is 3.13.
        python_exe = venv_path / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        version_result = subprocess.run(
            [str(python_exe), "--version"], capture_output=True, text=True
        )
        assert "3.13" in version_result.stdout, (
            f"Python version is not 3.13: {version_result.stdout}"
        )

    finally:
        os.chdir(original_dir)
