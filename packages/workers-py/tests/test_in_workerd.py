import shutil
import subprocess
from pathlib import Path

TEST_DIR = Path(__file__).parent
WORKERD_TEST = TEST_DIR / "workerd-test"
WORKERS_PY = TEST_DIR.parent


def test_in_workerd(tmp_path):
    target = tmp_path / "workerd-test"
    shutil.copytree(WORKERD_TEST, target)
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
    wd_config = target / "sdk.wd-test"
    wd_config.write_text(
        wd_config.read_text().replace("%PYTHON_MODULES", python_modules)
    )
    subprocess.run(
        ["npm", "i", "workerd"],
        cwd=target,
        check=True,
    )
    subprocess.run(
        ["node_modules/workerd/bin/workerd", "test", "sdk.wd-test", "--experimental"],
        cwd=target,
        check=True,
    )
