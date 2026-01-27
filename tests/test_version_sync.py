from pathlib import Path
from unittest.mock import Mock, patch

import pywrangler.sync as pywrangler_sync


class TestGetVendorPackageVersions:
    @patch.object(pywrangler_sync, "run_command")
    @patch.object(pywrangler_sync, "get_pyodide_venv_path")
    @patch.object(pywrangler_sync, "get_vendor_modules_path")
    def test_returns_parsed_packages(
        self, mock_vendor_path, mock_pyodide_path, mock_run_command
    ):
        mock_vendor_path.return_value = Path("/fake/python_modules")
        mock_pyodide_path.return_value = Path("/fake/pyodide-venv")
        mock_run_command.return_value = Mock(
            returncode=0,
            stdout="shapely==2.0.7\nnumpy==1.26.4\nclick==8.1.7\n",
        )

        result = pywrangler_sync._get_vendor_package_versions()

        assert result == ["shapely==2.0.7", "numpy==1.26.4", "click==8.1.7"]

    @patch.object(pywrangler_sync, "run_command")
    @patch.object(pywrangler_sync, "get_pyodide_venv_path")
    @patch.object(pywrangler_sync, "get_vendor_modules_path")
    def test_returns_empty_list_on_failure(
        self, mock_vendor_path, mock_pyodide_path, mock_run_command
    ):
        mock_vendor_path.return_value = Path("/fake/python_modules")
        mock_pyodide_path.return_value = Path("/fake/pyodide-venv")
        mock_run_command.return_value = Mock(returncode=1, stdout="")

        result = pywrangler_sync._get_vendor_package_versions()

        assert result == []

    @patch.object(pywrangler_sync, "run_command")
    @patch.object(pywrangler_sync, "get_pyodide_venv_path")
    @patch.object(pywrangler_sync, "get_vendor_modules_path")
    def test_filters_empty_lines_and_comments(
        self, mock_vendor_path, mock_pyodide_path, mock_run_command
    ):
        mock_vendor_path.return_value = Path("/fake/python_modules")
        mock_pyodide_path.return_value = Path("/fake/pyodide-venv")
        mock_run_command.return_value = Mock(
            returncode=0,
            stdout="# Python 3.12.7\nshapely==2.0.7\n\n\nnumpy==1.26.4\n# Comment\n",
        )

        result = pywrangler_sync._get_vendor_package_versions()

        assert result == ["shapely==2.0.7", "numpy==1.26.4"]

    @patch.object(pywrangler_sync, "run_command")
    @patch.object(pywrangler_sync, "get_pyodide_venv_path")
    @patch.object(pywrangler_sync, "get_vendor_modules_path")
    def test_filters_lines_without_version_specifier(
        self, mock_vendor_path, mock_pyodide_path, mock_run_command
    ):
        mock_vendor_path.return_value = Path("/fake/python_modules")
        mock_pyodide_path.return_value = Path("/fake/pyodide-venv")
        mock_run_command.return_value = Mock(
            returncode=0,
            stdout="shapely==2.0.7\nsome-package\nnumpy==1.26.4\n",
        )

        result = pywrangler_sync._get_vendor_package_versions()

        assert result == ["shapely==2.0.7", "numpy==1.26.4"]


class TestInstallRequirements:
    @patch.object(pywrangler_sync, "_install_requirements_to_vendor")
    @patch.object(pywrangler_sync, "_get_vendor_package_versions")
    @patch.object(pywrangler_sync, "_install_requirements_to_venv")
    def test_calls_vendor_then_venv(self, mock_venv, mock_get_vendor, mock_vendor):
        call_order = []
        mock_vendor.side_effect = lambda r: call_order.append("vendor")
        mock_get_vendor.side_effect = lambda: ["shapely==2.0.7", "numpy==1.26.4"]
        mock_venv.side_effect = lambda r: call_order.append("venv")

        pywrangler_sync.install_requirements(["click", "numpy"])

        assert call_order == ["vendor", "venv"]
        mock_vendor.assert_called_once_with(["click", "numpy"])
        mock_venv.assert_called_once_with(["shapely==2.0.7", "numpy==1.26.4"])

    @patch.object(pywrangler_sync, "_install_requirements_to_vendor")
    @patch.object(pywrangler_sync, "_get_vendor_package_versions")
    @patch.object(pywrangler_sync, "_install_requirements_to_venv")
    def test_native_error_shown_before_pyodide_error(
        self, mock_venv, mock_get_vendor, mock_vendor, caplog
    ):
        mock_vendor.return_value = "Pyodide install failed: no solution found"
        mock_get_vendor.return_value = []
        mock_venv.return_value = "Native install failed: package not found"

        import click
        import pytest

        with pytest.raises(click.exceptions.Exit):
            pywrangler_sync.install_requirements(["nonexistent-package"])

        log_messages = [record.message for record in caplog.records]
        native_idx = next(
            i for i, msg in enumerate(log_messages) if "Native install failed" in msg
        )
        pyodide_idx = next(
            (
                i
                for i, msg in enumerate(log_messages)
                if "Pyodide install failed" in msg
            ),
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
        self, mock_venv, mock_get_vendor, mock_vendor, caplog
    ):
        mock_vendor.return_value = "Pyodide install failed: no solution found"
        mock_get_vendor.return_value = []
        mock_venv.return_value = None

        import click
        import pytest

        with pytest.raises(click.exceptions.Exit):
            pywrangler_sync.install_requirements(["some-package"])

        log_messages = [record.message for record in caplog.records]
        assert any("Pyodide install failed" in msg for msg in log_messages)
        assert any("Python Worker failed" in msg for msg in log_messages)
