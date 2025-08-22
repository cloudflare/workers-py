import logging
import subprocess
from pathlib import Path

import click
from rich.logging import Console, RichHandler
from rich.theme import Theme

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
