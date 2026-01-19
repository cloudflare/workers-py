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


class TestSyncVenvToVendorVersions:
    @patch.object(pywrangler_sync, "_pip_install_to_venv")
    @patch.object(pywrangler_sync, "_get_vendor_package_versions")
    @patch.object(pywrangler_sync, "get_venv_workers_path")
    @patch.object(pywrangler_sync, "get_project_root")
    def test_syncs_packages(
        self, mock_root, mock_venv_path, mock_get_versions, mock_pip_install
    ):
        mock_root.return_value = Path("/fake/project")
        mock_venv_path.return_value = Path("/fake/project/.venv-workers")
        mock_get_versions.return_value = [
            "shapely==2.0.7",
            "numpy==1.26.4",
        ]

        pywrangler_sync._sync_venv_to_vendor_versions()

        mock_pip_install.assert_called_once()
        call_args = mock_pip_install.call_args
        packages = call_args[0][0]
        assert "shapely==2.0.7" in packages
        assert "numpy==1.26.4" in packages

    @patch.object(pywrangler_sync, "_pip_install_to_venv")
    @patch.object(pywrangler_sync, "_get_vendor_package_versions")
    @patch.object(pywrangler_sync, "get_venv_workers_path")
    @patch.object(pywrangler_sync, "get_project_root")
    def test_skips_when_no_packages(
        self, mock_root, mock_venv_path, mock_get_versions, mock_pip_install
    ):
        mock_root.return_value = Path("/fake/project")
        mock_venv_path.return_value = Path("/fake/project/.venv-workers")
        mock_get_versions.return_value = []

        pywrangler_sync._sync_venv_to_vendor_versions()

        mock_pip_install.assert_not_called()


class TestInstallRequirements:
    @patch.object(pywrangler_sync, "_sync_venv_to_vendor_versions")
    @patch.object(pywrangler_sync, "_install_requirements_to_vendor")
    @patch.object(pywrangler_sync, "_install_requirements_to_venv")
    def test_calls_all_three_functions_in_order(
        self, mock_venv, mock_vendor, mock_sync
    ):
        call_order = []
        mock_venv.side_effect = lambda r: call_order.append("venv")
        mock_vendor.side_effect = lambda r: call_order.append("vendor")
        mock_sync.side_effect = lambda: call_order.append("sync")

        pywrangler_sync.install_requirements(["click", "numpy"])

        assert call_order == ["venv", "vendor", "sync"]
        mock_venv.assert_called_once_with(["click", "numpy"])
        mock_vendor.assert_called_once_with(["click", "numpy"])
        mock_sync.assert_called_once()
