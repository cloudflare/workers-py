"""Tests for django_cf/db/base_engine.py - Core database functionality."""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch


class TestCFResult:
    """Tests for the CFResult class."""

    def test_init(self):
        """Test CFResult initialization."""
        from django_cf.db.base_engine import CFResult

        data = [(1, 'a'), (2, 'b'), (3, 'c')]
        result = CFResult(data)

        assert result.data == data
        assert result.lastrowid is None
        assert result.rowcount == -1

    def test_iter(self):
        """Test CFResult iteration."""
        from django_cf.db.base_engine import CFResult

        data = [(1, 'a'), (2, 'b')]
        result = CFResult(data)

        items = list(result)
        assert items == [(1, 'a'), (2, 'b')]

    def test_set_lastrowid(self):
        """Test setting lastrowid."""
        from django_cf.db.base_engine import CFResult

        result = CFResult([])
        result.set_lastrowid(42)

        assert result.lastrowid == 42

    def test_set_rowcount(self):
        """Test setting rowcount."""
        from django_cf.db.base_engine import CFResult

        result = CFResult([])
        result.set_rowcount(10)

        assert result.rowcount == 10

    def test_fetchone_with_data(self):
        """Test fetchone returns and removes last item."""
        from django_cf.db.base_engine import CFResult

        data = [(1, 'a'), (2, 'b'), (3, 'c')]
        result = CFResult(data)

        row = result.fetchone()
        assert row == (3, 'c')
        assert len(result.data) == 2

    def test_fetchone_empty(self):
        """Test fetchone returns None when empty."""
        from django_cf.db.base_engine import CFResult

        result = CFResult([])
        row = result.fetchone()

        assert row is None

    def test_fetchall(self):
        """Test fetchall returns all rows."""
        from django_cf.db.base_engine import CFResult

        data = [(1, 'a'), (2, 'b'), (3, 'c')]
        result = CFResult(data)

        rows = result.fetchall()
        # Note: fetchall uses fetchone which pops from end, so order is reversed
        assert rows == [(3, 'c'), (2, 'b'), (1, 'a')]
        assert len(result.data) == 0

    def test_fetchall_empty(self):
        """Test fetchall on empty result."""
        from django_cf.db.base_engine import CFResult

        result = CFResult([])
        rows = result.fetchall()

        assert rows == []

    def test_fetchmany_default(self):
        """Test fetchmany with default size=1."""
        from django_cf.db.base_engine import CFResult

        data = [(1, 'a'), (2, 'b'), (3, 'c')]
        result = CFResult(data)

        rows = result.fetchmany()
        assert rows == [(3, 'c')]
        assert len(result.data) == 2

    def test_fetchmany_specific_size(self):
        """Test fetchmany with specific size."""
        from django_cf.db.base_engine import CFResult

        data = [(1, 'a'), (2, 'b'), (3, 'c')]
        result = CFResult(data)

        rows = result.fetchmany(2)
        assert len(rows) == 2
        assert len(result.data) == 1

    def test_fetchmany_more_than_available(self):
        """Test fetchmany when requesting more than available."""
        from django_cf.db.base_engine import CFResult

        data = [(1, 'a'), (2, 'b')]
        result = CFResult(data)

        rows = result.fetchmany(5)
        assert len(rows) == 2
        assert len(result.data) == 0

    def test_from_object_with_list_rows(self):
        """Test from_object with list-style row data."""
        from django_cf.db.base_engine import CFResult

        data = [[1, 'hello', True], [2, 'world', False]]
        result = CFResult.from_object('SELECT * FROM test', None, data)

        rows = list(result)
        assert len(rows) == 2
        assert rows[0] == (1, 'hello', True)
        assert rows[1] == (2, 'world', False)

    def test_from_object_with_dict_rows(self):
        """Test from_object with dict-style row data."""
        from django_cf.db.base_engine import CFResult

        data = [{'id': 1, 'name': 'hello'}, {'id': 2, 'name': 'world'}]
        result = CFResult.from_object('SELECT * FROM test', None, data)

        rows = list(result)
        assert len(rows) == 2

    def test_from_object_insert_rowcount(self):
        """Test from_object sets rowcount for INSERT."""
        from django_cf.db.base_engine import CFResult

        result = CFResult.from_object(
            'INSERT INTO test VALUES (1)',
            None,
            [],
            rows_read=0,
            rows_written=5
        )

        assert result.rowcount == 5

    def test_from_object_update_rowcount(self):
        """Test from_object sets rowcount for UPDATE."""
        from django_cf.db.base_engine import CFResult

        result = CFResult.from_object(
            'UPDATE test SET name = "new"',
            None,
            [],
            rows_read=0,
            rows_written=3
        )

        assert result.rowcount == 3

    def test_from_object_delete_rowcount(self):
        """Test from_object sets rowcount for DELETE."""
        from django_cf.db.base_engine import CFResult

        result = CFResult.from_object(
            'DELETE FROM test WHERE id = 1',
            None,
            [],
            rows_read=0,
            rows_written=2
        )

        assert result.rowcount == 2

    def test_from_object_select_rowcount(self):
        """Test from_object sets rowcount for SELECT."""
        from django_cf.db.base_engine import CFResult

        result = CFResult.from_object(
            'SELECT * FROM test',
            None,
            [[1], [2], [3]],  # List-style rows, not tuples
            rows_read=3,
            rows_written=0
        )

        assert result.rowcount == 3

    def test_from_object_lastrowid(self):
        """Test from_object sets lastrowid."""
        from django_cf.db.base_engine import CFResult

        result = CFResult.from_object(
            'INSERT INTO test VALUES (1)',
            None,
            [],
            last_row_id=42
        )

        assert result.lastrowid == 42


