import configparser
import logging
import os
import shutil
from pathlib import Path

import click

from .resolve import (
    MANAGED_SDK_PACKAGE,
    InstallPlan,
    resolve_requirements,
)
from .utils import (
    check_uv_version,
    check_wrangler_config,
    find_pyproject_toml,
    get_lockfile_path,
    get_project_root,
    get_python_version,
    get_pywrangler_config,
    get_pywrangler_version,
    get_uv_pyodide_interp_name,
    run_command,
    temp_requirements_file,
)

logger = logging.getLogger(__name__)

# Env vars that can cause uv to target the wrong Python environment.
_UV_CONFLICTING_ENV_VARS = (
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "UV_PYTHON",
    "UV_PROJECT_ENVIRONMENT",
    "PYTHONHOME",
)


def _env_with_venv(venv_path: Path) -> dict[str, str]:
    """Build a subprocess env that points VIRTUAL_ENV at *venv_path*.

    Strips env vars that could redirect uv to a different environment,
    then sets VIRTUAL_ENV explicitly.  This is preferred over ``--python``
    for pyodide venvs because ``--python <dir>`` on Windows can cause uv
    to install packages outside the venv's site-packages.
    """
    env = {k: v for k, v in os.environ.items() if k not in _UV_CONFLICTING_ENV_VARS}
    env["VIRTUAL_ENV"] = str(venv_path)
    return env


def get_venv_workers_path() -> Path:
    return get_project_root() / ".venv-workers"


def get_venv_workers_token_path() -> Path:
    return get_venv_workers_path() / ".synced"


def get_vendor_modules_path() -> Path:
    return get_project_root() / "python_modules"


def get_vendor_token_path() -> Path:
    return get_vendor_modules_path() / ".synced"


def get_pyodide_venv_path() -> Path:
    return get_venv_workers_path() / "pyodide-venv"


def check_requirements_txt() -> None:
    old_requirements_txt = get_project_root() / "requirements.txt"
    if old_requirements_txt.is_file():
        with open(old_requirements_txt) as f:
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


def _ensure_venv_version(venv_path: Path, wanted: str) -> bool:
    """Check *venv_path* exists and its Python matches *wanted*.

    Returns True if the venv is up-to-date, False if it was removed
    (or never existed) and must be recreated.
    """
    if not venv_path.is_dir():
        return False

    pyvenv_cfg = venv_path / "pyvenv.cfg"
    if not pyvenv_cfg.is_file():
        logger.warning(
            f"Could not determine python version for {venv_path}, recreating."
        )
        shutil.rmtree(venv_path)
        return False

    cfg = configparser.ConfigParser()
    # pyvenv.cfg has no section headers; inject one so ConfigParser can parse it.
    cfg.read_string("[pyvenv]\n" + pyvenv_cfg.read_text())
    installed = cfg.get("pyvenv", "version_info", fallback=None)

    if installed is None:
        logger.warning(
            f"Could not determine python version for {venv_path}, recreating."
        )
        shutil.rmtree(venv_path)
        return False

    if wanted in installed:
        logger.debug(f"Virtual environment at {venv_path} already exists.")
        return True

    logger.warning(
        f"Recreating {venv_path} due to Python version mismatch. "
        f"Found {installed}, expected {wanted}"
    )
    shutil.rmtree(venv_path)
    return False


def create_workers_venv() -> None:
    wanted_python_version = get_python_version()
    logger.debug(f"Using python version from wrangler config: {wanted_python_version}")

    venv_workers_path = get_venv_workers_path()
    if _ensure_venv_version(venv_workers_path, wanted_python_version):
        return

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


def create_pyodide_venv() -> None:
    pyodide_venv_path = get_pyodide_venv_path()
    wanted_python_version = get_python_version()
    if _ensure_venv_version(pyodide_venv_path, wanted_python_version):
        return

    check_uv_version()
    logger.debug(f"Creating Pyodide virtual environment at {pyodide_venv_path}...")
    pyodide_venv_path.parent.mkdir(parents=True, exist_ok=True)
    interp_name = get_uv_pyodide_interp_name()
    run_command(["uv", "venv", str(pyodide_venv_path), "--python", interp_name])


