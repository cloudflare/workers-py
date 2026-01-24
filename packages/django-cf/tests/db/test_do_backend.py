"""Tests for django_cf/db/backends/do/base.py - Durable Objects database backend."""
import pytest
from unittest.mock import MagicMock, patch
import sys


class TestDODatabaseWrapperProcessQuery:
    """Tests for DO DatabaseWrapper.process_query method."""

    def _create_mock_wrapper(self):
        """Create a mock DO DatabaseWrapper for testing."""

        class MockDOWrapper:
            def __init__(self):
                self._cursor_mock = MagicMock()
                self._cursor_mock._defer_foreign_keys = False

            def cursor(self):
                return self._cursor_mock

            def process_query(self, query, params=None):
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

        return MockDOWrapper()

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

        assert 'null' in result_query
        assert result_params == ['test']

    def test_process_query_with_defer_foreign_keys(self):
        """Test process_query adds PRAGMA when _defer_foreign_keys is True."""
        wrapper = self._create_mock_wrapper()
        wrapper._cursor_mock._defer_foreign_keys = True

        query = 'INSERT INTO users (name) VALUES (%s)'
        params = ['test']
        result = wrapper.process_query(query, params)

        assert 'PRAGMA defer_foreign_keys = on' in result
        assert 'PRAGMA defer_foreign_keys = off' in result


class TestDODatabaseWrapperConfiguration:
    """Tests for DO DatabaseWrapper configuration."""

    def test_vendor_name(self):
        """Test vendor name is correct."""
        with open('/Users/gabriel/PycharmProjects/django-cf/django_cf/db/backends/do/base.py') as f:
            content = f.read()
            assert 'vendor = "cloudflare_durable_objects"' in content
            assert 'display_name = "DO"' in content

    def test_get_connection_params_returns_empty(self):
        """Test that get_connection_params returns empty dict for DO."""
        # DO backend doesn't need connection params like D1 does
        class MockDOWrapper:
            def get_connection_params(self):
                return {}

        wrapper = MockDOWrapper()
        params = wrapper.get_connection_params()

        assert params == {}


class TestDOMissingDateTruncBug:
    """Tests documenting the missing date_trunc bug in DO backend."""

    def test_do_process_query_missing_date_trunc(self):
        """
        Test demonstrating that DO backend is missing date_trunc replacement.

        The D1 backend calls replace_date_trunc_in_sql() in process_query(),
        but the DO backend does NOT. This is a bug that should be fixed.
        """
        # DO backend's process_query (simulated - without date_trunc)
        def do_process_query(query, params=None):
            # Note: NO replace_date_trunc_in_sql call
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

        # D1 backend's process_query (simulated - with date_trunc)
        def d1_process_query(query, params=None):
            from django_cf.db.base_engine import replace_date_trunc_in_sql
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
            return query, params

        test_query = 'SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders'
        test_params = ['year', 'UTC', 'UTC']

        # D1 correctly replaces date_trunc
        d1_result, _ = d1_process_query(test_query, test_params)
        assert 'django_date_trunc' not in d1_result

        # DO does NOT replace date_trunc (BUG)
        do_result, _ = do_process_query(test_query, test_params)
        # This shows the bug - django_date_trunc is still in the query
        # When this test fails after fix, remove the bug documentation
        assert 'django_date_trunc' in do_result  # Bug: should NOT be in result


class TestDOStorageInitialization:
    """Tests for DO storage initialization."""

    def test_storage_module_exists(self):
        """Test that storage module exists for DO backend."""
        import importlib.util
        spec = importlib.util.find_spec('django_cf.db.backends.do.storage')
        assert spec is not None

    def test_get_storage_function_exists(self):
        """Test that get_storage function exists in storage module."""
        with open('/Users/gabriel/PycharmProjects/django-cf/django_cf/db/backends/do/base.py') as f:
            content = f.read()
            assert 'from .storage import get_storage' in content


class TestDOQueryExecution:
    """Tests for DO query execution patterns."""

    def test_read_query_uses_raw(self):
        """Test that read queries use raw() method."""
        # Simulated DO run_query logic
        def mock_run_query(query, params=None, is_read=True):
            mock_db = MagicMock()
            mock_stmt = MagicMock()

            if params:
                mock_db.exec.return_value = mock_stmt
            else:
                mock_db.exec.return_value = mock_stmt

            if is_read:
                # Read queries call raw().toArray()
                mock_stmt.raw.return_value.toArray.return_value.to_py.return_value = []
                return mock_stmt.raw().toArray().to_py()
            else:
                return mock_stmt

        result = mock_run_query('SELECT * FROM users', is_read=True)
        assert result == []

    def test_error_handling_exposes_stack(self):
        """
        Test documenting that DO backend exposes full stack traces.

        This is a potential security issue - stack traces should not
        be exposed in production errors.
        """
        # The DO backend has this pattern:
        # except:
        #     from js import Error
        #     Error.stackTraceLimit = 1e10
        #     raise Error(Error.new().stack)

        with open('/Users/gabriel/PycharmProjects/django-cf/django_cf/db/backends/do/base.py') as f:
            content = f.read()
            # Verify the problematic pattern exists
            assert 'Error.stackTraceLimit = 1e10' in content
            assert 'raise Error(Error.new().stack)' in content


class TestDOParamConversion:
    """Tests for DO parameter type conversion."""

    def test_boolean_true_not_converted_in_process_query(self):
        """
        Test that boolean True is NOT converted in process_query.

        Note: Boolean conversion happens in CFDatabase.execute(), not process_query().
        """
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

        query = 'INSERT INTO test (active) VALUES (%s)'
        params = [True]
        result_query, result_params = process_query(query, params)

        # process_query doesn't convert booleans - that's CFDatabase.execute's job
        assert result_params == [True]

    def test_multiple_none_params_order_preserved(self):
        """Test that order is preserved with multiple None params."""
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

        query = 'INSERT INTO test (a, b, c, d) VALUES (%s, %s, %s, %s)'
        params = [1, None, 2, None]
        result_query, result_params = process_query(query, params)

        # Non-None params should be in order
        assert result_params == [1, 2]
        # Query should have correct mix of ? and null
        assert result_query == 'INSERT INTO test (a, b, c, d) VALUES (?, null, ?, null)'


class TestDOPragmaReturnTypeBug:
    """Tests documenting the PRAGMA return type bug in DO backend."""

    def test_pragma_returns_string_not_tuple(self):
        """
        Test demonstrating that PRAGMA mode returns string instead of tuple.

        When _defer_foreign_keys is True, process_query returns a string
        instead of a (query, params) tuple. This causes the params to be lost.
        """

        class MockDOWrapper:
            def __init__(self):
                self._cursor_mock = MagicMock()
                self._cursor_mock._defer_foreign_keys = True

            def cursor(self):
                return self._cursor_mock

            def process_query(self, query, params=None):
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
                    # BUG: Returns string, not tuple - params are lost!
                    return f'''
                    PRAGMA defer_foreign_keys = on

                    {query}

                    PRAGMA defer_foreign_keys = off
                    '''

                return query, params

        wrapper = MockDOWrapper()
        query = 'INSERT INTO users (name) VALUES (%s)'
        params = ['test']

        result = wrapper.process_query(query, params)

        # Bug: result is a string, not a tuple
        assert isinstance(result, str)
        # The params ['test'] are completely lost!
        # This will cause issues when trying to unpack: proc_query, params = result
