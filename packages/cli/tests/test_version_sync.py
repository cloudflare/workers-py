from pathlib import Path
from unittest.mock import patch

import pytest

import pywrangler.resolve as pywrangler_resolve
import pywrangler.sync as pywrangler_sync
import pywrangler.utils as pywrangler_utils
from pywrangler.resolve import InstallPlan


def _make_plan(tmp_path: Path, packages: list[tuple[str, str]]) -> InstallPlan:
    lockfile = tmp_path / "pylock.toml"
    lines = ['lock-version = "1.0"']
    for name, version in packages:
        lines.append(f'[[packages]]\nname = "{name}"\nversion = "{version}"')
    lockfile.write_text("\n".join(lines) + "\n")
    return InstallPlan(lockfile)


def test_parse_pip_freeze():
    result = pywrangler_sync._parse_pip_freeze(
        "shapely==2.0.7\nnumpy==1.26.4\nclick==8.1.7\n"
    )

    assert result == ["shapely==2.0.7", "numpy==1.26.4", "click==8.1.7"]

    result = pywrangler_sync._parse_pip_freeze(
        "# Python 3.12.7\nshapely==2.0.7\n\n\nnumpy==1.26.4\n# Comment\n"
    )

    assert result == ["shapely==2.0.7", "numpy==1.26.4"]

    result = pywrangler_sync._parse_pip_freeze(
        "shapely==2.0.7\nsome-package\nnumpy==1.26.4\n"
    )

    assert result == ["shapely==2.0.7", "numpy==1.26.4"]


def test_get_vendor_package_versions_disables_color():
    """The freeze output is parsed, so uv must not colorize it even under
    color-forcing environments (e.g. FORCE_COLOR=1)."""
    with (
        patch.object(pywrangler_sync, "run_command") as mock_run,
        patch.object(pywrangler_sync, "get_vendor_modules_path"),
        patch.object(
            pywrangler_sync,
            "get_pyodide_venv_path",
            return_value=Path("pyodide-venv"),
        ),
    ):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "shapely==2.0.7\n"

        result = pywrangler_sync._get_vendor_package_versions()

    assert result == ["shapely==2.0.7"]
    command = mock_run.call_args[0][0]
    assert command[:5] == [
        "uv",
        "pip",
        "freeze",
        "--color",
        "never",
    ]
    env = mock_run.call_args[1].get("env", {})
    assert env.get("VIRTUAL_ENV") == str(Path("pyodide-venv"))