def _install_requirements_to_vendor(
    plan: InstallPlan, allow_build: bool = False
) -> str | None:
    """Install packages to the Pyodide vendor directory from pylock.toml.

    By default ``--no-build`` is passed so only prebuilt wheels install. When
    *allow_build* is True, source distributions / local directory sources are
    allowed to build.

    Returns:
        Error message string if installation failed, None if successful.
    """
    vendor_path = get_vendor_modules_path()
    logger.debug(f"Using vendor path: {vendor_path}")

    if len(plan.requirements) == 0:
        logger.warning(
            f"Requirements list is empty. No dependencies to install in {vendor_path}."
        )
        return None

    # Install packages into vendor directory
    vendor_path.mkdir(parents=True, exist_ok=True)
    relative_vendor_path = vendor_path.relative_to(get_project_root())
    logger.info(
        f"Installing packages into [bold]{relative_vendor_path}[/bold]...",
        extra={"markup": True},
    )

    # Clear pyodide venv site-packages so stale packages from previous syncs
    # don't carry over into python_modules.
    pyv = get_python_version()
    site_packages_path = (
        f"lib/python{pyv}/site-packages" if os.name != "nt" else "Lib/site-packages"
    )
    pyodide_site_packages = get_pyodide_venv_path() / site_packages_path
    if pyodide_site_packages.is_dir():
        shutil.rmtree(pyodide_site_packages)
        pyodide_site_packages.mkdir()

    install_cmd = ["uv", "pip", "install"]
    if not allow_build:
        install_cmd.append("--no-build")
    else:
        # uv caches built wheels for local sources keyed on their path, so edits
        # to local checkouts wouldn't be picked up. Refresh the build cache for
        # those packages so `sync` always rebuilds them.
        for name in plan.local_packages:
            install_cmd += ["--refresh-package", name]
    install_cmd += ["-r", str(plan.lockfile), "--preview-features", "pylock"]
    result = run_command(
        install_cmd,
        capture_output=True,
        check=False,
        env=_env_with_venv(get_pyodide_venv_path()),
    )

    if result.returncode != 0:
        return result.stdout.strip()

    shutil.rmtree(vendor_path)
    shutil.copytree(pyodide_site_packages, vendor_path)

    # Create a pyvenv.cfg file in python_modules to mark it as a virtual environment
    (vendor_path / "pyvenv.cfg").touch()
    _write_sync_token(get_vendor_token_path())

    logger.info(
        f"Packages installed in [bold]{relative_vendor_path}[/bold].",
        extra={"markup": True},
    )
    return None


def _install_requirements_to_venv(constraints: list[str]) -> str | None:
    """Install packages to the native venv.

    Installs the project requirements using pyproject.toml, constrained to the
    versions that were resolved for Pyodide whenever a version is available.

    Returns:
        Error message string if installation failed, None if successful.
    """

    venv_workers_path = get_venv_workers_path()
    project_root = get_project_root()
    relative_venv_workers_path = venv_workers_path.relative_to(project_root)

    logger.info(
        f"Installing packages into [bold]{relative_venv_workers_path}[/bold]...",
        extra={"markup": True},
    )

    extra_packages = [
        "pyodide-py",
        MANAGED_SDK_PACKAGE,
    ]

    with temp_requirements_file(constraints) as constraints_file:
        result = run_command(
            [
                "uv",
                "pip",
                "install",
                "-r",
                str(project_root / "pyproject.toml"),
                "-c",
                constraints_file,
                *extra_packages,
            ],
            check=False,
            capture_output=True,
            env=_env_with_venv(venv_workers_path),
        )
        if result.returncode != 0:
            return result.stdout.strip()

    _write_sync_token(get_venv_workers_token_path())
    logger.info(
        f"Packages installed in [bold]{relative_venv_workers_path}[/bold].",
        extra={"markup": True},
    )

    return None


def _log_installed_packages(venv_path: Path) -> None:
    result = run_command(
        [
            "uv",
            "pip",
            "list",
            "--format=freeze",
        ],
        capture_output=True,
        check=False,
        env=_env_with_venv(venv_path),
    )
    if result.returncode == 0 and result.stdout.strip():
        logger.debug("Installed packages:")
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                logger.debug(f"  {line.strip()}")


def _parse_pip_freeze(result: str) -> list[str]:
    packages = []
    for line in result.strip().split("\n"):
        # filter out empty lines and comments that we cannot handle just in case
        line = line.strip()
        if line and not line.startswith("#") and "==" in line:
            packages.append(line)
    return packages


def _get_vendor_package_versions() -> list[str]:
    """Get pinned package versions from pyodide venv (e.g., ["shapely==2.0.7"])."""
    result = run_command(
        [
            "uv",
            "pip",
            "freeze",
            # This output is parsed, and FORCE_COLOR-style env vars make uv
            # colorize even when captured. "\x1b[1mshapely\x1b[0m==2.0.7"
            # still contains "==", so it survives _parse_pip_freeze and then
            # trips uv's requirements parser: error: Unexpected '<ESC>',
            # expected '-c', '-e', '-r' or the start of a requirement.
            "--color",
            "never",
            "--path",
            str(get_vendor_modules_path()),
        ],
        capture_output=True,
        env=_env_with_venv(get_pyodide_venv_path()),
    )
    if result.returncode != 0:
        logger.warning("Failed to get package versions from pyodide venv")
        return []

    return _parse_pip_freeze(result.stdout)


