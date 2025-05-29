import logging
from pathlib import Path
import subprocess
import click

logger = logging.getLogger(__name__)


def run_command(
    command: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    check: bool = True,
):
    logger.info(f"Running: {' '.join(command)}")
    try:
        process = subprocess.run(
            command, cwd=cwd, env=env, check=check, capture_output=True, text=True
        )
        if process.stdout:
            logger.info(f"Output:\n{process.stdout.strip()}")
        if process.stderr:
            logger.warning(f"Errors/Warnings:\n{process.stderr.strip()}")
        return process
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Error running command: {' '.join(command)}\nExit code: {e.returncode}\nStderr:\n{e.stderr.strip()}"
        )
        raise click.exceptions.Exit(code=e.returncode)
    except FileNotFoundError:
        logger.error(f"Command not found: {command[0]}. Is it installed and in PATH?")
        raise click.exceptions.Exit(code=1)
