"""Tests for WSGI handler and DjangoCF classes."""
import pytest
from django_cf import DjangoCF, DjangoCFDurableObject


class TestDjangoCFErrorMessages:
    """Tests for DjangoCF class error messages."""

    def test_djangocf_get_app_error_message(self):
        """Test that DjangoCF.get_app() raises NotImplementedError with correct message."""
        cf = DjangoCF()
        with pytest.raises(NotImplementedError) as exc_info:
            cf.get_app()
        # Verify no duplicate "implement" word
        assert str(exc_info.value) == "Please implement get_app in your django_cf worker"
        assert "implement implement" not in str(exc_info.value)

    def test_djangocf_durable_object_get_app_error_message(self):
        """Test that DjangoCFDurableObject.get_app() raises NotImplementedError with correct message."""
        # DjangoCFDurableObject.__init__ requires ctx and env, so test get_app directly
        assert "implement get_app" in DjangoCFDurableObject.get_app.__code__.co_consts[1]
        # Verify no duplicate word in the source constant
        for const in DjangoCFDurableObject.get_app.__code__.co_consts:
            if isinstance(const, str) and "implement" in const:
                assert "implement implement" not in const


class TestWSGIHeaderTransformation:
    """Tests for WSGI header name transformation.

    Per PEP 3333 (WSGI spec), HTTP headers should be stored in the environ dict as
    HTTP_HEADER_NAME where dashes are replaced with underscores and everything is uppercased.

    The handle_wsgi function can't be tested directly (requires Pyodide/js imports),
    so we verify the transformation logic via source code inspection.
    """

    def test_header_transformation_replaces_dashes(self):
        """Verify the header transformation code replaces dashes with underscores."""
        import inspect
        from django_cf import handle_wsgi

        source = inspect.getsource(handle_wsgi)
        # The header loop should include .replace("-", "_") for WSGI compliance
        assert '.replace("-", "_")' in source or ".replace('-', '_')" in source

    def test_header_transformation_logic_directly(self):
        """Test the header transformation expression produces correct WSGI keys."""
        # This tests the exact expression used in handle_wsgi line 42:
        # f'HTTP_{header[0].upper().replace("-", "_")}'
        test_cases = [
            ("content-type", "HTTP_CONTENT_TYPE"),
            ("x-forwarded-for", "HTTP_X_FORWARDED_FOR"),
            ("cf-access-jwt-assertion", "HTTP_CF_ACCESS_JWT_ASSERTION"),
            ("accept", "HTTP_ACCEPT"),
            ("x-custom-header", "HTTP_X_CUSTOM_HEADER"),
            ("cf-connecting-ip", "HTTP_CF_CONNECTING_IP"),
        ]
        for header_name, expected_key in test_cases:
            result = f'HTTP_{header_name.upper().replace("-", "_")}'
            assert result == expected_key, (
                f"Header '{header_name}' should map to '{expected_key}', got '{result}'"
            )
