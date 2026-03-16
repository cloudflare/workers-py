import shutil
import subprocess
from pathlib import Path

import pytest

TEST_DIR = Path(__file__).parent
WORKERD_TESTS = TEST_DIR / "workerd-test"
WORKERS_PY = TEST_DIR.parent


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
    modules = []
    PYTHON_MODULES = target / "python_modules"
    for path in PYTHON_MODULES.glob("**/*"):
        if path.is_dir():
            continue
        module_path = path.absolute().relative_to(PYTHON_MODULES)
        embed_path = path.absolute().relative_to(PYTHON_MODULES.parent)
        if path.suffix == ".py":
            modules.append(
                f'(name = "{module_path}", pythonModule = embed "{embed_path}")'
            )
        else:
            modules.append(f'(name = "{module_path}", data = embed "{embed_path}")')
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