class TestIsReadOnlyQuery:
    """Tests for the is_read_only_query function."""

    def test_select_query(self):
        """Test SELECT queries are read-only."""
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query('SELECT * FROM users') is True
        assert is_read_only_query('  SELECT id FROM users WHERE id = 1') is True
        assert is_read_only_query('select * from users') is True

    def test_insert_query(self):
        """Test INSERT queries are not read-only."""
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query('INSERT INTO users (name) VALUES ("test")') is False

    def test_update_query(self):
        """Test UPDATE queries are not read-only."""
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query('UPDATE users SET name = "new" WHERE id = 1') is False

    def test_delete_query(self):
        """Test DELETE queries are not read-only."""
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query('DELETE FROM users WHERE id = 1') is False

    def test_create_table_query(self):
        """Test CREATE TABLE queries are not read-only."""
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query('CREATE TABLE users (id INT)') is False

    def test_alter_table_query(self):
        """Test ALTER TABLE queries are not read-only."""
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query('ALTER TABLE users ADD COLUMN email TEXT') is False

    def test_drop_table_query(self):
        """Test DROP TABLE queries are not read-only."""
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query('DROP TABLE users') is False

    def test_replace_query(self):
        """Test REPLACE queries are not read-only."""
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query('REPLACE INTO users (id, name) VALUES (1, "test")') is False

    def test_empty_query(self):
        """Test empty query returns False."""
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query('') is False
        assert is_read_only_query('   ') is False


