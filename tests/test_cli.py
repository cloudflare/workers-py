import os
import shutil
import subprocess
import sys
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

@pytest.mark.parametrize("dependencies", [
    ["click"],  # Simple single dependency
    ["fastapi", "numpy"],
    []  # Empty dependency list
])
def test_sync_command_integration(dependencies, clean_test_dir):
    """Test the sync command with real commands running on the system."""
    # Create a test pyproject.toml with dependencies
    test_deps = create_test_pyproject(dependencies)
    
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
        
        # Check that each dependency was "installed"
        expected_packages = dependencies
        installed_packages = [d.name for d in TEST_SRC_VENDOR.iterdir() if d.is_dir()]
        
        print(f"Expected packages: {expected_packages}")
        print(f"Installed packages: {installed_packages}")
        
        for pkg in expected_packages:
            assert any(pkg.lower() in p.lower() for p in installed_packages), \
                f"Package {pkg} was not installed in {TEST_SRC_VENDOR}"
            
    else:
        # If no dependencies, vendor dir might still be created but should be empty
        if TEST_SRC_VENDOR.exists() and TEST_SRC_VENDOR.is_dir():
            # Allow for empty directories like __pycache__ that might be created
            assert all(d.name.startswith('__') for d in TEST_SRC_VENDOR.iterdir() if d.is_dir()), \
                f"Vendor directory should be empty of packages but contains: {list(TEST_SRC_VENDOR.iterdir())}"

@patch.object(pywrangler.sync, "PROJECT_ROOT", TEST_DIR)
@patch.object(pywrangler.sync, "PYPROJECT_TOML_PATH", TEST_PYPROJECT)
def test_sync_command_handles_missing_pyproject(clean_test_dir, caplog):
    """Test that the sync command correctly handles a missing pyproject.toml file."""
    # Don't create the pyproject.toml file
    assert not TEST_PYPROJECT.exists()

    # Use the Click test runner to invoke the command
    runner = CliRunner()
    result = runner.invoke(app, ["sync"])

    # Check that the command failed with the expected error
    assert result.exit_code != 0
    
    # Check that the error was logged
    expected_log_message = f"{TEST_PYPROJECT} not found"
    assert expected_log_message in caplog.text