class TestInstallRequirements:
    @patch.object(pywrangler_sync, "_install_requirements_to_vendor")
    @patch.object(pywrangler_sync, "_get_vendor_package_versions")
    @patch.object(pywrangler_sync, "_install_requirements_to_venv")
    def test_native_error_shown_before_pyodide_error(
        self, mock_venv, mock_get_vendor, mock_vendor, caplog, tmp_path
    ):
        mocked_pyodide_error = "Pyodide install failed: no solution found"
        mock_vendor.return_value = mocked_pyodide_error
        mock_get_vendor.return_value = []
        mocked_native_error = "Native install failed: package not found"
        mock_venv.return_value = mocked_native_error

        import click
        import pytest

        plan = _make_plan(
            tmp_path,
            [
                ("nonexistent-package", "1.0.0"),
                ("workers-runtime-sdk", "1.0.0"),
            ],
        )
        with pytest.raises(click.exceptions.Exit):
            pywrangler_sync.install_requirements(plan)

        assert mock_vendor.call_count == 1
        assert mock_venv.call_count == 1
        assert mock_get_vendor.call_count == 0

        passed_plan = mock_vendor.call_args_list[0][0][0]
        assert passed_plan.requirements == [
            ("nonexistent-package", "1.0.0"),
            ("workers-runtime-sdk", "1.0.0"),
        ]
        assert mock_venv.call_args_list[0][0][0] == []

        log_messages = [record.message for record in caplog.records]
        native_idx = next(
            i for i, msg in enumerate(log_messages) if mocked_native_error in msg
        )
        pyodide_idx = next(
            (i for i, msg in enumerate(log_messages) if mocked_pyodide_error in msg),
            None,
        )
        assert pyodide_idx is None, (
            "Pyodide error should not be shown when native error occurs"
        )
        assert native_idx is not None

    @patch.object(pywrangler_sync, "_install_requirements_to_vendor")
    @patch.object(pywrangler_sync, "_get_vendor_package_versions")
    @patch.object(pywrangler_sync, "_install_requirements_to_venv")
    def test_only_pyodide_error_shown_when_native_succeeds(
        self, mock_venv, mock_get_vendor, mock_vendor, caplog, tmp_path
    ):
        mocked_pyodide_error = "Pyodide install failed: no solution found"
        mock_vendor.return_value = mocked_pyodide_error
        mock_get_vendor.return_value = []
        mock_venv.return_value = None

        import click
        import pytest

        plan = _make_plan(
            tmp_path,
            [
                ("some-package", "1.0.0"),
                ("workers-runtime-sdk", "1.0.0"),
            ],
        )
        with pytest.raises(click.exceptions.Exit):
            pywrangler_sync.install_requirements(plan)

        assert mock_vendor.call_count == 1
        assert mock_venv.call_count == 1
        # Pyodide installation failed, so _get_vendor_package_versions should not be called
        assert mock_get_vendor.call_count == 0

        passed_plan = mock_vendor.call_args_list[0][0][0]
        assert passed_plan.requirements == [
            ("some-package", "1.0.0"),
            ("workers-runtime-sdk", "1.0.0"),
        ]

        # Without a Pyodide resolution, native installation is unconstrained.
        assert mock_venv.call_args_list[0][0][0] == []

        log_messages = [record.message for record in caplog.records]
        assert any(mocked_pyodide_error in msg for msg in log_messages)
        assert any(
            "Installation of packages into the Python Worker failed. Possibly because these packages are not currently supported. See above for details."
            in msg
            for msg in log_messages
        )

    @patch.object(pywrangler_sync, "_install_requirements_to_vendor")
    @patch.object(pywrangler_sync, "_get_vendor_package_versions")
    @patch.object(pywrangler_sync, "_install_requirements_to_venv")
    def test_pyodide_install_succeeds_but_native_installation_fail(
        self, mock_venv, mock_get_vendor, mock_vendor, caplog, tmp_path
    ):
        mocked_native_error = "Native install failed: package not found"
        mock_vendor.return_value = None
        mock_get_vendor.return_value = [
            "some-package==1.0.0",
            "workers-runtime-sdk==1.0.0",
        ]
        mock_venv.return_value = mocked_native_error

        import click
        import pytest

        plan = _make_plan(
            tmp_path,
            [
                ("some-package", "1.0.0"),
                ("workers-runtime-sdk", "1.0.0"),
            ],
        )
        with pytest.raises(click.exceptions.Exit):
            pywrangler_sync.install_requirements(plan)

        assert mock_vendor.call_count == 1
        assert mock_venv.call_count == 1
        assert mock_get_vendor.call_count == 1

        passed_plan = mock_vendor.call_args_list[0][0][0]
        assert passed_plan.requirements == [
            ("some-package", "1.0.0"),
            ("workers-runtime-sdk", "1.0.0"),
        ]
        assert mock_venv.call_args_list[0][0][0] == [
            "some-package==1.0.0",
            "workers-runtime-sdk==1.0.0",
        ]

        log_messages = [record.message for record in caplog.records]
        assert any(mocked_native_error in msg for msg in log_messages)
        assert any(
            "Failed to install the requirements defined in your pyproject.toml file. See above for details."
            in msg
            for msg in log_messages
        )

    @patch.object(pywrangler_sync, "_install_requirements_to_vendor")
    @patch.object(pywrangler_sync, "_get_vendor_package_versions")
    @patch.object(pywrangler_sync, "_install_requirements_to_venv")
    def test_known_pyodide_errors(
        self, mock_venv, mock_get_vendor, mock_vendor, caplog, tmp_path
    ):
        common_errors = {
            "invalid peer certificate": "Are your systems certificates correctly installed? Do you have an Enterprise VPN enabled?",
            "failed to fetch": "Is your network connection working?",
            "no solution found when resolving dependencies": "the packages you requested are not supported by Python Workers. See above for details.",
        }

        for error, message in common_errors.items():
            mock_vendor.return_value = error
            mock_get_vendor.return_value = []
            mock_venv.return_value = None

            import click
            import pytest

            plan = _make_plan(
                tmp_path,
                [
                    ("some-package", "1.0.0"),
                    ("workers-runtime-sdk", "1.0.0"),
                ],
            )
            with pytest.raises(click.exceptions.Exit):
                pywrangler_sync.install_requirements(plan)

            log_messages = [record.message for record in caplog.records]
            assert any(message in msg for msg in log_messages)


