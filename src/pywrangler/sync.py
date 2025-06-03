import logging
from pathlib import Path
import os
from pywrangler.utils import run_command, get_vendor_path_from_wrangler_config

import click

try:
    import tomllib  # Standard in Python 3.11+
except ImportError:
    import tomli as tomllib  # For Python < 3.11

logger = logging.getLogger(__name__)

# Define paths
PROJECT_ROOT = Path.cwd()  # Assumes script is run from project root
VENV_WORKERS_PATH = PROJECT_ROOT / ".venv-workers"
PYODIDE_VENV_PATH = VENV_WORKERS_PATH / "pyodide-venv"
PYPROJECT_TOML_PATH = PROJECT_ROOT / "pyproject.toml"
GENERATED_REQUIREMENTS_PATH = PYODIDE_VENV_PATH / "temp-requirements.txt"
VENV_REQUIREMENTS_PATH = VENV_WORKERS_PATH / "temp-venv-requirements.txt"


def check_pyproject_toml():
    if not PYPROJECT_TOML_PATH.is_file():
        logger.error(f"{PYPROJECT_TOML_PATH} not found.")
        raise click.exceptions.Exit(code=1)


def create_workers_venv():
    """
    Creates a virtual environment at `VENV_WORKERS_PATH` if it doesn't exist.
    """
    if not VENV_WORKERS_PATH.is_dir():  # Check if it's a directory
        logger.info(f"Creating virtual environment at {VENV_WORKERS_PATH}...")
        run_command(["uv", "venv", str(VENV_WORKERS_PATH), "--python", "python3.12"])
    else:
        logger.info(f"Virtual environment at {VENV_WORKERS_PATH} already exists.")


def _get_pyodide_cli_path():
    venv_bin_path = VENV_WORKERS_PATH / ("Scripts" if os.name == "nt" else "bin")
    pyodide_cli_path = venv_bin_path / ("pyodide.exe" if os.name == "nt" else "pyodide")
    return pyodide_cli_path


def install_pyodide_build():
    pyodide_cli_path = _get_pyodide_cli_path()

    if not pyodide_cli_path.is_file():
        logger.info(
            f"Installing pyodide-build in {VENV_WORKERS_PATH} using 'uv pip install'..."
        )
        venv_bin_path = pyodide_cli_path.parent

        # Ensure the python executable path is correct for the venv
        venv_python_executable = venv_bin_path / "python"
        if not venv_python_executable.is_file():
            logger.error(f"Python executable not found at {venv_python_executable}")
            raise click.exceptions.Exit(code=1)

        run_command(["uv", "pip", "install", "-p", str(venv_python_executable), "pip"])

        run_command(
            ["uv", "pip", "install", "-p", str(venv_python_executable), "pyodide-build"]
        )
    else:
        logger.info(
            f"pyodide-build CLI already found at {pyodide_cli_path} (skipping install.)"
        )


def create_pyodide_venv():
    pyodide_cli_path = _get_pyodide_cli_path()
    if not PYODIDE_VENV_PATH.is_dir():
        logger.info(f"Creating Pyodide virtual environment at {PYODIDE_VENV_PATH}...")
        PYODIDE_VENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        run_command([str(pyodide_cli_path), "venv", str(PYODIDE_VENV_PATH)])
    else:
        logger.info(
            f"Pyodide virtual environment at {PYODIDE_VENV_PATH} already exists."
        )


def generate_requirements():
    logger.info(
        f"Reading dependencies from {PYPROJECT_TOML_PATH} and generating {GENERATED_REQUIREMENTS_PATH}..."
    )
    try:
        with open(PYPROJECT_TOML_PATH, "rb") as f:  # Use binary mode for tomllib
            pyproject_data = tomllib.load(f)

        # Extract dependencies from [project.dependencies]
        dependencies = pyproject_data.get("project", {}).get("dependencies", [])

        if not dependencies:
            logger.warning(
                "No dependencies found in [project.dependencies] section of pyproject.toml."
            )
        else:
            # Write dependencies to requirements.txt
            GENERATED_REQUIREMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(GENERATED_REQUIREMENTS_PATH, "w") as req_file:
                for dep in dependencies:
                    req_file.write(f"{dep}\n")

            logger.info(
                f"Found {len(dependencies)} dependencies and wrote them to {GENERATED_REQUIREMENTS_PATH}."
            )

    except Exception as e:
        logger.error(f"Error parsing {PYPROJECT_TOML_PATH}: {str(e)}")
        raise click.exceptions.Exit(code=1)


