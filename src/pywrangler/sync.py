import logging
import os
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

import click
import pyjson5

from pywrangler.utils import (
    run_command,
    find_pyproject_toml,
)
from pywrangler.metadata import PYTHON_COMPAT_VERSIONS

try:
    import tomllib  # Standard in Python 3.11+
except ImportError:
    import tomli as tomllib  # For Python < 3.11

logger = logging.getLogger(__name__)

# Define paths
PYPROJECT_TOML_PATH = find_pyproject_toml()
PROJECT_ROOT = PYPROJECT_TOML_PATH.parent
VENV_WORKERS_PATH = PROJECT_ROOT / ".venv-workers"
VENV_WORKERS_TOKEN = PROJECT_ROOT / ".venv-workers/.synced"
PYODIDE_VENV_PATH = VENV_WORKERS_PATH / "pyodide-venv"
VENDOR_TOKEN = PROJECT_ROOT / "python_modules/.synced"
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


def _parse_wrangler_config() -> dict:
    """
    Parse wrangler configuration from either wrangler.toml or wrangler.jsonc.

    Returns:
        dict: Parsed configuration data
    """
    wrangler_toml = PROJECT_ROOT / "wrangler.toml"
    wrangler_jsonc = PROJECT_ROOT / "wrangler.jsonc"

    if wrangler_toml.is_file():
        try:
            with open(wrangler_toml, "rb") as f:
                return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            logger.error(f"Error parsing {wrangler_toml}: {e}")
            raise click.exceptions.Exit(code=1)

    if wrangler_jsonc.is_file():
        try:
            with open(wrangler_jsonc, "r") as f:
                content = f.read()
            return pyjson5.loads(content)
        except (pyjson5.Json5DecoderError, ValueError) as e:
            logger.error(f"Error parsing {wrangler_jsonc}: {e}")
            raise click.exceptions.Exit(code=1)

    return {}


def _get_python_version() -> Literal["3.12", "3.13"]:
    """
    Determine Python version from wrangler configuration.

    Returns:
        Python version string
    """
    config = _parse_wrangler_config()

    if not config:
        logger.error("No wrangler config found")
        raise click.exceptions.Exit(code=1)

    compat_flags = config.get("compatibility_flags", [])

    if "compatibility_date" not in config:
        logger.error("No compatibility_date specified in wrangler config")
        raise click.exceptions.Exit(code=1)
    try:
        compat_date = datetime.strptime(config.get("compatibility_date"), "%Y-%m-%d")
    except ValueError:
        logger.error(
            f"Invalid compatibility_date format: {config.get('compatibility_date')}"
        )
        raise click.exceptions.Exit(code=1)

    # Check if python_workers base flag is present (required for Python workers)
    if "python_workers" not in compat_flags:
        logger.error("`python_workers` compat flag not specified in wrangler config")
        raise click.exceptions.Exit(code=1)

    # Find the most specific Python version based on compat flags and date
    # Sort by version descending to prioritize newer versions
    sorted_versions = sorted(
        PYTHON_COMPAT_VERSIONS, key=lambda x: x.version, reverse=True
    )

    for py_version in sorted_versions:
        # Check if the specific compat flag is present
        if py_version.compat_flag in compat_flags:
            return py_version.version

        # For versions with compat_date, also check the date requirement
        if (
            py_version.compat_date
            and compat_date
            and compat_date >= py_version.compat_date
        ):
            return py_version.version

    logger.error("Could not determine Python version from wrangler config")
    raise click.exceptions.Exit(code=1)


def _get_uv_pyodide_interp_name():
    match _get_python_version():
        case "3.12":
            v = "3.12.7"
        case "3.13":
            v = "3.13.2"
    return f"cpython-{v}-emscripten-wasm32-musl"


def _get_pyodide_index():
    match _get_python_version():
        case "3.12":
            v = "0.27.7"
        case "3.13":
            v = "0.28.3"
    return "https://index.pyodide.org/" + v


def _get_venv_python_version() -> str | None:
    """
    Retrieves the Python version from the virtual environment.

    Returns:
        The Python version string or None if it cannot be determined.
    """
    venv_python = (
        VENV_WORKERS_PATH / "Scripts" / "python.exe"
        if os.name == "nt"
        else VENV_WORKERS_PATH / "bin" / "python"
    )
    if not venv_python.is_file():
        return None

    result = run_command(
        [str(venv_python), "--version"], check=False, capture_output=True
    )
    if result.returncode != 0:
        return None

    return result.stdout.strip()


