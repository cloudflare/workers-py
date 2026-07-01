import logging
import tomllib
from pathlib import Path

from .utils import (
    get_lockfile_path,
    get_project_root,
    get_pyodide_index,
    get_uv_pyodide_interp_name,
    read_pyproject_toml,
    run_command,
    temp_requirements_file,
)

logger = logging.getLogger(__name__)

MANAGED_SDK_PACKAGE = "workers-runtime-sdk"


class InstallPlan:
    # Lockfile keys that indicate a package is sourced locally
    _LOCAL_SOURCE_KEYS = ("directory", "sdist", "archive")

    def __init__(self, lockfile: Path) -> None:
        self.lockfile = lockfile
        self.requirements: list[tuple[str, str]] = []
        # Names of packages sourced from a local path. They need refreshing when
        # rebuilt.
        self.local_packages: list[str] = []

        with open(lockfile, "rb") as f:
            data = tomllib.load(f)

        for pkg in data.get("packages", []):
            name = pkg.get("name")
            if name and any(
                self._is_local_source(pkg, key) for key in self._LOCAL_SOURCE_KEYS
            ):
                self.local_packages.append(name)

            version = pkg.get("version")
            if not name or not version:
                logger.warning("Skipping malformed lockfile entry: %s", pkg)
                continue
            self.requirements.append((name, version))

    @staticmethod
    def _is_local_source(pkg: dict, key: str) -> bool:
        source = pkg.get(key)
        if not isinstance(source, dict):
            return False
        # A local reference has a `path``
        return "path" in source

    def to_requirement_strings(self) -> list[str]:
        return [f"{name}=={version}" for name, version in self.requirements]


def parse_requirements() -> list[str]:
    pyproject_data = read_pyproject_toml()

    # Extract dependencies from [project.dependencies]
    return pyproject_data.get("project", {}).get("dependencies", [])


def _compile_lockfile(
    requirements: list[str],
    lockfile_path: Path,
    *,
    upgrade: bool = False,
    allow_build: bool = False,
) -> None:
    """Run ``uv pip compile`` targeting Pyodide.

    Writes the compiled output to *lockfile_path*. When *lockfile_path* already
    exists, ``uv pip compile`` uses it as a constraint source so pinned versions
    are preserved across re-runs (no silent upgrades).

    By default ``--no-build`` is passed so only prebuilt wheels are used. This
    is because building a Pyodide platformed wheel will fail. Set *allow_build*
    to permit building source distributions / local directory sources. This is
    useful for testing against local checkouts of pure Python packages.
    """
    with temp_requirements_file(requirements) as req_in_path:
        cmd = [
            "uv",
            "pip",
            "compile",
            req_in_path,
            "--python",
            get_uv_pyodide_interp_name(),
            "--extra-index-url",
            get_pyodide_index(),
            "--index-strategy",
            "unsafe-best-match",
            "--no-header",
            "-o",
            str(lockfile_path),
        ]
        if not allow_build:
            cmd.append("--no-build")
        if upgrade:
            cmd.append("--upgrade")

        run_command(cmd, cwd=get_project_root(), capture_output=True)


def resolve_requirements(
    *, upgrade: bool = False, allow_build: bool = False
) -> InstallPlan:
    """Build an InstallPlan by compiling dependencies for the Pyodide target.

    Runs ``uv pip compile`` with the Pyodide interpreter and ``--no-build`` to
    resolve versions that have Pyodide wheels.  The compiled output is written
    to ``pylock.toml``; on subsequent runs the existing file constrains versions
    so they don't drift.

    When *allow_build* is True, ``--no-build`` is omitted so source
    distributions and local directory sources may be built. Building a binary
    extension in this way will fail in a confusing way.
    """
    lockfile = get_lockfile_path()

    deps = parse_requirements()
    deps.append(MANAGED_SDK_PACKAGE)

    _compile_lockfile(deps, lockfile, upgrade=upgrade, allow_build=allow_build)
    plan = InstallPlan(lockfile)

    logger.info("Resolved %d requirements from %s.", len(plan.requirements), lockfile)
    for name, version in plan.requirements:
        logger.debug("  - %s==%s", name, version)
    return plan
