"""Tests for sync module Python version detection."""

import click
import pytest

# Import the functions we want to test
import pywrangler.utils as util_module


@pytest.fixture
def test_dir(tmp_path, monkeypatch):
    test_dir = tmp_path
    monkeypatch.setattr(
        util_module, "find_pyproject_toml", lambda: test_dir / "pyproject.toml"
    )
    yield test_dir


def get_python_version():
    util_module.get_python_version.cache_clear()
    version = util_module.get_python_version()
    return version


def test_wrangler_toml_with_compat_flag(test_dir):
    """Test Python 3.13 detection with python_workers_20250116 compat flag."""
    wrangler_toml = test_dir / "wrangler.toml"
    wrangler_toml.write_text("""
name = "test-worker"
compatibility_flags = ["python_workers", "python_workers_20250116"]
compatibility_date = "2024-01-01"
""")

    version = get_python_version()
    assert version == "3.13"


def test_wrangler_toml_with_compat_date(test_dir):
    """Test Python 3.13 detection with compat date >= 2025-09-29."""
    wrangler_toml = test_dir / "wrangler.toml"
    wrangler_toml.write_text("""
name = "test-worker"
compatibility_flags = ["python_workers"]
compatibility_date = "2025-10-01"
""")

    version = get_python_version()
    assert version == "3.13"


def test_wrangler_jsonc_with_compat_flag(test_dir):
    """Test Python 3.13 detection with JSONC format."""
    wrangler_jsonc = test_dir / "wrangler.jsonc"
    wrangler_jsonc.write_text("""{
  // This is a comment
  "name": "test-worker",
  "compatibility_flags": ["python_workers", "python_workers_20250116"],
  "compatibility_date": "2024-01-01"
}""")

    version = get_python_version()
    assert version == "3.13"


def test_compat_date_boundary(test_dir):
    """Test the exact boundary date for compat_date."""
    wrangler_toml = test_dir / "wrangler.toml"

    # Test exactly on the boundary date
    wrangler_toml.write_text("""
name = "test-worker"
compatibility_flags = ["python_workers"]
compatibility_date = "2025-09-29"
""")

    version = get_python_version()
    assert version == "3.13"

    # Test one day before - should return 3.12 (base python_workers)
    wrangler_toml.write_text("""
name = "test-worker"
compatibility_flags = ["python_workers"]
compatibility_date = "2025-09-28"
""")

    version = get_python_version()
    assert (
        version == "3.12"
    )  # Should be 3.12 because only python_workers flag is present


def test_no_wrangler_config(test_dir):
    """Test error when no wrangler config exists."""
    with pytest.raises(click.exceptions.Exit) as exc_info:
        get_python_version()
    assert exc_info.value.exit_code == 1


def test_no_python_workers_flag(test_dir):
    """Test error when python_workers flag is missing."""
    wrangler_toml = test_dir / "wrangler.toml"
    wrangler_toml.write_text("""
name = "test-worker"
compatibility_flags = ["python_workers_20250116"]
compatibility_date = "2025-10-01"
""")

    with pytest.raises(click.exceptions.Exit) as exc_info:
        get_python_version()
    assert exc_info.value.exit_code == 1


def test_wrangler_jsonc_with_multiline_comments(test_dir):
    """Test Python 3.13 detection with JSONC format including multi-line comments."""
    wrangler_jsonc = test_dir / "wrangler.jsonc"
    wrangler_jsonc.write_text("""
/**
* For more details on how to configure Wrangler, refer to:
* https://developers.cloudflare.com/workers/wrangler/configuration/
*/
{
  "name": "test-worker",
  // Single line comment
  "compatibility_flags": [
    /* Another multi-line comment */ "python_workers", "python_workers_20250116"
  ],
  "compatibility_date": "2024-01-01" /* Inline multi-line comment */
}""")

    version = get_python_version()
    assert version == "3.13"


def test_wrangler_jsonc_with_trailing_commas(test_dir):
    """Test JSONC parsing with trailing commas (JSON5 feature)."""
    wrangler_jsonc = test_dir / "wrangler.jsonc"
    wrangler_jsonc.write_text("""{
  "name": "test-worker",
  "compatibility_date": "2025-10-01",
  "compatibility_flags": [
    "python_workers",
    "python_workers_20250116",
    "some_other_flag",
  ], // Trailing comma here
}""")

    version = get_python_version()
    assert version == "3.13"


def test_main_get_python_version_integration(test_dir):
    """Test the main _get_python_version function integration."""

    # Test with no config - should raise error
    with pytest.raises(click.exceptions.Exit) as exc_info:
        get_python_version()
    assert exc_info.value.exit_code == 1

    # Test with config that specifies 3.13
    wrangler_toml = test_dir / "wrangler.toml"
    wrangler_toml.write_text("""
name = "test-worker"
compatibility_date = "2024-09-09"
compatibility_flags = ["python_workers", "python_workers_20250116"]
""")

    version = get_python_version()
    assert version == "3.13"

    # Test with config that specifies 3.12 (only python_workers flag)
    wrangler_toml.write_text("""
name = "test-worker"
compatibility_date = "2024-09-09"
compatibility_flags = ["python_workers"]
""")

    version = get_python_version()
    assert version == "3.12"
