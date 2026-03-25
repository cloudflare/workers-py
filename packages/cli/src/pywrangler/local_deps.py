import logging
from pathlib import Path

from packaging.requirements import Requirement

from .utils import get_project_root, run_command

logger = logging.getLogger(__name__)


def is_local_path_dep(dep: str) -> bool:
    req = Requirement(dep)
    if req.url is None:
        return False
    url = req.url.strip()
    return not url.startswith(("http://", "https://"))


def parse_local_dep(dep: str) -> tuple[str, str, Path]:
    """Returns (name, extras_str, resolved_path).

    ``extras_str`` includes the brackets, e.g. ``"[extra1,extra2]"`` or ``""``.
    """
    req = Requirement(dep)
    if req.url is None:
        raise ValueError(f"Not a URL/path dependency: {dep}")

    url = req.url.strip()
    if url.startswith("file://"):
        url = url[len("file://") :]

    resolved = (get_project_root() / url).resolve()
    extras_str = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
    return req.name, extras_str, resolved


def build_wheels(local_deps: list[str], output_dir: Path) -> list[str]:
    results: list[str] = []
    for dep in local_deps:
        name, extras, path = parse_local_dep(dep)

        logger.info(f"Building wheel for local package '{name}' from {path}")
        if not path.exists():
            raise RuntimeError(f"Local package path does not exist: {path}")

        dep_out = output_dir / name
        dep_out.mkdir(parents=True, exist_ok=True)
        run_command(["uv", "build", "--wheel", str(path), "--out-dir", str(dep_out)])

        wheels = list(dep_out.glob("*.whl"))
        if not wheels:
            raise RuntimeError(f"No wheel produced for '{name}' from {path}")

        results.append(f"{wheels[0]}{extras}")
    return results
