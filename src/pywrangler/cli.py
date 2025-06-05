import logging
import subprocess

import click

from pywrangler.sync import (
    check_pyproject_toml,
    check_timestamps,
    create_pyodide_venv,
    create_workers_venv,
    generate_requirements,
    install_pyodide_build,
    install_requirements,
)
from pywrangler.utils import setup_logging, write_success

setup_logging()
logger = logging.getLogger("pywrangler")


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.pass_context
def app(ctx, debug=False):
    """
    A CLI tool for Cloudflare Workers.
    Use 'sync' command for Python package setup.
    Other commands (dev, publish, deploy) are proxied to 'wrangler'.
    """

    # Set the logging level to DEBUG if the debug flag is provided
    if debug:
        logger.setLevel(logging.DEBUG)


@app.command("sync")
@click.option("--force", is_flag=True, help="Force sync even if no changes detected")
def sync_command(force=False):
    """
    Installs Python packages from pyproject.toml into src/vendor.

    Also creates a virtual env for Workers that you can use for testing.
    """
    # Check if pyproject.toml exists
    check_pyproject_toml()

    # Check if sync is needed based on file timestamps
    sync_needed = force or check_timestamps()
    if not sync_needed:
        logger.warning(
            "pyproject.toml hasn't changed since last sync, use --force to ignore timestamp check"
        )
        return

    # Create .venv-workers if it doesn't exist
    create_workers_venv()

    # Set up Pyodide virtual env
    install_pyodide_build()
    create_pyodide_venv()

    # Generate requirements.txt from pyproject.toml by directly parsing the TOML file then install into vendor folder.
    has_requirements = generate_requirements()
    if not has_requirements:
        logger.warning(
            "No dependencies found in [project.dependencies] section of pyproject.toml."
        )
    install_requirements()

    write_success("Sync process completed successfully.")


def _proxy_to_wrangler(command_name, args_list):
    command_to_run = ["npx", "wrangler", command_name] + args_list
    logger.info(f"Passing command to npx wrangler: {' '.join(command_to_run)}")
    try:
        process = subprocess.run(command_to_run, check=False, cwd=".")
        click.get_current_context().exit(process.returncode)
    except FileNotFoundError:
        logger.error(
            "'npx' or 'wrangler' not found. Ensure Node.js and Wrangler are installed and in your PATH."
        )
        click.get_current_context().exit(1)


@app.command(
    "dev",
    help="Proxies the 'dev' command to wrangler. Args are passed through.",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def dev_command(ctx, args):
    ctx.invoke(sync_command, force=False)
    _proxy_to_wrangler("dev", list(args))


@app.command(
    "publish",
    help="Proxies the 'publish' command to wrangler. Args are passed through.",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def publish_command(ctx, args):
    ctx.invoke(sync_command, force=False)
    _proxy_to_wrangler("publish", list(args))


@app.command(
    "deploy",
    help="Proxies the 'deploy' command to wrangler. Args are passed through.",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def deploy_command(ctx, args):
    ctx.invoke(sync_command, force=False)
    _proxy_to_wrangler("deploy", list(args))
