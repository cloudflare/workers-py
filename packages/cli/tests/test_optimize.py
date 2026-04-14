import re
import shutil
import subprocess
from dataclasses import fields
from pathlib import Path
from textwrap import dedent

import pytest
from wheel_optimizer import OptimizerConfig

from pywrangler.optimize import (
    _ALL_OPTIMIZER_FIELDS,
    DEFAULT_ON_OPTIMIZERS,
    get_optimize_config,
    optimize_packages,
)

SAMPLE_PY = dedent('''\
    """Module docstring."""


    def hello():
        """Function docstring."""
        # This is a comment
        x = 1
        return x
''')

SAMPLE_PY_WITH_TYPES = dedent("""\
    def add(a: int, b: int) -> int:
        return a + b
""")


@pytest.fixture()
def vendor_dir(tmp_path: Path) -> Path:
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(SAMPLE_PY)
    (pkg / "typed.py").write_text(SAMPLE_PY_WITH_TYPES)
    (pkg / "__pycache__").mkdir()
    (pkg / "__pycache__" / "foo.cpython-312.pyc").write_bytes(b"fake")
    return tmp_path


def _mock_pyproject(monkeypatch, optimize_section=None):
    toml_data: dict = {"project": {"dependencies": []}}
    if optimize_section is not None:
        toml_data["tool"] = {"pywrangler": {"optimize": optimize_section}}
    monkeypatch.setattr("pywrangler.optimize.read_pyproject_toml", lambda: toml_data)


class TestGetOptimizeConfig:
    def test_defaults_when_no_config_section(self, monkeypatch):
        _mock_pyproject(monkeypatch)
        config = get_optimize_config()

        for field in _ALL_OPTIMIZER_FIELDS:
            expected = field in DEFAULT_ON_OPTIMIZERS
            assert getattr(config, field) is expected, (
                f"{field}: expected {expected}, got {getattr(config, field)}"
            )
        assert config.disable_all is False

    def test_user_can_disable_default_on_optimizer(self, monkeypatch):
        _mock_pyproject(monkeypatch, {"remove_docstrings": False})
        config = get_optimize_config()

        assert config.remove_docstrings is False
        assert config.remove_pycache is True
        assert config.remove_comments is True
        assert config.minify_whitespace is True

    def test_user_can_enable_opt_in_optimizer(self, monkeypatch):
        _mock_pyproject(monkeypatch, {"remove_type_annotations": True})
        config = get_optimize_config()

        assert config.remove_type_annotations is True
        for field in DEFAULT_ON_OPTIMIZERS:
            assert getattr(config, field) is True

    def test_disable_all_overrides_everything(self, monkeypatch):
        _mock_pyproject(
            monkeypatch,
            {"disable_all": True, "remove_docstrings": True},
        )
        config = get_optimize_config()
        assert config.disable_all is True

    def test_all_fields_accounted_for(self):
        dataclass_fields = {
            f.name for f in fields(OptimizerConfig) if f.name != "disable_all"
        }
        assert _ALL_OPTIMIZER_FIELDS == dataclass_fields


