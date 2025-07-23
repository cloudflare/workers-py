import logging
import os
from pathlib import Path
import tempfile

import click

from pywrangler.utils import (
    run_command,
    find_pyproject_toml,
)

try:
    import tomllib  # Standard in Python 3.11+
except ImportError:
    import tomli as tomllib  # For Python < 3.11

logger = logging.getLogger(__name__)

# Define paths
PYPROJECT_TOML_PATH = find_pyproject_toml()
PROJECT_ROOT = PYPROJECT_TOML_PATH.parent
VENV_WORKERS_PATH = PROJECT_ROOT / ".venv-workers"
PYODIDE_VENV_PATH = VENV_WORKERS_PATH / "pyodide-venv"
VENV_REQUIREMENTS_PATH = VENV_WORKERS_PATH / "temp-venv-requirements.txt"


def check_requirements_txt():
    old_requirements_txt = PROJECT_ROOT / "requirements.txt"
    if old_requirements_txt.is_file():
        with open(old_requirements_txt, "r") as f:
            requirements = f.read().splitlines()
            logger.warning(
                "Specifying Python Packages in requirements.txt is no longer supported, please use pyproject.toml instead.\n"
                + "Put the following in your pyproject.toml to vendor the packages currently in your requirements.txt:"
            )
            pyproject_text = "dependencies = [\n"
            pyproject_text += ",\n".join([f'  "{x}"' for x in requirements])
            pyproject_text += "\n]"
            logger.warning(pyproject_text)

        logger.error(
            f"{old_requirements_txt} exists. Delete the file to continue. Exiting."
        )
        raise click.exceptions.Exit(code=1)


def check_wrangler_config():
    wrangler_jsonc = PROJECT_ROOT / "wrangler.jsonc"
    wrangler_toml = PROJECT_ROOT / "wrangler.toml"
    if not wrangler_jsonc.is_file() and not wrangler_toml.is_file():
        logger.error(
            f"{wrangler_jsonc} or {wrangler_toml} not found in {PROJECT_ROOT}."
        )
        raise click.exceptions.Exit(code=1)


def create_workers_venv():
    """
    Creates a virtual environment at `VENV_WORKERS_PATH` if it doesn't exist.
    """
    if VENV_WORKERS_PATH.is_dir():
        logger.debug(f"Virtual environment at {VENV_WORKERS_PATH} already exists.")
        return

    logger.debug(f"Creating virtual environment at {VENV_WORKERS_PATH}...")
    run_command(["uv", "venv", str(VENV_WORKERS_PATH), "--python", "python3.12"])


def _get_pyodide_cli_path():
    venv_bin_path = VENV_WORKERS_PATH / ("Scripts" if os.name == "nt" else "bin")
    pyodide_cli_path = venv_bin_path / ("pyodide.exe" if os.name == "nt" else "pyodide")
    return pyodide_cli_path


def install_pyodide_build():
    pyodide_cli_path = _get_pyodide_cli_path()

    if pyodide_cli_path.is_file():
        logger.debug(
            f"pyodide-build CLI already found at {pyodide_cli_path} (skipping install.)"
        )
        return

    logger.debug(
        f"Installing pyodide-build in {VENV_WORKERS_PATH} using 'uv pip install'..."
    )
    venv_bin_path = pyodide_cli_path.parent

    # Ensure the python executable path is correct for the venv
    venv_python_executable = venv_bin_path / (
        "python.exe" if os.name == "nt" else "python"
    )
    if not venv_python_executable.is_file():
        logger.error(f"Python executable not found at {venv_python_executable}")
        raise click.exceptions.Exit(code=1)

    run_command(["uv", "pip", "install", "-p", str(venv_python_executable), "pip"])

    run_command(
        ["uv", "pip", "install", "-p", str(venv_python_executable), "pyodide-build"]
    )


def create_pyodide_venv():
    pyodide_cli_path = _get_pyodide_cli_path()
    if PYODIDE_VENV_PATH.is_dir():
        logger.debug(
            f"Pyodide virtual environment at {PYODIDE_VENV_PATH} already exists."
        )
        return

    logger.debug(f"Creating Pyodide virtual environment at {PYODIDE_VENV_PATH}...")
    PYODIDE_VENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    run_command([str(pyodide_cli_path), "venv", str(PYODIDE_VENV_PATH)])


