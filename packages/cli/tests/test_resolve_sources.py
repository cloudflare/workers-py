import sys
import zipfile
from pathlib import Path

import pytest

import pywrangler.resolve as resolve_module


@pytest.fixture
def local_index(tmp_path: Path) -> str:
    index = tmp_path / "index"
    index.mkdir()
    return index.as_uri()


def write_worker_project(project_dir: Path, dependency: str, source: str) -> None:
    (project_dir / "pyproject.toml").write_text(
        f"""
[project]
name = "test-worker"
version = "0.0.0"
dependencies = ["{dependency}"]

[tool.uv.sources]
{source}
"""
    )


def compile_project(
    project_dir: Path,
    local_index: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    allow_build: bool = False,
) -> Path:
    monkeypatch.setattr(resolve_module, "get_project_root", lambda: project_dir)
    monkeypatch.setattr(
        resolve_module, "get_uv_pyodide_interp_name", lambda: sys.executable
    )
    monkeypatch.setattr(resolve_module, "get_pyodide_index", lambda: local_index)
    lockfile = project_dir / "pylock.toml"

    resolve_module._compile_lockfile([], lockfile, allow_build=allow_build)

    return lockfile


def install_lockfile(project_dir: Path, lockfile: Path) -> Path:
    target = project_dir / "installed"
    resolve_module.run_command(
        [
            "uv",
            "pip",
            "install",
            "--target",
            str(target),
            "--python",
            sys.executable,
            "-r",
            str(lockfile),
            "--preview-features",
            "pylock",
        ],
        cwd=project_dir,
        capture_output=True,
    )
    return target


def install_project(project_dir: Path, constraints: list[str]) -> Path:
    target = project_dir / "native-installed"
    constraints_file = project_dir / "constraints.txt"
    constraints_file.write_text("\n".join(constraints))
    resolve_module.run_command(
        [
            "uv",
            "pip",
            "install",
            "--target",
            str(target),
            "--python",
            sys.executable,
            "-r",
            str(project_dir / "pyproject.toml"),
            "-c",
            str(constraints_file),
        ],
        cwd=project_dir,
        capture_output=True,
    )
    return target


def plan_constraints(plan: resolve_module.InstallPlan) -> list[str]:
    return [
        f"{name}=={version}"
        for name, version in plan.requirements
        if version is not None
    ]


@pytest.fixture
def dummy_wheel(tmp_path: Path) -> Path:
    wheel = tmp_path / "dummy_wheel-1.2.3-py3-none-any.whl"
    dist_info = "dummy_wheel-1.2.3.dist-info"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("dummy_wheel/__init__.py", "VALUE = 123\n")
        archive.writestr(
            f"{dist_info}/METADATA",
            "Metadata-Version: 2.1\nName: dummy-wheel\nVersion: 1.2.3\n",
        )
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(f"{dist_info}/RECORD", "")
    return wheel


def test_resolves_path_source_wheel(
    tmp_path: Path,
    dummy_wheel: Path,
    local_index: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_worker_project(
        tmp_path,
        "dummy-wheel",
        f'dummy-wheel = {{ path = "{dummy_wheel.name}" }}',
    )

    lockfile = compile_project(tmp_path, local_index, monkeypatch)
    target = install_lockfile(tmp_path, lockfile)

    assert (target / "dummy_wheel" / "__init__.py").read_text() == "VALUE = 123\n"

    plan = resolve_module.InstallPlan(lockfile)
    native_target = install_project(tmp_path, plan_constraints(plan))
    assert (native_target / "dummy_wheel" / "__init__.py").read_text() == (
        "VALUE = 123\n"
    )


@pytest.fixture
def dummy_source(tmp_path: Path) -> Path:
    source = tmp_path / "dummy-source"
    package = source / "dummy_source"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 456\n")
    (source / "pyproject.toml").write_text(
        """
[build-system]
requires = []
build-backend = "backend"
backend-path = ["."]

[project]
name = "dummy-source"
version = "4.5.6"
"""
    )
    (source / "backend.py").write_text(
        """
from pathlib import Path
from zipfile import ZipFile


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    filename = "dummy_source-4.5.6-py3-none-any.whl"
    dist_info = "dummy_source-4.5.6.dist-info"
    with ZipFile(Path(wheel_directory) / filename, "w") as archive:
        archive.write("dummy_source/__init__.py", "dummy_source/__init__.py")
        archive.writestr(
            f"{dist_info}/METADATA",
            "Metadata-Version: 2.1\\nName: dummy-source\\nVersion: 4.5.6\\n",
        )
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n",
        )
        archive.writestr(f"{dist_info}/RECORD", "")
    return filename
"""
    )
    return source


def test_resolves_local_directory_source(
    tmp_path: Path,
    dummy_source: Path,
    local_index: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_worker_project(
        tmp_path,
        "dummy-source",
        f'dummy-source = {{ path = "{dummy_source.name}" }}',
    )

    lockfile = compile_project(tmp_path, local_index, monkeypatch, allow_build=True)
    target = install_lockfile(tmp_path, lockfile)

    assert (target / "dummy_source" / "__init__.py").read_text() == "VALUE = 456\n"

    plan = resolve_module.InstallPlan(lockfile)
    assert plan.local_packages == ["dummy-source"]
    native_target = install_project(tmp_path, plan_constraints(plan))
    assert (native_target / "dummy_source" / "__init__.py").read_text() == (
        "VALUE = 456\n"
    )


def test_installs_pure_python_package_from_github(
    tmp_path: Path,
    local_index: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "621e4974ca25ce531773def586ba3ed8e736b3fc"
    write_worker_project(
        tmp_path,
        "sampleproject",
        (
            'sampleproject = { git = "https://github.com/pypa/sampleproject.git", '
            f'rev = "{revision}" }}'
        ),
    )

    lockfile = compile_project(tmp_path, local_index, monkeypatch, allow_build=True)
    target = install_lockfile(tmp_path, lockfile)

    assert (target / "sample" / "__init__.py").is_file()
    assert revision in lockfile.read_text()

    plan = resolve_module.InstallPlan(lockfile)
    assert plan_constraints(plan) == [
        "peppercorn==0.6",
        "sampleproject==4.0.0",
    ]
    native_target = install_project(tmp_path, plan_constraints(plan))
    assert (native_target / "sample" / "__init__.py").is_file()
