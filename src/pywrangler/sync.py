import logging
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

import click

from .utils import (
    run_command,
    find_pyproject_toml,
    get_python_version,
    get_pyodide_index,
    get_uv_pyodide_interp_name,
    get_project_root,
    read_pyproject_toml,
)


logger = logging.getLogger(__name__)


def get_venv_workers_path() -> Path:
    return get_project_root() / ".venv-workers"


def get_venv_workers_token_path() -> Path:
    return get_venv_workers_path() / ".synced"


def get_vendor_token_path() -> Path:
    return get_project_root() / "python_modules/.synced"


def get_pyodide_venv_path() -> Path:
    return get_venv_workers_path() / "pyodide-venv"


def check_requirements_txt() -> None:
    old_requirements_txt = get_project_root() / "requirements.txt"
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


MIN_UV_VERSION = (0, 8, 10)
MIN_WRANGLER_VERSION = (4, 42, 1)


def check_uv_version() -> None:
    res = run_command(["uv", "--version"], capture_output=True)
    ver_str = res.stdout.split(" ")[1]
    ver = tuple(int(x) for x in ver_str.split("."))
    if ver >= MIN_UV_VERSION:
        return
    min_version_str = ".".join(str(x) for x in MIN_UV_VERSION)
    logger.error(f"uv version at least {min_version_str} required, have {ver_str}.")
    logger.error("Update uv with `uv self update`.")
    raise click.exceptions.Exit(code=1)


def check_wrangler_version() -> None:
    """
    Check that the installed wrangler version is at least 4.42.1.

    Raises:
        click.exceptions.Exit: If wrangler is not installed or version is too old.
    """
    result = run_command(
        ["npx", "--yes", "wrangler", "--version"], capture_output=True, check=False
    )
    if result.returncode != 0:
        logger.error("Failed to get wrangler version. Is wrangler installed?")
        logger.error("Install wrangler with: npm install wrangler@latest")
        raise click.exceptions.Exit(code=1)

    # Parse version from output like "wrangler 4.42.1" or " ⛅️ wrangler 4.42.1"
    version_line = result.stdout.strip()
    # Extract version number using regex
    version_match = re.search(r"(\d+)\.(\d+)\.(\d+)", version_line)

    if not version_match:
        logger.error(f"Could not parse wrangler version from: {version_line}")
        logger.error("Install wrangler with: npm install wrangler@latest")
        raise click.exceptions.Exit(code=1)

    major, minor, patch = map(int, version_match.groups())
    current_version = (major, minor, patch)

    if current_version < MIN_WRANGLER_VERSION:
        min_version_str = ".".join(str(x) for x in MIN_WRANGLER_VERSION)
        current_version_str = ".".join(str(x) for x in current_version)
        logger.error(
            f"wrangler version at least {min_version_str} required, have {current_version_str}."
        )
        logger.error("Update wrangler with: npm install wrangler@latest")
        raise click.exceptions.Exit(code=1)

    logger.debug(
        f"wrangler version {'.'.join(str(x) for x in current_version)} is sufficient"
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


def _install_requirements_to_vendor(requirements: list[str]) -> None:
    vendor_path = get_project_root() / "python_modules"
    logger.debug(f"Using vendor path: {vendor_path}")

    if len(requirements) == 0:
        logger.warning(
            f"Requirements list is empty. No dependencies to install in {vendor_path}."
        )
        return

    # Install packages into vendor directory
    vendor_path.mkdir(parents=True, exist_ok=True)
    relative_vendor_path = vendor_path.relative_to(get_project_root())
    logger.info(
        f"Installing packages into [bold]{relative_vendor_path}[/bold]...",
        extra={"markup": True},
    )
    with temp_requirements_file(requirements) as requirements_file:
        run_command(
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
            env=os.environ | {"VIRTUAL_ENV": get_pyodide_venv_path()},
        )
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


def _install_requirements_to_venv(requirements: list[str]) -> None:
    # Create a requirements file for .venv-workers that includes pyodide-py
    venv_workers_path = get_venv_workers_path()
    project_root = get_project_root()
    relative_venv_workers_path = venv_workers_path.relative_to(project_root)
    requirements = requirements.copy()
    requirements.append("pyodide-py")

    logger.info(
        f"Installing packages into [bold]{relative_venv_workers_path}[/bold]...",
        extra={"markup": True},
    )
    with temp_requirements_file(requirements) as requirements_file:
        run_command(
            [
                "uv",
                "pip",
                "install",
                "-r",
                requirements_file,
            ],
            env=os.environ | {"VIRTUAL_ENV": venv_workers_path},
        )

    get_venv_workers_token_path().touch()
    logger.info(
        f"Packages installed in [bold]{relative_venv_workers_path}[/bold].",
        extra={"markup": True},
    )


def install_requirements(requirements: list[str]) -> None:
    _install_requirements_to_vendor(requirements)
    _install_requirements_to_venv(requirements)


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