class TestSyncTokenVersion:
    """Tests for workers-py version tracking inside sync token files."""

    @pytest.fixture
    def project_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[project]\nname='x'\nversion='0.0.0'\n")
        monkeypatch.chdir(tmp_path)
        pywrangler_utils.find_pyproject_toml.cache_clear()
        return tmp_path

    def test_write_sync_token_records_current_version(
        self, project_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(pywrangler_sync, "get_pywrangler_version", lambda: "1.2.3")
        token = project_root / ".venv-workers" / ".synced"

        pywrangler_sync._write_sync_token(token)

        assert token.is_file()
        assert token.read_text().strip() == "1.2.3"

    def test_sync_not_needed_when_version_matches(
        self, project_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(pywrangler_sync, "get_pywrangler_version", lambda: "1.2.3")
        pywrangler_sync._write_sync_token(pywrangler_sync.get_vendor_token_path())
        pywrangler_sync._write_sync_token(pywrangler_sync.get_venv_workers_token_path())

        assert pywrangler_sync.is_sync_needed() is False

    def test_sync_needed_when_version_changes(
        self, project_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(pywrangler_sync, "get_pywrangler_version", lambda: "1.2.3")
        pywrangler_sync._write_sync_token(pywrangler_sync.get_vendor_token_path())
        pywrangler_sync._write_sync_token(pywrangler_sync.get_venv_workers_token_path())

        # Simulate upgrading workers-py without touching pyproject.toml.
        monkeypatch.setattr(pywrangler_sync, "get_pywrangler_version", lambda: "1.2.4")

        assert pywrangler_sync.is_sync_needed() is True

    def test_sync_needed_when_only_vendor_version_changes(
        self, project_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(pywrangler_sync, "get_pywrangler_version", lambda: "1.2.3")
        pywrangler_sync._write_sync_token(pywrangler_sync.get_venv_workers_token_path())
        # vendor token written with an older version
        monkeypatch.setattr(pywrangler_sync, "get_pywrangler_version", lambda: "1.0.0")
        pywrangler_sync._write_sync_token(pywrangler_sync.get_vendor_token_path())

        # Current version matches venv token but not vendor token.
        monkeypatch.setattr(pywrangler_sync, "get_pywrangler_version", lambda: "1.2.3")

        assert pywrangler_sync.is_sync_needed() is True

    def test_sync_needed_when_token_missing_version(
        self, project_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(pywrangler_sync, "get_pywrangler_version", lambda: "1.2.3")
        # Write empty tokens to simulate pre-existing `.synced` files from older CLI versions.
        vendor_token = pywrangler_sync.get_vendor_token_path()
        venv_token = pywrangler_sync.get_venv_workers_token_path()
        vendor_token.parent.mkdir(parents=True, exist_ok=True)
        venv_token.parent.mkdir(parents=True, exist_ok=True)
        vendor_token.write_text("")
        venv_token.write_text("")

        assert pywrangler_sync.is_sync_needed() is True


class TestInstallPlan:
    def test_parses_packages_from_pylock(self, tmp_path):
        lockfile = tmp_path / "pylock.toml"
        lockfile.write_text(
            'lock-version = "1.0"\n'
            '[[packages]]\nname = "click"\nversion = "8.1.7"\n'
            '[[packages]]\nname = "numpy"\nversion = "2.0.2"\n'
        )
        plan = InstallPlan(lockfile)
        assert plan.requirements == [("click", "8.1.7"), ("numpy", "2.0.2")]
        assert plan.lockfile == lockfile

    def test_empty_packages(self, tmp_path):
        lockfile = tmp_path / "pylock.toml"
        lockfile.write_text('lock-version = "1.0"\n')
        plan = InstallPlan(lockfile)
        assert plan.requirements == []


class TestResolveRequirements:
    @patch.object(pywrangler_resolve, "_compile_lockfile")
    @patch.object(pywrangler_resolve, "get_lockfile_path")
    def test_compiles_from_project(self, mock_lockpath, mock_compile, tmp_path):
        lockfile = tmp_path / "pylock.toml"
        mock_lockpath.return_value = lockfile

        def write_lockfile(reqs, path, **kwargs):
            path.write_text(
                'lock-version = "1.0"\n'
                '[[packages]]\nname = "click"\nversion = "8.1.7"\n'
                '[[packages]]\nname = "workers-runtime-sdk"\nversion = "1.1.5"\n'
            )

        mock_compile.side_effect = write_lockfile

        plan = pywrangler_resolve.resolve_requirements()
        assert ("click", "8.1.7") in plan.requirements
        assert ("workers-runtime-sdk", "1.1.5") in plan.requirements
        mock_compile.assert_called_once_with(
            [pywrangler_resolve.MANAGED_SDK_PACKAGE],
            lockfile,
            upgrade=False,
            allow_build=False,
        )


class TestSyncNeededWithLockfile:
    @pytest.fixture
    def project_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[project]\nname='x'\nversion='0.0.0'\n")
        monkeypatch.chdir(tmp_path)
        pywrangler_utils.find_pyproject_toml.cache_clear()
        monkeypatch.setattr(pywrangler_sync, "get_pywrangler_version", lambda: "1.0.0")
        return tmp_path

    def test_sync_needed_when_lockfile_newer_than_token(
        self, project_root: Path
    ) -> None:
        pywrangler_sync._write_sync_token(pywrangler_sync.get_vendor_token_path())
        pywrangler_sync._write_sync_token(pywrangler_sync.get_venv_workers_token_path())

        assert pywrangler_sync.is_sync_needed() is False

        lockfile = project_root / "pylock.toml"
        lockfile.write_text("click==8.1.7\n")
        import os
        import time

        future = time.time() + 10
        os.utime(lockfile, (future, future))

        assert pywrangler_sync.is_sync_needed() is True


class TestEnsureVenvVersion:
    def test_returns_false_when_dir_missing(self, tmp_path):
        venv = tmp_path / "nonexistent"
        assert pywrangler_sync._ensure_venv_version(venv, "3.13") is False

    def test_returns_true_when_version_matches(self, tmp_path):
        venv = tmp_path / "venv"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("home = /some/path\nversion_info = 3.13.2\n")
        assert pywrangler_sync._ensure_venv_version(venv, "3.13") is True
        assert venv.is_dir()

    def test_removes_and_returns_false_on_mismatch(self, tmp_path):
        venv = tmp_path / "venv"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("home = /some/path\nversion_info = 3.12.7\n")
        assert pywrangler_sync._ensure_venv_version(venv, "3.13") is False
        assert not venv.exists()

    def test_removes_when_pyvenv_cfg_missing(self, tmp_path):
        venv = tmp_path / "venv"
        venv.mkdir()
        assert pywrangler_sync._ensure_venv_version(venv, "3.13") is False
        assert not venv.exists()

    def test_removes_when_version_info_line_missing(self, tmp_path):
        venv = tmp_path / "venv"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("home = /some/path\n")
        assert pywrangler_sync._ensure_venv_version(venv, "3.13") is False
        assert not venv.exists()


class TestCreatePyodideVenv:
    @patch.object(pywrangler_sync, "run_command")
    @patch.object(pywrangler_sync, "check_uv_version")
    @patch.object(
        pywrangler_sync,
        "get_uv_pyodide_interp_name",
        return_value="cpython-3.14.2-emscripten-wasm32-musl",
    )
    @patch.object(pywrangler_sync, "get_python_version", return_value="3.14")
    def test_recreates_on_version_mismatch(
        self, mock_version, mock_interp, mock_check, mock_run, tmp_path
    ):
        venv = tmp_path / ".venv-workers" / "pyodide-venv"
        venv.mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text("home = /some/path\nversion_info = 3.13.2\n")
        (venv / "lib").mkdir()

        with patch.object(pywrangler_sync, "get_pyodide_venv_path", return_value=venv):
            pywrangler_sync.create_pyodide_venv()

        assert not (venv / "lib").exists()
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "uv",
            "venv",
            str(venv),
            "--python",
            "cpython-3.14.2-emscripten-wasm32-musl",
        ]

    @patch.object(pywrangler_sync, "run_command")
    @patch.object(pywrangler_sync, "get_python_version", return_value="3.13")
    def test_skips_when_version_matches(self, mock_version, mock_run, tmp_path):
        venv = tmp_path / ".venv-workers" / "pyodide-venv"
        venv.mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text("home = /some/path\nversion_info = 3.13.2\n")

        with patch.object(pywrangler_sync, "get_pyodide_venv_path", return_value=venv):
            pywrangler_sync.create_pyodide_venv()

        mock_run.assert_not_called()
