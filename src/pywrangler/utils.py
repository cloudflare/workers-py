import logging
import subprocess
from pathlib import Path

import click
from functools import cache
from rich.logging import Console, RichHandler
from rich.theme import Theme
from .metadata import PYTHON_COMPAT_VERSIONS
from datetime import datetime
from typing import Literal
import pyjson5
import tomllib

WRANGLER_COMMAND = ["npx", "--yes", "wrangler"]
WRANGLER_CREATE_COMMAND = ["npx", "--yes", "create-cloudflare"]

logger = logging.getLogger(__name__)

SUCCESS_LEVEL = 100
RUNNING_LEVEL = 15
OUTPUT_LEVEL = 16


def setup_logging():
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
        level=logging.INFO,
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


def write_success(msg):
    logging.log(SUCCESS_LEVEL, msg)


def run_command(
    command: list[str | Path],
    cwd: Path | None = None,
    env: dict | None = None,
    check: bool = True,
    capture_output: bool = False,
):
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
    try:
        process = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=check,
            capture_output=capture_output,
            text=True,
        )
        if process.stdout and not capture_output:
            logger.log(OUTPUT_LEVEL, f"{process.stdout.strip()}")
        return process
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Error running command: {' '.join(str(arg) for arg in command)}\nExit code: {e.returncode}\nOutput:\n{e.stdout.strip() if e.stdout else ''}{e.stderr.strip() if e.stderr else ''}"
        )
        raise click.exceptions.Exit(code=e.returncode)
    except FileNotFoundError:
        logger.error(f"Command not found: {command[0]}. Is it installed and in PATH?")
        raise click.exceptions.Exit(code=1)


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


def get_project_root() -> Path:
    return find_pyproject_toml().parent


def check_wrangler_config():
    PROJECT_ROOT = get_project_root()
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
    PROJECT_ROOT = get_project_root()
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


def get_uv_pyodide_interp_name():
    match get_python_version():
        case "3.12":
            v = "3.12.7"
        case "3.13":
            v = "3.13.2"
    return f"cpython-{v}-emscripten-wasm32-musl"


def get_pyodide_index():
    match get_python_version():
        case "3.12":
            v = "0.27.7"
        case "3.13":
            v = "0.28.3"
    return "https://index.pyodide.org/" + v