def parse_requirements() -> list[str]:
    logger.debug(f"Reading dependencies from {PYPROJECT_TOML_PATH}...")
    try:
        with open(PYPROJECT_TOML_PATH, "rb") as f:
            pyproject_data = tomllib.load(f)

        # Extract dependencies from [project.dependencies]
        dependencies = pyproject_data.get("project", {}).get("dependencies", [])

        logger.info(f"Found {len(dependencies)} dependencies.")
        return dependencies
    except tomllib.TOMLDecodeError as e:
        logger.error(f"Error parsing {PYPROJECT_TOML_PATH}: {str(e)}")
        raise click.exceptions.Exit(code=1)


def _install_requirements_to_vendor(requirements: list[str]):
    vendor_path = PROJECT_ROOT / "python_modules"
    logger.debug(f"Using vendor path: {vendor_path}")

    if len(requirements) == 0:
        logger.warning(
            f"Requirements list is empty. No dependencies to install in {vendor_path}."
        )
        return

    # Write dependencies to a requirements.txt-style temp file.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", dir=PYODIDE_VENV_PATH
    ) as temp_file:
        temp_file.write("\n".join(requirements))
        temp_file.flush()
        temp_file_path = Path(temp_file.name)

        # Install packages into vendor directory
        vendor_path.mkdir(parents=True, exist_ok=True)
        pyodide_venv_pip_path = (
            PYODIDE_VENV_PATH
            / ("Scripts" if os.name == "nt" else "bin")
            / ("pip.exe" if os.name == "nt" else "pip")
        )
        relative_vendor_path = vendor_path.relative_to(PROJECT_ROOT)
        logger.info(
            f"Installing packages into [bold]{relative_vendor_path}[/bold] using Pyodide pip...",
            extra={"markup": True},
        )
        run_command(
            [
                str(pyodide_venv_pip_path),
                "install",
                "-t",
                str(vendor_path),
                "-r",
                str(temp_file_path),
            ]
        )
        logger.info(
            f"Packages installed in [bold]{relative_vendor_path}[/bold].",
            extra={"markup": True},
        )


def _install_requirements_to_venv(requirements: list[str]):
    # Create a requirements file for .venv-workers that includes webtypy and pyodide-py
    VENV_REQUIREMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    requirements = requirements.copy()
    requirements.append("webtypy")
    requirements.append("pyodide-py")

    # Write dependencies to a requirements.txt-style temp file.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", dir=VENV_REQUIREMENTS_PATH.parent
    ) as temp_file:
        temp_file.write("\n".join(requirements))
        temp_file.flush()
        temp_file_path = Path(temp_file.name)

        # Install packages into .venv-workers so that user's IDE can see the packages.
        venv_bin_path = VENV_WORKERS_PATH / ("Scripts" if os.name == "nt" else "bin")
        venv_python_executable = venv_bin_path / (
            "python.exe" if os.name == "nt" else "python"
        )

        # For nicer logs, output the relative path.
        relative_venv_workers_path = VENV_WORKERS_PATH.relative_to(PROJECT_ROOT)
        if venv_python_executable.is_file():
            logger.info(
                f"Installing packages into [bold]{relative_venv_workers_path}[/bold] using uv pip...",
                extra={"markup": True},
            )
            run_command(
                [
                    "uv",
                    "pip",
                    "install",
                    "-p",
                    venv_python_executable,
                    "-r",
                    str(temp_file_path),
                ]
            )
            logger.info(
                f"Packages installed in [bold]{relative_venv_workers_path}[/bold].",
                extra={"markup": True},
            )
        else:
            logger.warning(
                f"Python executable not found at {venv_python_executable}. Skipping installation in [bold]{relative_venv_workers_path}[/bold].",
                extra={"markup": True},
            )


def install_requirements(requirements: list[str]):
    _install_requirements_to_vendor(requirements)
    _install_requirements_to_venv(requirements)


def is_sync_needed():
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
    if not VENV_WORKERS_PATH.is_dir():
        return True

    venv_mtime = VENV_WORKERS_PATH.stat().st_mtime
    venv_needs_update = pyproject_mtime > venv_mtime
    if venv_needs_update:
        return True

    # Check if vendor directory exists and get its timestamp
    vendor_path = PROJECT_ROOT / "python_modules"
    if not vendor_path.is_dir():
        return True

    vendor_mtime = vendor_path.stat().st_mtime
    vendor_needs_update = pyproject_mtime > vendor_mtime
    return vendor_needs_update
