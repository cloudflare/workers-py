from unittest.mock import patch

import pywrangler.sync as pywrangler_sync


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


class TestInstallRequirements:
    @patch.object(pywrangler_sync, "_install_requirements_to_vendor")
    @patch.object(pywrangler_sync, "_get_vendor_package_versions")
    @patch.object(pywrangler_sync, "_install_requirements_to_venv")
    def test_native_error_shown_before_pyodide_error(
        self, mock_venv, mock_get_vendor, mock_vendor, caplog
    ):
        mocked_pyodide_error = "Pyodide install failed: no solution found"
        mock_vendor.return_value = mocked_pyodide_error
        mock_get_vendor.return_value = []
        mocked_native_error = "Native install failed: package not found"
        mock_venv.return_value = mocked_native_error

        import click
        import pytest

        with pytest.raises(click.exceptions.Exit):
            pywrangler_sync.install_requirements(["nonexistent-package"])

        assert mock_vendor.call_count == 1
        assert mock_venv.call_count == 1
        assert mock_get_vendor.call_count == 0

        assert mock_vendor.call_args_list[0][0][0] == ["nonexistent-package"]
        assert mock_venv.call_args_list[0][0][0] == ["nonexistent-package"]

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
        self, mock_venv, mock_get_vendor, mock_vendor, caplog
    ):
        mocked_pyodide_error = "Pyodide install failed: no solution found"
        mock_vendor.return_value = mocked_pyodide_error
        mock_get_vendor.return_value = []
        mock_venv.return_value = None

        import click
        import pytest

        with pytest.raises(click.exceptions.Exit):
            pywrangler_sync.install_requirements(["some-package"])

        assert mock_vendor.call_count == 1
        assert mock_venv.call_count == 1
        # Pyodide installation failed, so _get_vendor_package_versions should not be called
        assert mock_get_vendor.call_count == 0

        assert mock_vendor.call_args_list[0][0][0] == ["some-package"]

        # native installation should be called with the original requirements
        assert mock_venv.call_args_list[0][0][0] == ["some-package"]

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
        self, mock_venv, mock_get_vendor, mock_vendor, caplog
    ):
        mocked_native_error = "Native install failed: package not found"
        mock_vendor.return_value = None
        mock_get_vendor.return_value = ["some-package==1.0.0"]
        mock_venv.return_value = mocked_native_error

        import click
        import pytest

        with pytest.raises(click.exceptions.Exit):
            pywrangler_sync.install_requirements(["some-package"])

        assert mock_vendor.call_count == 1
        assert mock_venv.call_count == 1
        assert mock_get_vendor.call_count == 1

        assert mock_vendor.call_args_list[0][0][0] == ["some-package"]
        assert mock_venv.call_args_list[0][0][0] == ["some-package==1.0.0"]

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
        self, mock_venv, mock_get_vendor, mock_vendor, caplog
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

            with pytest.raises(click.exceptions.Exit):
                pywrangler_sync.install_requirements(["some-package"])

            log_messages = [record.message for record in caplog.records]
            assert any(message in msg for msg in log_messages)
