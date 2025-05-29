import logging
import click
from rich.logging import RichHandler

from pywrangler.sync import (
    create_workers_venv,
    install_requirements,
    install_pyodide_build,
    create_pyodide_venv,
    generate_requirements,
    check_pyproject_toml,
)


# Configure Rich logger
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    force=True,  # Ensure this configuration is applied
    handlers=[RichHandler(rich_tracebacks=True, show_time=False, console=None)],
)
logger = logging.getLogger("pywrangler")


@click.group(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
@click.pass_context
def app(ctx):
    """
    A CLI tool for Cloudflare Workers.
    Use 'sync' command for Python package setup.
    Other commands are passed to 'wrangler'.
    """
    pass


@app.command("sync")
def sync_command():
    """
    Installs Python packages from pyproject.toml into src/vendor.

    Also creates a virtual env for Workers that you can use for testing.
    """
    logger.info("Starting sync process...")

    # Check if pyproject.toml exists
    check_pyproject_toml()

    # Create .venv-workers if it doesn't exist
    create_workers_venv()

    # Set up Pyodide virtual env
    install_pyodide_build()
    create_pyodide_venv()

    # Generate requirements.txt from pyproject.toml by directly parsing the TOML file then install into vendor folder.
    generate_requirements()
    install_requirements()

    logger.info("Sync process completed successfully.")


if __name__ == "__main__":
    app()