class TestReplaceDateTruncInSql:
    """Tests for the replace_date_trunc_in_sql function."""

    def test_no_date_trunc(self):
        """Test SQL without date_trunc is unchanged."""
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        sql = 'SELECT * FROM users WHERE created_at > "2023-01-01"'
        result = replace_date_trunc_in_sql(sql)

        assert result == sql

    def test_django_date_trunc_replacement(self):
        """Test django_date_trunc is replaced with CASE statement."""
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        sql = 'SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders'
        result = replace_date_trunc_in_sql(sql)

        # Should contain CASE statement with STRFTIME
        assert 'CASE %s' in result
        assert 'STRFTIME' in result
        assert 'django_date_trunc' not in result

    def test_django_datetime_trunc_replacement(self):
        """Test django_datetime_trunc is replaced with CASE statement."""
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        sql = 'SELECT django_datetime_trunc(%s, created_at, %s, %s) FROM orders'
        result = replace_date_trunc_in_sql(sql)

        # Should contain CASE statement
        assert 'CASE %s' in result
        assert 'django_datetime_trunc' not in result

    def test_year_truncation_in_case(self):
        """Test year truncation template is in result."""
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        sql = 'SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders'
        result = replace_date_trunc_in_sql(sql)

        assert "WHEN 'year'" in result
        assert '%Y-01-01' in result

    def test_month_truncation_in_case(self):
        """Test month truncation template is in result."""
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        sql = 'SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders'
        result = replace_date_trunc_in_sql(sql)

        assert "WHEN 'month'" in result
        assert '%Y-%m-01' in result

    def test_day_truncation_in_case(self):
        """Test day truncation template is in result."""
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        sql = 'SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders'
        result = replace_date_trunc_in_sql(sql)

        assert "WHEN 'day'" in result
        assert 'DATE(created_at)' in result

    def test_multiple_date_truncs(self):
        """Test multiple django_date_trunc calls are replaced."""
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        sql = '''SELECT django_date_trunc(%s, created_at, %s, %s),
                        django_date_trunc(%s, updated_at, %s, %s) FROM orders'''
        result = replace_date_trunc_in_sql(sql)

        assert 'django_date_trunc' not in result
        # Should have multiple CASE statements
        assert result.count('CASE %s') == 2


