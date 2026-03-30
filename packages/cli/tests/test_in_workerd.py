import shutil
import subprocess
from pathlib import Path

import pytest

TEST_DIR = Path(__file__).parent
WORKERD_TESTS = TEST_DIR / "workerd-test"
WORKERS_PY = TEST_DIR.parent
WORKERS_RUNTIME_SDK = WORKERS_PY.parent / "runtime-sdk" / "src"


def discover_workerd_tests():
    """Find all subdirs under workerd-tests/ that contain a .wd-test file."""
    cases = []
    for subdir in sorted(WORKERD_TESTS.iterdir()):
        if not subdir.is_dir():
            continue
        wd_files = list(subdir.glob("*.wd-test"))
        if wd_files:
            cases.append(pytest.param(subdir, wd_files[0].name, id=subdir.name))
    return cases


def embed(dir: Path, root: Path, level: int = 0):
    modules = []
    module_path_root = dir
    for _ in range(level):
        module_path_root = module_path_root.parent

    for path in dir.glob("**/*"):
        if path.is_dir():
            continue

        module_path = path.absolute().relative_to(module_path_root)
        embed_path = path.absolute().relative_to(root)
        if path.suffix == ".py":
            modules.append(
                f'(name = "{module_path}", pythonModule = embed "{embed_path}")'
            )
        else:
            modules.append(f'(name = "{module_path}", data = embed "{embed_path}")')
    return modules


@pytest.mark.parametrize("test_dir, wd_test_file", discover_workerd_tests())
def test_in_workerd(tmp_path, test_dir, wd_test_file, pytestconfig):
    color = pytestconfig.get_terminal_writer().hasmarkup
    target = tmp_path / test_dir.name
    shutil.copytree(test_dir, target)
    subprocess.run(
        ["uv", "run", "--with", WORKERS_PY, "pywrangler", "sync"],
        cwd=target,
        check=True,
    )

    # Copy runtime-sdk to the python modules as well
    # FIXME: remove this and pass runtime-sdk as a dependency explicitly after
    #        https://github.com/cloudflare/workers-py/pull/81 is merged
    shutil.copytree(WORKERS_RUNTIME_SDK, target / "python_modules", dirs_exist_ok=True)

    modules = embed(target / "python_modules", target, level=1) + embed(
        target / "tests", target, level=1
    )

    python_modules = ",\n".join(modules) + ",\n"
    wd_config = target / wd_test_file
    wd_config.write_text(
        wd_config.read_text()
        .replace("%PYTHON_MODULES", python_modules)
        .replace("%COLOR", str(color).lower())
    )
    subprocess.run(
        ["npm", "i", "workerd"],
        cwd=target,
        check=True,
    )
    subprocess.run(
        ["node_modules/workerd/bin/workerd", "test", wd_test_file, "--experimental"],
        cwd=target,
        check=True,
    )
