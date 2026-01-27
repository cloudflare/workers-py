import logging
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import click

from .utils import (
    check_uv_version,
    check_wrangler_config,
    find_pyproject_toml,
    get_project_root,
    get_pyodide_index,
    get_python_version,
    get_uv_pyodide_interp_name,
    read_pyproject_toml,
    run_command,
)

logger = logging.getLogger(__name__)


def get_venv_workers_path() -> Path:
    return get_project_root() / ".venv-workers"


def get_venv_workers_token_path() -> Path:
    return get_venv_workers_path() / ".synced"


def get_vendor_modules_path() -> Path:
    return get_project_root() / "python_modules"


def get_vendor_token_path() -> Path:
    return get_vendor_modules_path() / ".synced"


def get_pyodide_venv_path() -> Path:
    return get_venv_workers_path() / "pyodide-venv"


def check_requirements_txt() -> None:
    old_requirements_txt = get_project_root() / "requirements.txt"
    if old_requirements_txt.is_file():
        with open(old_requirements_txt) as f:
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


def _get_venv_python_version() -> str | None:
    """
    Retrieves the Python version from the virtual environment.

    Returns:
        The Python version string or None if it cannot be determined.
    """
    venv_workers_path = get_venv_workers_path()
    venv_python = (
        venv_workers_path / "Scripts" / "python.exe"
        if os.name == "nt"
        else venv_workers_path / "bin" / "python"
    )
    if not venv_python.is_file():
        return None

    result = run_command(
        [str(venv_python), "--version"], check=False, capture_output=True
    )
    if result.returncode != 0:
        return None

    return result.stdout.strip()


def create_workers_venv() -> None:
    """
    Creates a virtual environment at `venv_workers_path` if it doesn't exist.
    """
    wanted_python_version = get_python_version()
    logger.debug(f"Using python version from wrangler config: {wanted_python_version}")

    venv_workers_path = get_venv_workers_path()
    if venv_workers_path.is_dir():
        installed_version = _get_venv_python_version()
        if installed_version:
            if wanted_python_version in installed_version:
                logger.debug(
                    f"Virtual environment at {venv_workers_path} already exists."
                )
                return

            logger.warning(
                f"Recreating virtual environment at {venv_workers_path} due to Python version mismatch. "
                f"Found {installed_version}, expected {wanted_python_version}"
            )
        else:
            logger.warning(
                f"Could not determine python version for {venv_workers_path}, recreating."
            )

        shutil.rmtree(venv_workers_path)

    logger.debug(f"Creating virtual environment at {venv_workers_path}...")
    run_command(
        [
            "uv",
            "venv",
            str(venv_workers_path),
            "--python",
            f"python{wanted_python_version}",
        ]
    )


def create_pyodide_venv() -> None:
    pyodide_venv_path = get_pyodide_venv_path()
    if pyodide_venv_path.is_dir():
        logger.debug(
            f"Pyodide virtual environment at {pyodide_venv_path} already exists."
        )
        return

    check_uv_version()
    logger.debug(f"Creating Pyodide virtual environment at {pyodide_venv_path}...")
    pyodide_venv_path.parent.mkdir(parents=True, exist_ok=True)
    interp_name = get_uv_pyodide_interp_name()
    run_command(["uv", "python", "install", interp_name])
    run_command(["uv", "venv", pyodide_venv_path, "--python", interp_name])


def parse_requirements() -> list[str]:
    pyproject_data = read_pyproject_toml()

    # Extract dependencies from [project.dependencies]
    dependencies = pyproject_data.get("project", {}).get("dependencies", [])

    logger.info(f"Found {len(dependencies)} dependencies.")
    return dependencies


@contextmanager
def temp_requirements_file(requirements: list[str]) -> Iterator[str]:
    # Write dependencies to a requirements.txt-style temp file.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt") as temp_file:
        temp_file.write("\n".join(requirements))
        temp_file.flush()
        yield temp_file.name


def _install_requirements_to_vendor(requirements: list[str]) -> str | None:
    """Install packages to the Pyodide vendor directory.

    Returns:
        Error message string if installation failed, None if successful.
    """
    vendor_path = get_vendor_modules_path()
    logger.debug(f"Using vendor path: {vendor_path}")

    if len(requirements) == 0:
        logger.warning(
            f"Requirements list is empty. No dependencies to install in {vendor_path}."
        )
        return None

    # Install packages into vendor directory
    vendor_path.mkdir(parents=True, exist_ok=True)
    relative_vendor_path = vendor_path.relative_to(get_project_root())
    logger.info(
        f"Installing packages into [bold]{relative_vendor_path}[/bold]...",
        extra={"markup": True},
    )
    with temp_requirements_file(requirements) as requirements_file:
        result = run_command(
            [
                "uv",
                "pip",
                "install",
                "--no-build",
                "-r",
                requirements_file,
                "--extra-index-url",
                get_pyodide_index(),
                "--index-strategy",
                "unsafe-best-match",
            ],
            capture_output=True,
            check=False,
            env=os.environ | {"VIRTUAL_ENV": get_pyodide_venv_path()},
        )
        if result.returncode != 0:
            return result.stdout.strip()

        pyv = get_python_version()
        shutil.rmtree(vendor_path)
        shutil.copytree(
            get_pyodide_venv_path() / f"lib/python{pyv}/site-packages", vendor_path
        )

    # Create a pyvenv.cfg file in python_modules to mark it as a virtual environment
    (vendor_path / "pyvenv.cfg").touch()
    get_vendor_token_path().touch()

    logger.info(
        f"Packages installed in [bold]{relative_vendor_path}[/bold].",
        extra={"markup": True},
    )
    return None


