"""WSGI handler tests executed inside workerd."""

# pyright: reportMissingImports=false

import pytest


class TestDjangoCFErrorMessages:
    def test_djangocf_get_app_error_message(self):
        from django_cf import DjangoCF

        cf = DjangoCF()
        with pytest.raises(NotImplementedError) as exc_info:
            cf.get_app()

        assert (
            str(exc_info.value) == "Please implement get_app in your django_cf worker"
        )
        assert "implement implement" not in str(exc_info.value)

    def test_djangocf_durable_object_get_app_error_message(self):
        from django_cf import DjangoCFDurableObject

        with pytest.raises(NotImplementedError) as exc_info:
            DjangoCFDurableObject.get_app(None)

        assert (
            str(exc_info.value) == "Please implement get_app in your django_cf worker"
        )
        assert "implement implement" not in str(exc_info.value)
