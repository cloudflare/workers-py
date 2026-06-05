import logging
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .utils import (
    get_lockfile_path,
    get_project_root,
    get_pyodide_index,
    get_uv_pyodide_interp_name,
    read_pyproject_toml,
    run_command,
)

logger = logging.getLogger(__name__)

MANAGED_SDK_PACKAGE = "workers-runtime-sdk"


@dataclass
class InstallPlan:
    """Requirements resolved for installation (requirements.txt-style strings)."""

    requirements: list[str] = field(default_factory=list)
    lockfile: Path | None = None


def parse_requirements() -> list[str]:
    pyproject_data = read_pyproject_toml()

    # Extract dependencies from [project.dependencies]
    return pyproject_data.get("project", {}).get("dependencies", [])


def _compile_requirements(
    requirements: list[str],
    lockfile_path: Path,
    *,
    upgrade: bool = False,
) -> list[str]:
    """Run ``uv pip compile`` targeting Pyodide and return pinned requirement strings.

    Writes the compiled output to *lockfile_path*. When *lockfile_path* already
    exists, ``uv pip compile`` uses it as a constraint source so pinned versions
    are preserved across re-runs (no silent upgrades).
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".in", delete=False) as req_file:
        req_file.write("\n".join(requirements))
        req_file.flush()
        req_in_path = req_file.name

    try:
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
            "--no-build",
            "--no-header",
            "-o",
            str(lockfile_path),
        ]
        if upgrade:
            cmd.append("--upgrade")

        run_command(cmd, cwd=get_project_root(), capture_output=True)
    finally:
        Path(req_in_path).unlink(missing_ok=True)

    return _read_lockfile_requirements(lockfile_path)


def _read_lockfile_requirements(lockfile_path: Path) -> list[str]:
    """Read pinned ``name==version`` pairs from a ``pylock.toml`` file."""
    with open(lockfile_path, "rb") as f:
        data = tomllib.load(f)

    results = []
    for pkg in data.get("packages", []):
        name = pkg.get("name")
        version = pkg.get("version")
        if not name or not version:
            logger.warning("Skipping malformed lockfile entry: %s", pkg)
            continue
        results.append(f"{name}=={version}")
    return results


def resolve_requirements(*, upgrade: bool = False) -> InstallPlan:
    """Build an InstallPlan by compiling dependencies for the Pyodide target.

    Runs ``uv pip compile`` with the Pyodide interpreter and ``--no-build``
    to resolve versions that have Pyodide wheels.  The compiled output is
    written to ``pylock.toml``; on subsequent runs the existing file
    constrains versions so they don't drift.
    """
    lockfile = get_lockfile_path()

    deps = parse_requirements()
    deps.append(MANAGED_SDK_PACKAGE)

    requirements = _compile_requirements(deps, lockfile, upgrade=upgrade)

    logger.info("Resolved %d requirements from %s.", len(requirements), lockfile)
    for req in requirements:
        logger.debug("  - %s", req)
    return InstallPlan(requirements=requirements, lockfile=lockfile)