def create_workers_venv():
    """
    Creates a virtual environment at `VENV_WORKERS_PATH` if it doesn't exist.
    """
    wanted_python_version = _get_python_version()
    logger.debug(f"Using python version from wrangler config: {wanted_python_version}")

    if VENV_WORKERS_PATH.is_dir():
        installed_version = _get_venv_python_version()
        if installed_version:
            if wanted_python_version in installed_version:
                logger.debug(
                    f"Virtual environment at {VENV_WORKERS_PATH} already exists."
                )
                return

            logger.warning(
                f"Recreating virtual environment at {VENV_WORKERS_PATH} due to Python version mismatch. "
                f"Found {installed_version}, expected {wanted_python_version}"
            )
        else:
            logger.warning(
                f"Could not determine python version for {VENV_WORKERS_PATH}, recreating."
            )

        shutil.rmtree(VENV_WORKERS_PATH)

    logger.debug(f"Creating virtual environment at {VENV_WORKERS_PATH}...")
    run_command(
        [
            "uv",
            "venv",
            str(VENV_WORKERS_PATH),
            "--python",
            f"python{wanted_python_version}",
        ]
    )


MIN_UV_VERSION = (0, 8, 10)


def check_uv_version():
    res = run_command(["uv", "--version"], capture_output=True)
    ver_str = res.stdout.split(" ")[1]
    ver = tuple(int(x) for x in ver_str.split("."))
    if ver >= MIN_UV_VERSION:
        return
    min_version_str = ".".join(str(x) for x in MIN_UV_VERSION)
    logger.error(f"uv version at least {min_version_str} required, have {ver_str}.")
    logger.error("Update uv with `uv self update`.")
    raise click.exceptions.Exit(code=1)


def create_pyodide_venv():
    if PYODIDE_VENV_PATH.is_dir():
        logger.debug(
            f"Pyodide virtual environment at {PYODIDE_VENV_PATH} already exists."
        )
        return

    check_uv_version()
    logger.debug(f"Creating Pyodide virtual environment at {PYODIDE_VENV_PATH}...")
    PYODIDE_VENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    interp_name = _get_uv_pyodide_interp_name()
    run_command(["uv", "python", "install", interp_name])
    run_command(["uv", "venv", PYODIDE_VENV_PATH, "--python", interp_name])


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


@contextmanager
def temp_requirements_file(requirements: list[str]):
    # Write dependencies to a requirements.txt-style temp file.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt") as temp_file:
        temp_file.write("\n".join(requirements))
        temp_file.flush()
        yield temp_file.name


def _install_requirements_to_vendor(requirements: list[str]):
    vendor_path = PROJECT_ROOT / "python_modules"
    logger.debug(f"Using vendor path: {vendor_path}")

    if len(requirements) == 0:
        logger.warning(
            f"Requirements list is empty. No dependencies to install in {vendor_path}."
        )
        return

    # Install packages into vendor directory
    vendor_path.mkdir(parents=True, exist_ok=True)
    relative_vendor_path = vendor_path.relative_to(PROJECT_ROOT)
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
                _get_pyodide_index(),
                "--index-strategy",
                "unsafe-best-match",
            ],
            env=os.environ | {"VIRTUAL_ENV": PYODIDE_VENV_PATH},
        )
        pyv = _get_python_version()
        shutil.rmtree(vendor_path)
        shutil.copytree(
            PYODIDE_VENV_PATH / f"lib/python{pyv}/site-packages", vendor_path
        )

    # Create a pyvenv.cfg file in python_modules to mark it as a virtual environment
    (vendor_path / "pyvenv.cfg").touch()
    VENDOR_TOKEN.touch()

    logger.info(
        f"Packages installed in [bold]{relative_vendor_path}[/bold].",
        extra={"markup": True},
    )


def _install_requirements_to_venv(requirements: list[str]):
    # Create a requirements file for .venv-workers that includes webtypy and pyodide-py
    relative_venv_workers_path = VENV_WORKERS_PATH.relative_to(PROJECT_ROOT)
    requirements = requirements.copy()
    requirements.append("webtypy")
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
            env=os.environ | {"VIRTUAL_ENV": VENV_WORKERS_PATH},
        )
    VENV_WORKERS_TOKEN.touch()
    logger.info(
        f"Packages installed in [bold]{relative_venv_workers_path}[/bold].",
        extra={"markup": True},
    )


def install_requirements(requirements: list[str]):
    _install_requirements_to_vendor(requirements)
    _install_requirements_to_venv(requirements)


def _is_out_of_date(token: Path, time: float) -> bool:
    if not token.exists():
        return True
    return time > token.stat().st_mtime


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
    return _is_out_of_date(VENDOR_TOKEN, pyproject_mtime) or _is_out_of_date(
        VENV_WORKERS_TOKEN, pyproject_mtime
    )