class TestOptimizeVendor:
    def test_default_removes_docstrings_and_comments(self, monkeypatch, vendor_dir):
        _mock_pyproject(monkeypatch)
        optimize_packages(vendor_dir)

        result = (vendor_dir / "mypkg" / "__init__.py").read_text()
        assert '"""Module docstring."""' not in result
        assert '"""Function docstring."""' not in result
        assert "# This is a comment" not in result

    def test_default_removes_pycache(self, monkeypatch, vendor_dir):
        _mock_pyproject(monkeypatch)
        pyc = vendor_dir / "mypkg" / "__pycache__" / "foo.cpython-312.pyc"
        assert pyc.exists()

        optimize_packages(vendor_dir)
        assert not pyc.exists()

    def test_default_minifies_whitespace(self, monkeypatch, vendor_dir):
        four_space = "    x = 1\n"
        src = (vendor_dir / "mypkg" / "__init__.py").read_text()
        assert four_space in src

        _mock_pyproject(monkeypatch)
        optimize_packages(vendor_dir)

        result = (vendor_dir / "mypkg" / "__init__.py").read_text()
        assert four_space not in result

    def test_default_does_not_remove_type_annotations(self, monkeypatch, vendor_dir):
        _mock_pyproject(monkeypatch)
        optimize_packages(vendor_dir)

        result = (vendor_dir / "mypkg" / "typed.py").read_text()
        assert "int" in result

    def test_opt_in_removes_type_annotations(self, monkeypatch, vendor_dir):
        _mock_pyproject(monkeypatch, {"remove_type_annotations": True})
        optimize_packages(vendor_dir)

        result = (vendor_dir / "mypkg" / "typed.py").read_text()
        assert ": int" not in result
        assert "-> int" not in result

    def test_disable_all_skips_everything(self, monkeypatch, vendor_dir):
        _mock_pyproject(monkeypatch, {"disable_all": True})
        optimize_packages(vendor_dir)

        result = (vendor_dir / "mypkg" / "__init__.py").read_text()
        assert '"""Module docstring."""' in result
        assert "# This is a comment" in result
        pyc = vendor_dir / "mypkg" / "__pycache__" / "foo.cpython-312.pyc"
        assert pyc.exists()

    def test_all_defaults_off_skips_everything(self, monkeypatch, vendor_dir):
        all_off = dict.fromkeys(_ALL_OPTIMIZER_FIELDS, False)
        _mock_pyproject(monkeypatch, all_off)
        optimize_packages(vendor_dir)

        result = (vendor_dir / "mypkg" / "__init__.py").read_text()
        assert '"""Module docstring."""' in result


@pytest.fixture()
def integration_dir():
    workspace = Path(__file__).parent / "test_workspace_optimize"
    shutil.rmtree(workspace, ignore_errors=True)
    (workspace / "src").mkdir(parents=True)
    try:
        yield workspace.absolute()
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _write_pyproject(
    test_dir: Path,
    dependencies: list[str],
    optimize_section: dict[str, bool] | None = None,
) -> None:
    deps_str = ", ".join(f'"{d}"' for d in dependencies)
    content = dedent(f"""\
        [build-system]
        requires = ["setuptools>=61.0"]
        build-backend = "setuptools.build_meta"

        [project]
        name = "test-project"
        version = "0.1.0"
        requires-python = ">=3.12"
        dependencies = [{deps_str}]
    """)
    if optimize_section is not None:
        content += "\n[tool.pywrangler.optimize]\n"
        for key, val in optimize_section.items():
            content += f"{key} = {str(val).lower()}\n"
    (test_dir / "pyproject.toml").write_text(content)


def _write_wrangler_jsonc(test_dir: Path) -> None:
    content = dedent("""\
        {
            "name": "test-worker",
            "main": "src/worker.py",
            "compatibility_date": "2026-03-20",
            "compatibility_flags": ["python_workers"]
        }
    """)
    (test_dir / "wrangler.jsonc").write_text(content)


def test_sync_applies_default_optimizations(integration_dir):
    _write_pyproject(integration_dir, ["six"])
    _write_wrangler_jsonc(integration_dir)

    result = subprocess.run(
        ["uv", "run", "pywrangler", "sync"],
        capture_output=True,
        text=True,
        cwd=integration_dir,
        check=False,
    )
    assert result.returncode == 0, f"sync failed:\n{result.stdout}\n{result.stderr}"

    vendor = integration_dir / "python_modules"
    assert vendor.exists()

    min_file_size = 100
    py_files = [
        f
        for f in vendor.rglob("*.py")
        if f.stat().st_size > min_file_size and f.name != "pyvenv.cfg"
    ]
    content = py_files[0].read_text()

    # minify_whitespace: original 4-space indentation becomes 1-space.
    # 1-space-indented lines are impossible in unminified source, so their
    # presence proves the optimizer ran.
    assert re.search(r"^ \S", content, re.MULTILINE), (
        f"Expected 1-space indentation from minify_whitespace in {py_files[0].name}"
    )

    # remove_docstrings: file should not start with a triple-quoted string.
    assert not content.lstrip().startswith(('"""', "'''")), (
        f"Module docstring still present in {py_files[0].name}"
    )