def install_requirements():
    # Get the vendor path dynamically from wrangler config
    try:
        vendor_path_relative = get_vendor_path_from_wrangler_config(PROJECT_ROOT)
    except Exception as e:
        logger.error(f"Error getting vendor path: {str(e)}")
        raise click.exceptions.Exit(code=1)

    # Make vendor_path absolute by joining with PROJECT_ROOT
    vendor_path = PROJECT_ROOT / vendor_path_relative
    logger.info(f"Using vendor path: {vendor_path} (determined from wrangler config)")

    # Install packages into vendor directory
    if (
        GENERATED_REQUIREMENTS_PATH.is_file()
        and GENERATED_REQUIREMENTS_PATH.stat().st_size > 0
    ):
        vendor_path.mkdir(parents=True, exist_ok=True)
        pyodide_venv_pip_path = (
            PYODIDE_VENV_PATH
            / ("Scripts" if os.name == "nt" else "bin")
            / ("pip.exe" if os.name == "nt" else "pip")
        )
        logger.info(
            f"Installing packages into {vendor_path} using Pyodide pip ({pyodide_venv_pip_path})..."
        )
        run_command(
            [
                str(pyodide_venv_pip_path),
                "install",
                "-t",
                str(vendor_path),
                "-r",
                str(GENERATED_REQUIREMENTS_PATH),
            ]
        )
        logger.info(f"Packages installed in {vendor_path}.")
    else:
        logger.warning(
            f"{GENERATED_REQUIREMENTS_PATH} is empty or was not created. No dependencies to install in {vendor_path}."
        )

    # Create a requirements file for .venv-workers that includes webtypy
    VENV_REQUIREMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Start with existing requirements (if any)
    if (
        GENERATED_REQUIREMENTS_PATH.is_file()
        and GENERATED_REQUIREMENTS_PATH.stat().st_size > 0
    ):
        with open(GENERATED_REQUIREMENTS_PATH, "r") as src, open(
            VENV_REQUIREMENTS_PATH, "w"
        ) as dest:
            dest.write(src.read())
    else:
        # Create a new empty requirements file
        with open(VENV_REQUIREMENTS_PATH, "w") as f:
            pass

    # Add webtypy to the venv requirements file for type hints
    with open(VENV_REQUIREMENTS_PATH, "r") as f:
        current_content = f.read()

    with open(VENV_REQUIREMENTS_PATH, "a") as f:
        if current_content and not current_content.endswith("\n"):
            f.write("\n")
        f.write("webtypy\n")

    # Install packages into .venv-workers so that user's IDE can see the packages.
    venv_bin_path = VENV_WORKERS_PATH / ("Scripts" if os.name == "nt" else "bin")
    venv_python_executable = venv_bin_path / (
        "python.exe" if os.name == "nt" else "python"
    )

    if venv_python_executable.is_file():
        logger.info(f"Installing packages into {VENV_WORKERS_PATH} using uv pip...")
        run_command(
            [
                "uv",
                "pip",
                "install",
                "-p",
                str(venv_python_executable),
                "-r",
                str(VENV_REQUIREMENTS_PATH),
            ]
        )
        logger.info(f"Packages installed in {VENV_WORKERS_PATH}.")
    else:
        logger.warning(
            f"Python executable not found at {venv_python_executable}. Skipping installation in {VENV_WORKERS_PATH}."
        )

    # Clean up temporary files
    if GENERATED_REQUIREMENTS_PATH.exists():
        GENERATED_REQUIREMENTS_PATH.unlink()
        logger.info(f"Cleaned up {GENERATED_REQUIREMENTS_PATH}.")
    if VENV_REQUIREMENTS_PATH.exists():
        VENV_REQUIREMENTS_PATH.unlink()
        logger.info(f"Cleaned up {VENV_REQUIREMENTS_PATH}.")


def check_timestamps():
    """
    Checks if pyproject.toml has been modified since the last sync.

    Returns:
        bool: True if sync is needed, False otherwise
    """

    if not PYPROJECT_TOML_PATH.is_file():
        # If pyproject.toml doesn't exist, we need to abort anyway
        return True

    pyproject_mtime = PYPROJECT_TOML_PATH.stat().st_mtime

    # Check if .venv-workers exists and get its timestamp
    venv_needs_update = True
    if VENV_WORKERS_PATH.is_dir():
        venv_mtime = VENV_WORKERS_PATH.stat().st_mtime
        venv_needs_update = pyproject_mtime > venv_mtime

    # Check if vendor directory exists and get its timestamp
    vendor_needs_update = True
    vendor_path = None
    try:
        vendor_path_relative = get_vendor_path_from_wrangler_config(PROJECT_ROOT)
        vendor_path = PROJECT_ROOT / vendor_path_relative

        if vendor_path.is_dir():
            vendor_mtime = vendor_path.stat().st_mtime
            vendor_needs_update = pyproject_mtime > vendor_mtime
    except Exception as e:
        # If we can't determine the vendor path, default to requiring an update
        vendor_needs_update = True

    # If either directory needs an update, return True
    sync_needed = venv_needs_update or vendor_needs_update

    return sync_needed
