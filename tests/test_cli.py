import os
import shutil
import subprocess
from pathlib import Path
import pytest
from click.testing import CliRunner
from unittest.mock import patch

# Import the full module so we can patch constants
import pywrangler.cli
from pywrangler.cli import app, sync_command

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
    package_name_normalized = package_name.lower().replace('-', '_')

    matches = list(site_packages_path.glob(f"*{package_name_normalized}*"))
    if matches:
        print(f"Found {package_name} as: {matches}")
        return True

    # If we get here, nothing was found
    print(f"Could not find {package_name} in {site_packages_path}")
    print(f"Contents of site-packages: {[p.name for p in site_packages_path.iterdir()]}")
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
    
    content = f"""
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "test-project"
version = "0.1.0"
description = "Test Project"
requires-python = ">=3.8"
dependencies = [
    {','.join([f'"{dep}"' for dep in dependencies])}
]
"""
    TEST_PYPROJECT.write_text(content)
    return dependencies


def create_test_wrangler_jsonc(main_path="src/worker.py"):
    """Create a test wrangler.jsonc file with the given main path."""
    content = f"""
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
    content = f"""
# Name of the worker
name = "test-worker-toml"

# Main script to run
main = "{main_path}"

# Compatibility date
compatibility_date = "2023-10-30"
"""
    TEST_WRANGLER_TOML.write_text(content)

@pytest.mark.parametrize("dependencies", [
    ["click"],  # Simple single dependency
    ["fastapi", "numpy"],
    []  # Empty dependency list
])
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
    assert result.returncode == 0, f"Script failed with output: {result.stdout}\nErrors: {result.stderr}"
    
    # Verify the src/vendor directory has the expected packages
    TEST_SRC_VENDOR = TEST_DIR / "src" / "vendor"
    if test_deps:
        assert TEST_SRC_VENDOR.exists(), f"Vendor directory was not created at {TEST_SRC_VENDOR}"
        
        for pkg in dependencies:
            assert is_package_installed(TEST_SRC_VENDOR, pkg), f"Package {pkg} was not installed in {TEST_SRC_VENDOR}"
            
    else:
        # If no dependencies, vendor dir might still be created but should be empty
        if TEST_SRC_VENDOR.exists() and TEST_SRC_VENDOR.is_dir():
            # Allow for empty directories like __pycache__ that might be created
            assert all(d.name.startswith('__') for d in TEST_SRC_VENDOR.iterdir() if d.is_dir()), \
                f"Vendor directory should be empty of packages but contains: {list(TEST_SRC_VENDOR.iterdir())}"
    
    # Check .venv-workers directory exists and has the expected packages
    TEST_VENV_WORKERS = TEST_DIR / ".venv-workers"
    assert TEST_VENV_WORKERS.exists(), f".venv-workers directory was not created at {TEST_VENV_WORKERS}"
    
    # Check that packages were installed in .venv-workers
    if os.name == "nt":
        site_packages_path = TEST_VENV_WORKERS / "Lib" / "site-packages"
    else:
        site_packages_path = TEST_VENV_WORKERS / "lib" / "python3.12" / "site-packages"
    assert site_packages_path.exists(), "site-packages directory does not exist in .venv-workers"
    
    # Check that webtypy is installed (should always be installed)
    assert is_package_installed(site_packages_path, "webtypy"), "webtypy package was not installed in .venv-workers"
    
    # Check that all dependencies from pyproject.toml are installed
    for dep in dependencies:
        assert is_package_installed(site_packages_path, dep), f"Package {dep} was not installed in .venv-workers"

@patch.object(pywrangler.sync, "PROJECT_ROOT", TEST_DIR)
@patch.object(pywrangler.sync, "PYPROJECT_TOML_PATH", TEST_PYPROJECT)
def test_sync_command_handles_missing_pyproject(clean_test_dir, caplog):
    """Test that the sync command correctly handles a missing pyproject.toml file."""
    # Don't create the pyproject.toml file
    assert not TEST_PYPROJECT.exists()
    
    # Create a wrangler.jsonc file so we don't fail due to missing wrangler config
    create_test_wrangler_jsonc()

    # Use the Click test runner to invoke the command
    runner = CliRunner()
    result = runner.invoke(app, ["sync"])

    # Check that the command failed with the expected error
    assert result.exit_code != 0
    
    # Check that the error was logged
    expected_log_message = f"{TEST_PYPROJECT} not found"
    assert expected_log_message in caplog.text


@patch("pywrangler.cli.check_timestamps")
@patch("pywrangler.cli.install_requirements")
def test_sync_command_with_unchanged_timestamps(mock_install_requirements, 
                                             mock_check_timestamps,
                                             clean_test_dir, caplog):
    """Test that the sync command skips sync when timestamps indicate no change."""
    
    # Create the pyproject.toml file
    create_test_pyproject()
    
    # Create a wrangler.jsonc file
    create_test_wrangler_jsonc()
    
    # Mock check_timestamps to return False (no sync needed)
    mock_check_timestamps.return_value = False

    # Use the Click test runner to invoke the command
    runner = CliRunner()
    result = runner.invoke(app, ["sync"])

    # Check that the command succeeded
    assert result.exit_code == 0
    
    # Verify that none of the sync functions were called
    mock_install_requirements.assert_not_called()


@patch("pywrangler.cli.check_timestamps")
@patch("pywrangler.cli.install_requirements")
def test_sync_command_with_changed_timestamps(
                                           mock_install_requirements,
                                           mock_check_timestamps,
                                           clean_test_dir, caplog):
    """Test that the sync command runs when timestamps indicate changes."""
    # Create the pyproject.toml file
    create_test_pyproject()
    
    # Create a wrangler.jsonc file
    create_test_wrangler_jsonc()
    
    # Mock check_timestamps to return True (sync needed)
    mock_check_timestamps.return_value = True

    # Use the Click test runner to invoke the command
    runner = CliRunner()
    result = runner.invoke(app, ["sync"])

    # Check that the command succeeded
    assert result.exit_code == 0
    
    # Verify that all the sync functions were called
    mock_install_requirements.assert_called_once()


@patch("pywrangler.cli.check_timestamps")
@patch("pywrangler.cli.install_requirements")
def test_sync_command_with_force_flag(
                                     mock_install_requirements,
                                     mock_check_timestamps,
                                     clean_test_dir, caplog):
    """Test that the sync command runs when the --force flag is used, regardless of timestamps."""
    # Create the pyproject.toml file
    create_test_pyproject()
    
    # Create a wrangler.jsonc file
    create_test_wrangler_jsonc()
    
    # Mock check_timestamps to return False (no sync needed)
    # This should be ignored due to the --force flag
    mock_check_timestamps.return_value = False

    # Use the Click test runner to invoke the command with --force
    runner = CliRunner()
    result = runner.invoke(app, ["sync", "--force"])

    # Check that the command succeeded
    assert result.exit_code == 0
    
    # Verify that all the sync functions were called despite the timestamp check
    mock_install_requirements.assert_called_once()


@patch.object(pywrangler.sync, "PROJECT_ROOT", TEST_DIR)
@patch.object(pywrangler.sync, "PYPROJECT_TOML_PATH", TEST_PYPROJECT)
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


@patch.object(pywrangler.sync, "PROJECT_ROOT", TEST_DIR)
@patch.object(pywrangler.sync, "PYPROJECT_TOML_PATH", TEST_PYPROJECT)
def test_sync_command_with_wrangler_toml(clean_test_dir, caplog):
    """Test that the sync command correctly processes wrangler.toml files."""
    # Create the necessary files
    create_test_pyproject(["click"])
    create_test_wrangler_toml("dist/worker.js")
    
    # Verify files exist
    assert TEST_PYPROJECT.exists()
    assert TEST_WRANGLER_TOML.exists()
    assert not TEST_WRANGLER_JSONC.exists()  # Ensure JSONC doesn't exist

    # Use the Click test runner to invoke the command
    runner = CliRunner()
    result = runner.invoke(app, ["sync"])
    
    # Check the command output and logs
    assert result.exit_code == 0, f"Command failed: {result.stdout}\n{result.stderr}"
    
    # Check that the path contains dist/vendor (but as an absolute path)
    assert f"{TEST_DIR}/dist/vendor" in caplog.text
    
    # Verify vendor directory was created in the correct location
    vendor_path = TEST_DIR / "dist" / "vendor"
    assert vendor_path.exists(), f"Vendor directory was not created at {vendor_path}"
