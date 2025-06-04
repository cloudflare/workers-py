import json
import logging
from pathlib import Path
import subprocess

from rich.logging import RichHandler, Console
from rich.theme import Theme
import click
import commentjson

try:
    import tomllib  # Standard in Python 3.11+
except ImportError:
    import tomli as tomllib  # For Python < 3.11

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
    command: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    check: bool = True,
):
    logger.log(RUNNING_LEVEL, f"{' '.join(command)}")
    try:
        process = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if process.stdout:
            logger.log(OUTPUT_LEVEL, f"{process.stdout.strip()}")
        return process
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Error running command: {' '.join(command)}\nExit code: {e.returncode}\nStderr:\n{e.stderr.strip()}"
        )
        raise click.exceptions.Exit(code=e.returncode)
    except FileNotFoundError:
        logger.error(f"Command not found: {command[0]}. Is it installed and in PATH?")
        raise click.exceptions.Exit(code=1)


def get_vendor_path_from_wrangler_config(project_path: Path) -> Path:
    """
    Determines the vendor path by reading the 'main' field from wrangler.toml or wrangler.jsonc.

    The vendor path is assumed to be a directory named 'vendor' inside the same
    directory as the script specified by the 'main' field.

    Args:
        project_path: The root path of the worker project.

    Returns:
        A Path object representing the vendor directory relative to the project_path.

    Raises:
        FileNotFoundError: If neither wrangler.toml nor wrangler.jsonc is found.
        ValueError: If 'main' field is missing, not a string, or if config is malformed.
    """
    wrangler_toml_path = project_path / "wrangler.toml"
    wrangler_jsonc_path = project_path / "wrangler.jsonc"

    config_data = None
    config_file_path = None

    # Check if both configuration files exist
    has_toml = wrangler_toml_path.exists() and wrangler_toml_path.is_file()
    has_jsonc = wrangler_jsonc_path.exists() and wrangler_jsonc_path.is_file()

    if has_toml and has_jsonc:
        raise ValueError(
            f"Ambiguous configuration: both wrangler.toml and wrangler.jsonc exist in {project_path}. Please use only one configuration file."
        )
    elif has_toml:
        config_file_path = wrangler_toml_path
        try:
            with open(config_file_path, "rb") as f:  # Use binary mode for tomllib
                config_data = tomllib.load(f)
        except (tomllib.TOMLDecodeError, ValueError) as e:
            raise ValueError(f"Invalid TOML in {config_file_path}: {e}") from e
    elif has_jsonc:
        config_file_path = wrangler_jsonc_path
        try:
            with open(config_file_path, "r", encoding="utf-8") as f:
                config_data = commentjson.load(f)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Invalid JSONC in {config_file_path}: {e}") from e
        except Exception as e:
            raise ValueError(f"Could not process {config_file_path}: {e}") from e
    else:
        raise FileNotFoundError(
            f"Wrangler configuration file (wrangler.toml or wrangler.jsonc) not found in {project_path}"
        )

    if not config_data:
        raise ValueError(f"Could not load configuration from {config_file_path}")

    main_field = config_data.get("main")
    if main_field is None:
        raise ValueError(f"'main' field not found in {config_file_path}")

    if not isinstance(main_field, str):
        raise ValueError(f"'main' field in {config_file_path} must be a string.")

    if not main_field.strip():
        raise ValueError(f"'main' field in {config_file_path} cannot be empty.")

    main_script_path_relative_to_project = Path(main_field)
    base_dir_relative_to_project = main_script_path_relative_to_project.parent

    vendor_path_relative_to_project = base_dir_relative_to_project / "vendor"

    return vendor_path_relative_to_project