class TestCFDatabase:
    """Tests for the CFDatabase class."""

    def test_connect(self):
        """Test CFDatabase.connect creates new instance."""
        from django_cf.db.base_engine import CFDatabase

        mock_wrapper = MagicMock()
        db = CFDatabase.connect(mock_wrapper)

        assert isinstance(db, CFDatabase)
        assert db.databaseWrapper == mock_wrapper

    def test_cursor_returns_self(self):
        """Test cursor() returns self."""
        from django_cf.db.base_engine import CFDatabase

        db = CFDatabase(MagicMock())
        cursor = db.cursor()

        assert cursor is db

    def test_commit_does_nothing(self):
        """Test commit() returns None (no-op)."""
        from django_cf.db.base_engine import CFDatabase

        db = CFDatabase(MagicMock())
        result = db.commit()

        assert result is None

    def test_rollback_does_nothing(self):
        """Test rollback() returns None (no-op)."""
        from django_cf.db.base_engine import CFDatabase

        db = CFDatabase(MagicMock())
        result = db.rollback()

        assert result is None

    def test_close_does_nothing(self):
        """Test close() returns None."""
        from django_cf.db.base_engine import CFDatabase

        db = CFDatabase(MagicMock())
        result = db.close()

        assert result is None

    def test_defer_foreign_keys(self):
        """Test defer_foreign_keys correctly sets the instance variable."""
        from django_cf.db.base_engine import CFDatabase

        db = CFDatabase(MagicMock())

        db.defer_foreign_keys(True)
        assert db._defer_foreign_keys is True

        db.defer_foreign_keys(False)
        assert db._defer_foreign_keys is False

    def test_execute_converts_boolean_true(self):
        """Test execute converts True to 1."""
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])

        db = CFDatabase(mock_wrapper)
        db.execute('INSERT INTO test VALUES (%s)', (True,))

        # Check that True was converted to 1
        call_args = mock_wrapper.run_query.call_args
        assert call_args[0][1] == (1,)

    def test_execute_converts_boolean_false(self):
        """Test execute converts False to 0."""
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])

        db = CFDatabase(mock_wrapper)
        db.execute('INSERT INTO test VALUES (%s)', (False,))

        # Check that False was converted to 0
        call_args = mock_wrapper.run_query.call_args
        assert call_args[0][1] == (0,)

    def test_execute_converts_decimal_to_string(self):
        """Test execute converts Decimal to string."""
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])

        db = CFDatabase(mock_wrapper)
        db.execute('INSERT INTO test VALUES (%s)', (Decimal('10.5'),))

        # Check that Decimal was converted to string
        call_args = mock_wrapper.run_query.call_args
        assert call_args[0][1] == ('10.5',)

    def test_execute_no_params(self):
        """Test execute with no parameters."""
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])

        db = CFDatabase(mock_wrapper)
        db.execute('SELECT * FROM test')

        call_args = mock_wrapper.run_query.call_args
        assert call_args[0][0] == 'SELECT * FROM test'
        assert call_args[0][1] is None

    def test_fetchone_delegates_to_result(self):
        """Test fetchone delegates to lastResult."""
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_result = CFResult([(1, 'test')])
        mock_wrapper.run_query.return_value = mock_result

        db = CFDatabase(mock_wrapper)
        db.execute('SELECT * FROM test')
        row = db.fetchone()

        assert row == (1, 'test')

    def test_fetchall_delegates_to_result(self):
        """Test fetchall delegates to lastResult."""
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_result = CFResult([(1, 'a'), (2, 'b')])
        mock_wrapper.run_query.return_value = mock_result

        db = CFDatabase(mock_wrapper)
        db.execute('SELECT * FROM test')
        rows = db.fetchall()

        assert len(rows) == 2

    def test_lastrowid_property(self):
        """Test lastrowid property delegates to lastResult."""
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_result = CFResult([])
        mock_result.set_lastrowid(42)
        mock_wrapper.run_query.return_value = mock_result

        db = CFDatabase(mock_wrapper)
        db.execute('INSERT INTO test VALUES (1)')

        assert db.lastrowid == 42

    def test_rowcount_property(self):
        """Test rowcount property delegates to lastResult."""
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_result = CFResult([])
        mock_result.set_rowcount(5)
        mock_wrapper.run_query.return_value = mock_result

        db = CFDatabase(mock_wrapper)
        db.execute('UPDATE test SET name = "new"')

        assert db.rowcount == 5


class TestCFDatabaseFeatures:
    """Tests for the CFDatabaseFeatures class."""

    def test_transactions_disabled(self):
        """Test that transactions are disabled."""
        from django_cf.db.base_engine import CFDatabaseFeatures

        mock_wrapper = MagicMock()
        features = CFDatabaseFeatures(mock_wrapper)

        assert features.atomic_transactions is False
        assert features.supports_transactions is False

    def test_savepoints_disabled(self):
        """Test that savepoints are disabled."""
        from django_cf.db.base_engine import CFDatabaseFeatures

        mock_wrapper = MagicMock()
        features = CFDatabaseFeatures(mock_wrapper)

        assert features.can_release_savepoints is False

    def test_constraint_checks_disabled(self):
        """Test that constraint checks cannot be deferred."""
        from django_cf.db.base_engine import CFDatabaseFeatures

        mock_wrapper = MagicMock()
        features = CFDatabaseFeatures(mock_wrapper)

        assert features.can_defer_constraint_checks is False
        assert features.supports_pragma_foreign_key_check is False

    def test_max_query_params(self):
        """Test max_query_params is set."""
        from django_cf.db.base_engine import CFDatabaseFeatures

        mock_wrapper = MagicMock()
        features = CFDatabaseFeatures(mock_wrapper)

        assert features.max_query_params == 100

    def test_bulk_insert_enabled(self):
        """Test bulk insert is enabled."""
        from django_cf.db.base_engine import CFDatabaseFeatures

        mock_wrapper = MagicMock()
        features = CFDatabaseFeatures(mock_wrapper)

        assert features.has_bulk_insert is True
        assert features.can_return_columns_from_insert is True


