from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import pywrangler.local_deps as local_deps_mod
from pywrangler.local_deps import (
    build_wheels,
    is_local_path_dep,
    parse_local_dep,
)

# ---------------------------------------------------------------------------
# is_local_path_dep
# ---------------------------------------------------------------------------


class TestIsLocalPathDep:
    def test_relative_path(self):
        assert is_local_path_dep("mylib @ ../../mylib") is True

    def test_dot_relative_path(self):
        assert is_local_path_dep("mylib @ ./mylib") is True

    def test_absolute_path(self):
        assert is_local_path_dep("mylib @ /opt/libs/mylib") is True

    def test_file_url(self):
        assert is_local_path_dep("mylib @ file:///opt/libs/mylib") is True

    def test_with_extras(self):
        assert is_local_path_dep("mylib[extra1] @ ../mylib") is True

    def test_with_markers(self):
        assert is_local_path_dep('mylib @ ../mylib ; python_version >= "3.12"') is True

    def test_http_url_is_not_local(self):
        assert is_local_path_dep("mylib @ https://example.com/mylib.tar.gz") is False

    def test_http_url_is_not_local_insecure(self):
        assert is_local_path_dep("mylib @ http://example.com/mylib.tar.gz") is False

    def test_registry_dep_is_not_local(self):
        assert is_local_path_dep("requests>=2.28") is False

    def test_plain_name_is_not_local(self):
        assert is_local_path_dep("click") is False


# ---------------------------------------------------------------------------
# parse_local_dep
# ---------------------------------------------------------------------------

FAKE_PROJECT_ROOT = Path("/fake/project")


@pytest.fixture(autouse=True)
def _patch_project_root():
    with patch.object(
        local_deps_mod, "get_project_root", return_value=FAKE_PROJECT_ROOT
    ):
        yield


class TestParseLocalDep:
    def test_relative_path(self):
        name, extras, path = parse_local_dep("mylib @ ../../mylib")
        assert name == "mylib"
        assert extras == ""
        assert path == (FAKE_PROJECT_ROOT / "../../mylib").resolve()

    def test_absolute_path(self):
        name, extras, path = parse_local_dep("mylib @ /opt/libs/mylib")
        assert name == "mylib"
        assert path == Path("/opt/libs/mylib").resolve()

    def test_file_url(self):
        name, extras, path = parse_local_dep("mylib @ file:///opt/libs/mylib")
        assert name == "mylib"
        assert path == Path("/opt/libs/mylib").resolve()

    def test_extras_preserved(self):
        name, extras, path = parse_local_dep("mylib[foo,bar] @ ../mylib")
        assert name == "mylib"
        assert extras == "[bar,foo]"

    def test_markers_stripped_from_path(self):
        name, extras, path = parse_local_dep(
            'mylib @ ../mylib ; python_version >= "3.12"'
        )
        assert name == "mylib"
        assert "python_version" not in str(path)

    def test_raises_for_non_url_dep(self):
        with pytest.raises(ValueError, match="Not a URL/path dependency"):
            parse_local_dep("requests>=2.28")


# ---------------------------------------------------------------------------
# build_wheels
# ---------------------------------------------------------------------------


class TestBuildWheels:
    @patch.object(local_deps_mod, "run_command")
    def test_builds_wheel_and_returns_path(self, mock_run, tmp_path):
        pkg_src = tmp_path / "mypkg"
        pkg_src.mkdir()

        output_dir = tmp_path / "wheels"
        output_dir.mkdir()

        def fake_uv_build(cmd, **_kwargs):
            wheel_name = "mypkg-0.1.0-py3-none-any.whl"
            (output_dir / "mypkg" / wheel_name).touch()
            return Mock(returncode=0)

        mock_run.side_effect = fake_uv_build

        with patch.object(local_deps_mod, "get_project_root", return_value=tmp_path):
            results = build_wheels([f"mypkg @ {pkg_src}"], output_dir)

        assert len(results) == 1
        assert results[0].endswith(".whl")
        mock_run.assert_called_once()

    @patch.object(local_deps_mod, "run_command")
    def test_preserves_extras(self, mock_run, tmp_path):
        pkg_src = tmp_path / "mypkg"
        pkg_src.mkdir()

        output_dir = tmp_path / "wheels"
        output_dir.mkdir()

        def fake_uv_build(cmd, **_kwargs):
            (output_dir / "mypkg" / "mypkg-1.0.0-py3-none-any.whl").touch()
            return Mock(returncode=0)

        mock_run.side_effect = fake_uv_build

        with patch.object(local_deps_mod, "get_project_root", return_value=tmp_path):
            results = build_wheels([f"mypkg[extra1] @ {pkg_src}"], output_dir)

        assert results[0].endswith(".whl[extra1]")

    def test_raises_if_path_missing(self, tmp_path):
        output_dir = tmp_path / "wheels"
        output_dir.mkdir()

        with patch.object(local_deps_mod, "get_project_root", return_value=tmp_path):
            with pytest.raises(RuntimeError, match="does not exist"):
                build_wheels(["mypkg @ ./nonexistent"], output_dir)

    @patch.object(local_deps_mod, "run_command")
    def test_raises_if_no_wheel_produced(self, mock_run, tmp_path):
        pkg_src = tmp_path / "mypkg"
        pkg_src.mkdir()

        output_dir = tmp_path / "wheels"
        output_dir.mkdir()

        mock_run.return_value = Mock(returncode=0)

        with patch.object(local_deps_mod, "get_project_root", return_value=tmp_path):
            with pytest.raises(RuntimeError, match="No wheel produced"):
                build_wheels([f"mypkg @ {pkg_src}"], output_dir)
