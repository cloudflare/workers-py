import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Literal, TypedDict, cast

import click
import pyjson5
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

from .metadata import PYTHON_COMPAT_VERSIONS

WRANGLER_COMMAND = ["npx", "--yes", "wrangler"]
WRANGLER_CREATE_COMMAND = ["npx", "--yes", "create-cloudflare"]

logger = logging.getLogger(__name__)

SUCCESS_LEVEL = logging.CRITICAL + 50
RUNNING_LEVEL = logging.DEBUG + 5
OUTPUT_LEVEL = logging.DEBUG + 6

# Valid log levels for PYWRANGLER_LOG environment variable
_LOG_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,  # alias
    "error": logging.ERROR,
}


def setup_logging() -> int:
    """
    Configure logging with Rich handler.

    Reads PYWRANGLER_LOG environment variable to set log level.
    Valid values: debug, info, warning, warn, error (case-insensitive).
    Defaults to INFO if not set or invalid.

    Returns:
        The configured logging level (e.g., logging.DEBUG, logging.INFO).
    """
    # Determine log level from environment variable
    env_level = os.environ.get("PYWRANGLER_LOG", "").lower().strip()
    if env_level and env_level not in _LOG_LEVEL_MAP:
        # Print warning to stderr for invalid value (before logging is configured)
        print(
            f"Warning: Invalid PYWRANGLER_LOG value '{env_level}'. "
            f"Valid values: {', '.join(sorted(set(_LOG_LEVEL_MAP.keys())))}. "
            "Defaulting to 'info'.",
            file=sys.stderr,
        )
        log_level = logging.INFO
    elif env_level:
        log_level = _LOG_LEVEL_MAP[env_level]
    else:
        log_level = logging.INFO

    console = Console(
        theme=Theme(
            {
                "logging.level.success": "bold green",
                "logging.level.debug": "magenta",
                "logging.level.running": "cyan",
                "logging.level.output": "cyan",
            }
        )
    )

    # Configure Rich logger
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        force=True,  # Ensure this configuration is applied
        handlers=[
            RichHandler(
                rich_tracebacks=True, show_time=False, console=console, show_path=False
            )
        ],
    )
    logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")
    logging.addLevelName(RUNNING_LEVEL, "RUNNING")
    logging.addLevelName(OUTPUT_LEVEL, "OUTPUT")

    return log_level


def _get_pywrangler_version() -> str:
    """Get the version of pywrangler."""
    try:
        from importlib.metadata import version

        return version("workers-py")
    except Exception:
        return "unknown"


def log_startup_info() -> None:
    """
    Log startup information for debugging.
    """
    logger.debug(f"pywrangler version: {_get_pywrangler_version()}")
    logger.debug(f"Python: {platform.python_version()}")
    logger.debug(f"Platform: {sys.platform}")
    logger.debug(f"Working directory: {Path.cwd()}")


def write_success(msg: str) -> None:
    logging.log(SUCCESS_LEVEL, msg)


def run_command(
    command: list[str],
    cwd: Path | None = None,
    env: Mapping[str, str | Path] | None = None,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """
    Runs a command and handles logging and errors.

    Args:
        command: The command to run as a list of strings.
        cwd: The working directory.
        env: Environment variables.
        check: If True, raise an exception on non-zero exit codes.
        capture_output: If True, capture and return stdout/stderr.

    Returns:
        A subprocess.CompletedProcess instance.
    """
    logger.log(RUNNING_LEVEL, f"{' '.join(str(arg) for arg in command)}")

    # Some tools like `npm` may be a batch file on Windows (npm.cmd), and calling them only by
    # name may fails in subprocess.run. Use shutil.which to find the real name.
    abspath = shutil.which(command[0])
    if not abspath:
        logger.error(f"Command not found: {command[0]}. Is it installed and in PATH?")
        raise click.exceptions.Exit(code=1)

    realname = str(Path(command[0]).with_name(Path(abspath).name))
    command = [realname] + command[1:]
    try:
        kwargs = {}
        if capture_output:
            kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        process = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=check,
            text=True,
            encoding="utf-8",
            **kwargs,
        )  # type: ignore[call-overload]
        if process.stdout and not capture_output:
            logger.log(OUTPUT_LEVEL, f"{process.stdout.strip()}")
        return process  # type: ignore[no-any-return]
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Error running command: {' '.join(str(arg) for arg in command)}\nExit code: {e.returncode}\nOutput:\n{e.stdout.strip() if e.stdout else ''}"
        )
        raise click.exceptions.Exit(code=e.returncode) from None
    except FileNotFoundError:
        logger.error(f"Command not found: {command[0]}. Is it installed and in PATH?")
        raise click.exceptions.Exit(code=1) from None