class TestCFDatabaseWrapper:
    """Tests for the CFDatabaseWrapper class."""

    def test_get_database_version(self):
        """Test get_database_version returns tuple."""
        from django_cf.db.base_engine import CFDatabaseWrapper

        with patch.object(CFDatabaseWrapper, '__init__', lambda x, *args: None):
            wrapper = CFDatabaseWrapper.__new__(CFDatabaseWrapper)
            version = wrapper.get_database_version()

            assert version == (4,)

    def test_close_does_nothing(self):
        """Test close() is a no-op."""
        from django_cf.db.base_engine import CFDatabaseWrapper

        with patch.object(CFDatabaseWrapper, '__init__', lambda x, *args: None):
            wrapper = CFDatabaseWrapper.__new__(CFDatabaseWrapper)
            result = wrapper.close()

            assert result is None

    def test_savepoint_not_allowed(self):
        """Test _savepoint_allowed returns False."""
        from django_cf.db.base_engine import CFDatabaseWrapper

        with patch.object(CFDatabaseWrapper, '__init__', lambda x, *args: None):
            wrapper = CFDatabaseWrapper.__new__(CFDatabaseWrapper)
            result = wrapper._savepoint_allowed()

            assert result is False

    def test_is_usable_always_true(self):
        """Test is_usable always returns True."""
        from django_cf.db.base_engine import CFDatabaseWrapper

        with patch.object(CFDatabaseWrapper, '__init__', lambda x, *args: None):
            wrapper = CFDatabaseWrapper.__new__(CFDatabaseWrapper)
            result = wrapper.is_usable()

            assert result is True

    def test_run_query_not_implemented(self):
        """Test run_query raises NotImplementedError."""
        from django_cf.db.base_engine import CFDatabaseWrapper

        with patch.object(CFDatabaseWrapper, '__init__', lambda x, *args: None):
            wrapper = CFDatabaseWrapper.__new__(CFDatabaseWrapper)

            with pytest.raises(NotImplementedError):
                wrapper.run_query('SELECT 1')


class TestCFDatabaseOperations:
    """Tests for the CFDatabaseOperations class."""

    def test_bulk_insert_sql(self):
        """Test bulk_insert_sql generates correct SQL."""
        from django_cf.db.base_engine import CFDatabaseOperations

        mock_wrapper = MagicMock()
        ops = CFDatabaseOperations(mock_wrapper)

        fields = ['id', 'name']
        placeholder_rows = [('%s', '%s'), ('%s', '%s')]

        result = ops.bulk_insert_sql(fields, placeholder_rows)

        assert result == 'VALUES (%s, %s), (%s, %s)'

    def test_last_executed_query_no_params(self):
        """Test last_executed_query with no parameters."""
        from django_cf.db.base_engine import CFDatabaseOperations

        mock_wrapper = MagicMock()
        ops = CFDatabaseOperations(mock_wrapper)

        sql = 'SELECT * FROM test'
        result = ops.last_executed_query(None, sql, None)

        assert result == sql

    def test_last_executed_query_with_params(self):
        """Test last_executed_query with parameters."""
        from django_cf.db.base_engine import CFDatabaseOperations

        mock_wrapper = MagicMock()
        mock_wrapper.connection = MagicMock()
        mock_cursor = MagicMock()
        mock_wrapper.connection.cursor.return_value = mock_cursor
        ops = CFDatabaseOperations(mock_wrapper)

        sql = 'SELECT * FROM test WHERE id = %s'
        # The actual result depends on _quote_params_for_last_executed_query
        # which may return None, causing substitution to either work or fall back
        result = ops.last_executed_query(None, sql, [1])

        # Result should be a string (either substituted or original)
        assert isinstance(result, str)
        assert 'SELECT * FROM test WHERE id' in result

    def test_last_executed_query_catches_formatting_errors(self):
        """Test last_executed_query catches Exception on format failure."""
        from django_cf.db.base_engine import CFDatabaseOperations

        mock_wrapper = MagicMock()
        ops = CFDatabaseOperations(mock_wrapper)

        # Mismatched format string and params to trigger formatting error
        sql = 'SELECT * FROM test WHERE id = %s AND name = %s'
        params = (1,)  # Too few params for the format string

        result = ops.last_executed_query(None, sql, params)

        # Should fall back to returning original sql on formatting error
        assert result == sql

    def test_last_executed_query_does_not_catch_keyboard_interrupt(self):
        """Test last_executed_query does not suppress KeyboardInterrupt."""
        from django_cf.db.base_engine import CFDatabaseOperations

        mock_wrapper = MagicMock()
        ops = CFDatabaseOperations(mock_wrapper)

        # Object whose __str__ raises KeyboardInterrupt during sql % params
        class BadStr:
            def __str__(self):
                raise KeyboardInterrupt()
            def __format__(self, spec):
                raise KeyboardInterrupt()

        # Patch _quote_params to return a tuple with our bad object
        ops._quote_params_for_last_executed_query = lambda params: (BadStr(),)

        sql = 'SELECT * FROM test WHERE id = %s'

        with pytest.raises(KeyboardInterrupt):
            ops.last_executed_query(None, sql, [1])