def install_requirements(plan: InstallPlan, allow_build: bool = False) -> None:
    # First, install to the Pyodide vendor directory. This determines the exact package
    # versions that will run in production.
    pyodide_error = _install_requirements_to_vendor(plan, allow_build=allow_build)

    # Then install to .venv-workers using the pinned versions from vendor.
    # This ensures host packages accurately reflect what will run in production.
    # If the installation to the Pyodide vendor directory fails, use the original requirements
    # to see if it fails in the native venv as well.
    if pyodide_error:
        host_constraints = []
    else:
        host_constraints = _get_vendor_package_versions()
    native_error = _install_requirements_to_venv(host_constraints)

    # Show the native error first (more likely to be actionable), then the Pyodide error.
    if native_error:
        logger.warning(native_error)
        logger.error(
            "Failed to install the requirements defined in your pyproject.toml file. See above for details."
        )
        raise click.exceptions.Exit(code=1)

    if pyodide_error:
        logger.warning(pyodide_error)
        # Handle some common failures and give nicer error messages for them.
        lowered_error = pyodide_error.lower()
        if "invalid peer certificate" in lowered_error:
            logger.error(
                "Installation failed because of an invalid peer certificate. Are your systems certificates correctly installed? Do you have an Enterprise VPN enabled?"
            )
        elif "failed to fetch" in lowered_error:
            logger.error(
                "Installation failed because of a failed fetch. Is your network connection working?"
            )
        elif "no solution found when resolving dependencies" in lowered_error:
            logger.error(
                "Installation failed because the packages you requested are not supported by Python Workers. See above for details."
            )
        else:
            logger.error(
                "Installation of packages into the Python Worker failed. Possibly because these packages are not currently supported. See above for details."
            )
        raise click.exceptions.Exit(code=1)

    _log_installed_packages(get_venv_workers_path())


def _write_sync_token(token: Path) -> None:
    """Record the current workers-py version into the given sync token file."""
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(get_pywrangler_version())


def _read_sync_token_version(token: Path) -> str | None:
    """Read the workers-py version recorded in a sync token, if any."""
    if not token.is_file():
        return None
    try:
        return token.read_text().strip() or None
    except OSError:
        return None


def _is_out_of_date(token: Path, time: float) -> bool:
    if not token.exists():
        return True
    if time > token.stat().st_mtime:
        return True
    recorded_version = _read_sync_token_version(token)
    current_version = get_pywrangler_version()
    if recorded_version != current_version:
        logger.debug(
            f"workers-py version changed from {recorded_version!r} to {current_version!r}; "
            f"{token.parent} needs to be re-synced"
        )
        return True
    return False


def is_sync_needed() -> bool:
    """
    Checks if pyproject.toml or pylock.toml has been modified since the last
    sync, or if the workers-py version has changed since the last sync.

    Returns:
        bool: True if sync is needed, False otherwise
    """
    pyproject_toml_path = find_pyproject_toml()
    if not pyproject_toml_path.is_file():
        # If pyproject.toml doesn't exist, we need to abort anyway
        return True

    latest_mtime = pyproject_toml_path.stat().st_mtime

    lockfile = get_lockfile_path()
    if lockfile.is_file():
        latest_mtime = max(latest_mtime, lockfile.stat().st_mtime)

    return _is_out_of_date(get_vendor_token_path(), latest_mtime) or _is_out_of_date(
        get_venv_workers_token_path(), latest_mtime
    )


def sync(
    force: bool = False,
    directly_requested: bool = False,
    upgrade: bool = False,
    allow_build: bool | None = None,
) -> None:
    # Check if requirements.txt does not exist.
    check_requirements_txt()

    # Resolve the build override: explicit CLI flag wins, otherwise fall back to
    # `[tool.pywrangler] allow-build` in pyproject.toml so `dev`/`deploy` (which
    # call sync() without flags) honor it too.
    if allow_build is None:
        allow_build = bool(get_pywrangler_config().get("allow-build", False))

    # Check if sync is needed based on file timestamps
    sync_needed = force or is_sync_needed()
    if not sync_needed:
        logger.debug("Sync not needed - no changes detected")
        if directly_requested:
            logger.warning(
                "pyproject.toml hasn't changed since last sync, use --force to ignore timestamp check"
            )
        return

    logger.debug("Sync needed - proceeding with installation")

    # Check to make sure a wrangler config file exists.
    check_wrangler_config()

    # Create .venv-workers if it doesn't exist
    create_workers_venv()

    # Set up Pyodide virtual env
    create_pyodide_venv()

    # Resolve dependencies via uv pip compile targeting Pyodide, then install into vendor folder.
    plan = resolve_requirements(upgrade=upgrade, allow_build=allow_build)
    if not plan.requirements:
        logger.warning(
            "No dependencies found in [project.dependencies] section of pyproject.toml."
        )
    install_requirements(plan, allow_build=allow_build)