@cache
def find_pyproject_toml() -> Path:
    """
    Search for pyproject.toml starting from current working directory and going up the directory tree.

    Returns:
        Path to pyproject.toml if found.

    Raises:
        click.exceptions.Exit: If pyproject.toml is not found in the directory tree.
    """

    parent_dirs = (Path.cwd().resolve() / "dummy").parents
    for current_dir in parent_dirs:
        pyproject_path = current_dir / "pyproject.toml"
        if pyproject_path.is_file():
            return pyproject_path

    logger.error(
        f"pyproject.toml not found in {Path.cwd().resolve()} or any parent directories"
    )
    raise click.exceptions.Exit(code=1)


class PyProjectProject(TypedDict):
    dependencies: list[str]


class PyProject(TypedDict):
    project: PyProjectProject


def read_pyproject_toml() -> PyProject:
    pyproject_toml = find_pyproject_toml()
    logger.debug(f"Reading {pyproject_toml}...")
    try:
        with open(pyproject_toml, "rb") as f:
            return cast(PyProject, tomllib.load(f))
    except tomllib.TOMLDecodeError as e:
        logger.error(f"Error parsing {pyproject_toml}: {str(e)}")
        raise click.exceptions.Exit(code=1) from None


def get_project_root() -> Path:
    return find_pyproject_toml().parent


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


def check_wrangler_config() -> None:
    PROJECT_ROOT = get_project_root()
    wrangler_jsonc = PROJECT_ROOT / "wrangler.jsonc"
    wrangler_toml = PROJECT_ROOT / "wrangler.toml"
    if not wrangler_jsonc.is_file() and not wrangler_toml.is_file():
        logger.error(
            f"{wrangler_jsonc} or {wrangler_toml} not found in {PROJECT_ROOT}."
        )
        raise click.exceptions.Exit(code=1)


class WranglerConfig(TypedDict, total=False):
    compatibility_date: str
    compatibility_flags: list[str]


def _parse_wrangler_config() -> WranglerConfig:
    """
    Parse wrangler configuration from either wrangler.toml or wrangler.jsonc.

    Returns:
        dict: Parsed configuration data
    """
    PROJECT_ROOT = get_project_root()
    wrangler_toml = PROJECT_ROOT / "wrangler.toml"
    wrangler_jsonc = PROJECT_ROOT / "wrangler.jsonc"

    if wrangler_toml.is_file():
        try:
            with open(wrangler_toml, "rb") as f:
                return cast(WranglerConfig, tomllib.load(f))
        except tomllib.TOMLDecodeError as e:
            logger.error(f"Error parsing {wrangler_toml}: {e}")
            raise click.exceptions.Exit(code=1) from None

    if wrangler_jsonc.is_file():
        try:
            with open(wrangler_jsonc) as f:
                content = f.read()
            return cast(WranglerConfig, pyjson5.loads(content))
        except (pyjson5.Json5DecoderException, ValueError) as e:
            logger.error(f"Error parsing {wrangler_jsonc}: {e}")
            raise click.exceptions.Exit(code=1) from None

    return {}


@cache
def get_python_version() -> Literal["3.12", "3.13"]:
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
    compat_date_str = config.get("compatibility_date", None)
    if compat_date_str is None:
        logger.error("No compatibility_date specified in wrangler config")
        raise click.exceptions.Exit(code=1)
    try:
        compat_date = datetime.strptime(compat_date_str, "%Y-%m-%d")
    except ValueError:
        logger.error(
            f"Invalid compatibility_date format: {config.get('compatibility_date')}"
        )
        raise click.exceptions.Exit(code=1) from None

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
        if py_version.compat_date and compat_date >= py_version.compat_date:
            return py_version.version

    logger.error("Could not determine Python version from wrangler config")
    raise click.exceptions.Exit(code=1)


def get_uv_pyodide_interp_name() -> str:
    match get_python_version():
        case "3.12":
            v = "3.12.7"
        case "3.13":
            v = "3.13.2"
    return f"cpython-{v}-emscripten-wasm32-musl"


def get_pyodide_index() -> str:
    match get_python_version():
        case "3.12":
            v = "0.27.7"
        case "3.13":
            v = "0.28.3"
    return "https://index.pyodide.org/" + v