class TestCFSQLCompiler:
    """Tests for the CFSQLCompiler class."""

    def test_replace_date_trunc_functions_year(self):
        """Test _replace_date_trunc_functions for year truncation."""
        from django_cf.db.base_engine import CFSQLCompiler

        compiler = CFSQLCompiler.__new__(CFSQLCompiler)

        sql = "SELECT django_date_trunc('year', created_at) FROM orders"
        result = compiler._replace_date_trunc_functions(sql)

        assert 'STRFTIME("%Y-01-01", created_at)' in result
        assert 'django_date_trunc' not in result

    def test_replace_date_trunc_functions_month(self):
        """Test _replace_date_trunc_functions for month truncation."""
        from django_cf.db.base_engine import CFSQLCompiler

        compiler = CFSQLCompiler.__new__(CFSQLCompiler)

        sql = "SELECT django_date_trunc('month', created_at) FROM orders"
        result = compiler._replace_date_trunc_functions(sql)

        assert 'STRFTIME("%Y-%m-01", created_at)' in result

    def test_replace_date_trunc_functions_day(self):
        """Test _replace_date_trunc_functions for day truncation."""
        from django_cf.db.base_engine import CFSQLCompiler

        compiler = CFSQLCompiler.__new__(CFSQLCompiler)

        sql = "SELECT django_date_trunc('day', created_at) FROM orders"
        result = compiler._replace_date_trunc_functions(sql)

        assert 'DATE(created_at)' in result

    def test_replace_date_trunc_functions_hour(self):
        """Test _replace_date_trunc_functions for hour truncation."""
        from django_cf.db.base_engine import CFSQLCompiler

        compiler = CFSQLCompiler.__new__(CFSQLCompiler)

        sql = "SELECT django_date_trunc('hour', created_at) FROM orders"
        result = compiler._replace_date_trunc_functions(sql)

        assert 'STRFTIME("%Y-%m-%d %H:00:00", created_at)' in result

    def test_replace_date_trunc_functions_unknown_kind(self):
        """Test _replace_date_trunc_functions with unknown kind returns original."""
        from django_cf.db.base_engine import CFSQLCompiler

        compiler = CFSQLCompiler.__new__(CFSQLCompiler)

        sql = "SELECT django_date_trunc('unknown', created_at) FROM orders"
        result = compiler._replace_date_trunc_functions(sql)

        # Unknown kind should leave the original match
        assert "django_date_trunc('unknown', created_at)" in result
