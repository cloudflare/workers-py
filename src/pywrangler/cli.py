import logging
import click
import subprocess
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


@click.group()
@click.pass_context
def app(ctx):
    """
    A CLI tool for Cloudflare Workers.
    Use 'sync' command for Python package setup.
    Other commands (dev, publish, deploy) are proxied to 'wrangler'.
    """
    # This function now primarily serves as a group for subcommands.
    # ctx.obj can be used to pass data to subcommands if needed.
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
    _proxy_to_wrangler("dev", list(args))


@app.command(
    "publish",
    help="Proxies the 'publish' command to wrangler. Args are passed through.",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def publish_command(ctx, args):
    _proxy_to_wrangler("publish", list(args))


@app.command(
    "deploy",
    help="Proxies the 'deploy' command to wrangler. Args are passed through.",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def deploy_command(ctx, args):
    _proxy_to_wrangler("deploy", list(args))


if __name__ == "__main__":
    app()
