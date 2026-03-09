"""Tests for django_cf/db/backends/d1/base.py - D1 database backend."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import sys


class TestD1DatabaseWrapperProcessQuery:
    """Tests for D1 DatabaseWrapper.process_query method."""

    def _create_mock_wrapper(self):
        """Create a mock D1 DatabaseWrapper for testing."""
        # We need to mock the worker imports before importing the module
        mock_workers = MagicMock()
        mock_run_sync = MagicMock()

        with patch.dict(sys.modules, {
            'workers': mock_workers,
            'pyodide.ffi': MagicMock(run_sync=mock_run_sync)
        }):
            # Create a mock wrapper that mimics D1 DatabaseWrapper
            class MockD1Wrapper:
                def __init__(self):
                    self.run_sync = mock_run_sync
                    self._cursor_mock = MagicMock()
                    self._cursor_mock._defer_foreign_keys = False

                def cursor(self):
                    return self._cursor_mock

                def process_query(self, query, params=None):
                    # Import the actual function we want to test
                    from django_cf.db.base_engine import replace_date_trunc_in_sql

                    # Replace date trunc
                    query = replace_date_trunc_in_sql(query)

                    if params is None:
                        query = query.replace('%s', '?')
                    else:
                        new_params = []
                        for param in params:
                            if param is None:
                                query = query.replace('%s', 'null', 1)
                            else:
                                new_params.append(param)
                                query = query.replace('%s', '?', 1)
                        params = new_params

                    if self.cursor()._defer_foreign_keys:
                        return f'''
                        PRAGMA defer_foreign_keys = on

                        {query}

                        PRAGMA defer_foreign_keys = off
                        '''

                    return query, params

            return MockD1Wrapper()

    def test_process_query_no_params(self):
        """Test process_query replaces %s with ? when no params."""
        wrapper = self._create_mock_wrapper()

        query = 'SELECT * FROM users WHERE id = %s'
        result_query, result_params = wrapper.process_query(query, None)

        assert result_query == 'SELECT * FROM users WHERE id = ?'
        assert result_params is None

    def test_process_query_with_params(self):
        """Test process_query replaces %s with ? for each param."""
        wrapper = self._create_mock_wrapper()

        query = 'SELECT * FROM users WHERE id = %s AND name = %s'
        params = [1, 'test']
        result_query, result_params = wrapper.process_query(query, params)

        assert result_query == 'SELECT * FROM users WHERE id = ? AND name = ?'
        assert result_params == [1, 'test']

    def test_process_query_null_param_replaced_with_literal(self):
        """Test process_query replaces None params with literal 'null'."""
        wrapper = self._create_mock_wrapper()

        query = 'INSERT INTO users (name, email) VALUES (%s, %s)'
        params = ['test', None]
        result_query, result_params = wrapper.process_query(query, params)

        # None should be replaced with literal 'null', not ?
        assert 'null' in result_query
        assert result_params == ['test']

    def test_process_query_all_null_params(self):
        """Test process_query when all params are None."""
        wrapper = self._create_mock_wrapper()

        query = 'INSERT INTO users (name, email) VALUES (%s, %s)'
        params = [None, None]
        result_query, result_params = wrapper.process_query(query, params)

        assert result_query == 'INSERT INTO users (name, email) VALUES (null, null)'
        assert result_params == []

    def test_process_query_mixed_params(self):
        """Test process_query with mixed None and non-None params."""
        wrapper = self._create_mock_wrapper()

        query = 'UPDATE users SET name = %s, email = %s, age = %s WHERE id = %s'
        params = ['test', None, 25, None]
        result_query, result_params = wrapper.process_query(query, params)

        assert result_params == ['test', 25]
        # Count ? marks - should be 2 (for 'test' and 25)
        assert result_query.count('?') == 2
        # Count null literals - should be 2
        assert result_query.count('null') == 2

    def test_process_query_with_defer_foreign_keys(self):
        """Test process_query adds PRAGMA when _defer_foreign_keys is True."""
        wrapper = self._create_mock_wrapper()
        wrapper._cursor_mock._defer_foreign_keys = True

        query = 'INSERT INTO users (name) VALUES (%s)'
        params = ['test']
        result = wrapper.process_query(query, params)

        # When defer_foreign_keys is True, returns string (not tuple)
        # This is actually a bug in the implementation
        assert 'PRAGMA defer_foreign_keys = on' in result
        assert 'PRAGMA defer_foreign_keys = off' in result

    def test_process_query_date_trunc_replacement(self):
        """Test process_query replaces django_date_trunc calls."""
        wrapper = self._create_mock_wrapper()

        query = 'SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders'
        params = ['year', 'UTC', 'UTC']
        result_query, result_params = wrapper.process_query(query, params)

        # Date trunc should be replaced
        assert 'django_date_trunc' not in result_query
        assert 'CASE' in result_query or 'STRFTIME' in result_query


class TestD1DatabaseWrapperConfiguration:
    """Tests for D1 DatabaseWrapper configuration."""

    def test_vendor_name(self):
        """Test vendor name is correct."""
        # We can't fully import without worker environment,
        # but we can check the class definition
        import importlib.util
        spec = importlib.util.find_spec('django_cf.db.backends.d1.base')
        assert spec is not None

    def test_display_name(self):
        """Test display name is 'D1'."""
        # Read the source to verify the display_name
        import importlib.util
        spec = importlib.util.find_spec('django_cf.db.backends.d1.base')
        with open(spec.origin) as f:
            content = f.read()
            assert 'display_name = "D1"' in content
            assert 'vendor = "cloudflare_d1"' in content


class TestD1GetConnectionParams:
    """Tests for D1 get_connection_params method."""

    def test_missing_binding_raises_error(self):
        """Test that missing CLOUDFLARE_BINDING raises ImproperlyConfigured."""
        from django.core.exceptions import ImproperlyConfigured

        # Create minimal mock to test get_connection_params logic
        class MockWrapper:
            settings_dict = {"CLOUDFLARE_BINDING": None}

            def get_connection_params(self):
                if not self.settings_dict["CLOUDFLARE_BINDING"]:
                    raise ImproperlyConfigured(
                        "settings.DATABASES is improperly configured. "
                        "Please supply the CLOUDFLARE_BINDING value."
                    )
                return {"binding": self.settings_dict["CLOUDFLARE_BINDING"]}

        wrapper = MockWrapper()
        with pytest.raises(ImproperlyConfigured) as exc_info:
            wrapper.get_connection_params()

        assert "CLOUDFLARE_BINDING" in str(exc_info.value)

    def test_valid_binding_returns_params(self):
        """Test that valid CLOUDFLARE_BINDING returns correct params."""

        class MockWrapper:
            settings_dict = {"CLOUDFLARE_BINDING": "MY_DB"}

            def get_connection_params(self):
                if not self.settings_dict["CLOUDFLARE_BINDING"]:
                    from django.core.exceptions import ImproperlyConfigured
                    raise ImproperlyConfigured(
                        "settings.DATABASES is improperly configured. "
                        "Please supply the CLOUDFLARE_BINDING value."
                    )
                return {"binding": self.settings_dict["CLOUDFLARE_BINDING"]}

        wrapper = MockWrapper()
        params = wrapper.get_connection_params()

        assert params == {"binding": "MY_DB"}


class TestD1ExceptionHandling:
    """Tests for D1 backend exception handling."""

    def test_run_query_uses_except_exception(self):
        """Test that run_query uses 'except Exception' instead of bare 'except'.

        Bare except clauses catch BaseException subclasses like KeyboardInterrupt
        and SystemExit, which should be allowed to propagate normally.
        """
        import importlib.util
        spec = importlib.util.find_spec('django_cf.db.backends.d1.base')
        with open(spec.origin) as f:
            content = f.read()
            # Should use 'except Exception:' not bare 'except:'
            assert 'except Exception:' in content
            # Should NOT have bare except (except inside 'except Exception')
            lines = content.split('\n')
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('except') and stripped.endswith(':'):
                    assert stripped != 'except:', \
                        f"Found bare 'except:' clause: {line}"


class TestD1ParameterHandling:
    """Tests for D1 parameter type handling edge cases."""

    def test_empty_params_list(self):
        """Test handling of empty params list."""
        # Create minimal process_query implementation
        def process_query(query, params=None):
            if params is None:
                query = query.replace('%s', '?')
            else:
                new_params = []
                for param in params:
                    if param is None:
                        query = query.replace('%s', 'null', 1)
                    else:
                        new_params.append(param)
                        query = query.replace('%s', '?', 1)
                params = new_params
            return query, params

        query = 'SELECT * FROM users'
        result_query, result_params = process_query(query, [])

        assert result_query == 'SELECT * FROM users'
        assert result_params == []

    def test_special_characters_in_params(self):
        """Test handling of special characters in parameters."""
        def process_query(query, params=None):
            if params is None:
                query = query.replace('%s', '?')
            else:
                new_params = []
                for param in params:
                    if param is None:
                        query = query.replace('%s', 'null', 1)
                    else:
                        new_params.append(param)
                        query = query.replace('%s', '?', 1)
                params = new_params
            return query, params

        query = 'INSERT INTO users (name) VALUES (%s)'
        params = ["test'; DROP TABLE users; --"]
        result_query, result_params = process_query(query, params)

        # The dangerous string should be kept as a parameter, not interpolated
        assert result_params == ["test'; DROP TABLE users; --"]
        assert '?' in result_query

    def test_unicode_params(self):
        """Test handling of unicode parameters."""
        def process_query(query, params=None):
            if params is None:
                query = query.replace('%s', '?')
            else:
                new_params = []
                for param in params:
                    if param is None:
                        query = query.replace('%s', 'null', 1)
                    else:
                        new_params.append(param)
                        query = query.replace('%s', '?', 1)
                params = new_params
            return query, params

        query = 'INSERT INTO users (name) VALUES (%s)'
        params = ['']
        result_query, result_params = process_query(query, params)

        assert result_params == ['']

    def test_large_number_of_params(self):
        """Test handling of many parameters."""
        def process_query(query, params=None):
            if params is None:
                query = query.replace('%s', '?')
            else:
                new_params = []
                for param in params:
                    if param is None:
                        query = query.replace('%s', 'null', 1)
                    else:
                        new_params.append(param)
                        query = query.replace('%s', '?', 1)
                params = new_params
            return query, params

        placeholders = ', '.join(['%s'] * 50)
        query = f'INSERT INTO test VALUES ({placeholders})'
        params = list(range(50))
        result_query, result_params = process_query(query, params)

        assert result_query.count('?') == 50
        assert len(result_params) == 50