def _pip_install_to_venv(
    requirements: list[str],
    venv_path: Path,
    action_name: str,
) -> str | None:
    """Install packages to a venv.

    Returns:
        Error message string if installation failed, None if successful.
    """
    project_root = get_project_root()
    relative_venv_path = venv_path.relative_to(project_root)

    logger.info(
        f"{action_name} [bold]{relative_venv_path}[/bold]...",
        extra={"markup": True},
    )
    with temp_requirements_file(requirements) as requirements_file:
        result = run_command(
            ["uv", "pip", "install", "-r", requirements_file],
            check=False,
            env=os.environ | {"VIRTUAL_ENV": venv_path},
            capture_output=True,
        )
        if result.returncode != 0:
            return result.stdout.strip()

    logger.info(
        f"Packages installed in [bold]{relative_venv_path}[/bold].",
        extra={"markup": True},
    )
    return None


def _install_requirements_to_venv(requirements: list[str]) -> str | None:
    """Install packages to the native venv.

    Uses pinned versions from vendor directory if available to ensure host packages
    accurately reflect what will run in production.

    Returns:
        Error message string if installation failed, None if successful.
    """
    requirements = requirements + ["pyodide-py"]
    error = _pip_install_to_venv(
        requirements,
        get_venv_workers_path(),
        action_name="Installing packages into",
    )
    if error:
        return error

    get_venv_workers_token_path().touch()
    return None


def _get_vendor_package_versions() -> list[str]:
    """Get pinned package versions from pyodide venv (e.g., ["shapely==2.0.7"])."""
    result = run_command(
        ["uv", "pip", "freeze", "--path", get_vendor_modules_path()],
        env=os.environ | {"VIRTUAL_ENV": get_pyodide_venv_path()},
        capture_output=True,
    )
    if result.returncode != 0:
        logger.warning("Failed to get package versions from pyodide venv")
        return []

    packages = []
    for line in result.stdout.strip().split("\n"):
        # filter out empty lines and comments that we cannot handle just in case
        line = line.strip()
        if line and not line.startswith("#") and "==" in line:
            packages.append(line)
    return packages


def install_requirements(requirements: list[str]) -> None:
    # First, install to the Pyodide vendor directory. This determines the exact package
    # versions that will run in production.
    pyodide_error = _install_requirements_to_vendor(requirements)

    # Then install to .venv-workers using the pinned versions from vendor.
    # This ensures host packages accurately reflect what will run in production.
    native_error = _install_requirements_to_venv(_get_vendor_package_versions())

    # Show the native error first (more likely to be actionable), then the Pyodide error.
    if native_error:
        logger.warning(native_error)
        logger.error(
            "Failed to install the requirements defined in your pyproject.toml file. See above for details."
        )
        raise click.exceptions.Exit(code=1)

    if pyodide_error:
        logger.warning(pyodide_error)
        # Handle some common failures and give nicer error messages for them.
        lowered_error = pyodide_error.lower()
        if "invalid peer certificate" in lowered_error:
            logger.error(
                "Installation failed because of an invalid peer certificate. Are your systems certificates correctly installed? Do you have an Enterprise VPN enabled?"
            )
        elif "failed to fetch" in lowered_error:
            logger.error(
                "Installation failed because of a failed fetch. Is your network connection working?"
            )
        elif "no solution found when resolving dependencies" in lowered_error:
            logger.error(
                "Installation failed because the packages you requested are not supported by Python Workers. See above for details."
            )
        else:
            logger.error(
                "Installation of packages into the Python Worker failed. Possibly because these packages are not currently supported. See above for details."
            )
        raise click.exceptions.Exit(code=1)


def _is_out_of_date(token: Path, time: float) -> bool:
    if not token.exists():
        return True
    return time > token.stat().st_mtime


def is_sync_needed() -> bool:
    """
    Checks if pyproject.toml has been modified since the last sync.

    Returns:
        bool: True if sync is needed, False otherwise
    """
    pyproject_toml_path = find_pyproject_toml()
    if not pyproject_toml_path.is_file():
        # If pyproject.toml doesn't exist, we need to abort anyway
        return True

    pyproject_mtime = pyproject_toml_path.stat().st_mtime
    return _is_out_of_date(get_vendor_token_path(), pyproject_mtime) or _is_out_of_date(
        get_venv_workers_token_path(), pyproject_mtime
    )


def sync(force: bool = False, directly_requested: bool = False) -> None:
    # Check if requirements.txt does not exist.
    check_requirements_txt()

    # Check if sync is needed based on file timestamps
    sync_needed = force or is_sync_needed()
    if not sync_needed:
        if directly_requested:
            logger.warning(
                "pyproject.toml hasn't changed since last sync, use --force to ignore timestamp check"
            )
        return

    # Check to make sure a wrangler config file exists.
    check_wrangler_config()

    # Create .venv-workers if it doesn't exist
    create_workers_venv()

    # Set up Pyodide virtual env
    create_pyodide_venv()

    # Generate requirements.txt from pyproject.toml by directly parsing the TOML file then install into vendor folder.
    requirements = parse_requirements()
    if not requirements:
        logger.warning(
            "No dependencies found in [project.dependencies] section of pyproject.toml."
        )
    install_requirements(requirements)
