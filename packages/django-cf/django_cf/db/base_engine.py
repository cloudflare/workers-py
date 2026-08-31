import re

import sqlparse
from django.db import (
    DatabaseError,
    DataError,
    Error,
    IntegrityError,
    InterfaceError,
    InternalError,
    NotSupportedError,
    OperationalError,
    ProgrammingError,
)
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.sqlite3.base import DatabaseWrapper as SQLiteDatabaseWrapper
from django.db.backends.sqlite3.client import DatabaseClient as SQLiteDatabaseClient
from django.db.backends.sqlite3.creation import (
    DatabaseCreation as SQLiteDatabaseCreation,
)
from django.db.backends.sqlite3.features import (
    DatabaseFeatures as SQLiteDatabaseFeatures,
)
from django.db.backends.sqlite3.introspection import (
    DatabaseIntrospection as SQLiteDatabaseIntrospection,
)
from django.db.backends.sqlite3.operations import (
    DatabaseOperations as SQLiteDatabaseOperations,
)
from django.db.backends.sqlite3.schema import (
    DatabaseSchemaEditor as SQLiteDatabaseSchemaEditor,
)
from django.db.models.functions import (
    TruncDate,
    TruncDay,
    TruncHour,
    TruncMinute,
    TruncMonth,
    TruncQuarter,
    TruncSecond,
    TruncTime,
    TruncWeek,
    TruncYear,
)
from django.db.models.sql.compiler import SQLCompiler

from ._async_unsafe import _unwrap_async_unsafe


def replace_date_trunc_in_sql(sql):
    """Replace django_date_trunc and django_datetime_trunc function calls with SQLite equivalents."""
    if "django_date_trunc" not in sql and "django_datetime_trunc" not in sql:
        return sql

    # Pattern to match django_datetime_trunc(%s, field, %s, %s) or django_date_trunc(%s, field, %s, %s)
    # The kind is passed as a parameter (%s), so we need to replace the entire function call
    # with a CASE statement that handles all possible kinds
    pattern = r"django_(?:date|datetime)_trunc\(%s,\s*([^,]+),\s*%s,\s*%s\)"

    def replace_func(match):
        field = match.group(1).strip()

        # Since the kind is a parameter, we need to use a CASE statement
        # that handles all truncation types
        replacement = (
            f"CASE %s "
            f"WHEN 'year' THEN STRFTIME('%Y-01-01', {field}) "
            f"WHEN 'quarter' THEN CASE ((CAST(STRFTIME('%m', {field}) AS INTEGER) - 1) / 3 + 1) "
            f"  WHEN 1 THEN STRFTIME('%Y-01-01', {field}) "
            f"  WHEN 2 THEN STRFTIME('%Y-04-01', {field}) "
            f"  WHEN 3 THEN STRFTIME('%Y-07-01', {field}) "
            f"  WHEN 4 THEN STRFTIME('%Y-10-01', {field}) END "
            f"WHEN 'month' THEN STRFTIME('%Y-%m-01', {field}) "
            f"WHEN 'week' THEN DATE({field}, '-' || CAST((CAST(STRFTIME('%w', {field}) AS INTEGER) + 6) % 7 AS TEXT) || ' days') "
            f"WHEN 'day' THEN DATE({field}) "
            f"WHEN 'hour' THEN STRFTIME('%Y-%m-%d %H:00:00', {field}) "
            f"WHEN 'minute' THEN STRFTIME('%Y-%m-%d %H:%M:00', {field}) "
            f"WHEN 'second' THEN STRFTIME('%Y-%m-%d %H:%M:%S', {field}) "
            f"WHEN 'date' THEN DATE({field}) "
            f"WHEN 'time' THEN TIME({field}) "
            f"END"
        )
        return replacement

    return re.sub(pattern, replace_func, sql)


class CFDatabaseIntrospection(SQLiteDatabaseIntrospection):
    pass


class CFDatabaseCreation(SQLiteDatabaseCreation):
    pass


class CFDatabaseClient(SQLiteDatabaseClient):
    pass


class CFDatabaseSchemaEditor(SQLiteDatabaseSchemaEditor):
    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            for sql in self.deferred_sql:
                self.execute(sql)
        if self.atomic_migration:
            self.atomic.__exit__(exc_type, exc_value, traceback)


class CFDatabaseOperations(SQLiteDatabaseOperations):
    pass

    # This patches some weird bugs related to the Database class
    def _quote_params_for_last_executed_query(self, params):
        """
        Only for last_executed_query! Don't use this to execute SQL queries!
        """
        # This function is limited both by SQLITE_LIMIT_VARIABLE_NUMBER (the
        # number of parameters, default = 999) and SQLITE_MAX_COLUMN (the
        # number of return values, default = 2000). Since Python's sqlite3
        # module doesn't expose the get_limit() C API, assume the default
        # limits are in effect and split the work in batches if needed.
        BATCH_SIZE = 999
        if len(params) > BATCH_SIZE:
            results = ()
            for index in range(0, len(params), BATCH_SIZE):
                chunk = params[index : index + BATCH_SIZE]
                results += self._quote_params_for_last_executed_query(chunk)
            return results

        # Both locals below are unused because the `return` that consumed them is
        # commented out, so this function falls through and returns None. Left in
        # place rather than deleted so the intended implementation stays visible.
        sql = "SELECT " + ", ".join(["QUOTE(?)"] * len(params))  # noqa: F841
        # Bypass Django's wrappers and use the underlying sqlite3 connection
        # to avoid logging this query - it would trigger infinite recursion.

        cursor = self.connection.connection.cursor()  # noqa: F841
        # Native sqlite3 cursors cannot be used as context managers.
        # try:
        #     return cursor.execute(sql, params).fetchone()
        # finally:
        #     cursor.close()

    def last_executed_query(self, cursor, sql, params):
        # Python substitutes parameters in Modules/_sqlite/cursor.c with:
        # bind_parameters(state, self->statement, parameters);
        # Unfortunately there is no way to reach self->statement from Python,
        # so we quote and substitute parameters manually.
        if params:
            if isinstance(params, (list, tuple)):
                params = self._quote_params_for_last_executed_query(params)
            else:
                values = tuple(params.values())
                values = self._quote_params_for_last_executed_query(values)
                params = dict(zip(params, values))
            try:
                return sql % params
            except Exception:
                return sql
        # For consistency with SQLiteCursorWrapper.execute(), just return sql
        # when there are no parameters. See #13648 and #17158.
        else:
            return sql

    def bulk_insert_sql(self, fields, placeholder_rows):
        placeholder_rows_sql = (", ".join(row) for row in placeholder_rows)
        values_sql = ", ".join("(%s)" % sql for sql in placeholder_rows_sql)
        return "VALUES " + values_sql


class CFDatabaseFeatures(SQLiteDatabaseFeatures):
    has_select_for_update = True
    has_native_uuid_field = False
    atomic_transactions = False
    supports_transactions = False
    uses_savepoints = False  # No savepoint support in Cloudflare D1
    can_release_savepoints = False
    supports_atomic_references_rename = False
    can_clone_databases = False
    can_rollback_ddl = False
    # Unsupported add column and foreign key in single statement
    # https://github.com/pingcap/tidb/issues/45474
    can_create_inline_fk = False
    order_by_nulls_first = True
    create_test_procedure_without_params_sql = None
    create_test_procedure_with_int_param_sql = None
    supports_aggregate_filter_clause = True
    can_defer_constraint_checks = False
    supports_pragma_foreign_key_check = False
    can_alter_table_rename_column = False
    max_query_params = 100
    supports_forward_references = False
    has_bulk_insert = True
    # supports_select_union = False
    # supports_select_intersection = False
    # supports_select_difference = False
    can_return_columns_from_insert = True

    minimum_database_version = (4,)


class CFResult:
    lastrowid = None
    rowcount = -1

    def __init__(self, data):
        self.data = data
        self._position = 0

    def __iter__(self):
        return iter(self.data)

    def set_lastrowid(self, value):
        self.lastrowid = value

    def set_rowcount(self, value):
        self.rowcount = value

    def fetchone(self):
        if self._position < len(self.data):
            row = self.data[self._position]
            self._position += 1
            return row
        return None

    def fetchall(self):
        ret = self.data[self._position :]
        self._position = len(self.data)
        return ret

    def fetchmany(self, size=1):
        if size <= 0:
            return []
        end = min(self._position + size, len(self.data))
        ret = self.data[self._position : end]
        self._position = end
        return ret

    @staticmethod
    def from_object(
        query, params, data, rows_read=None, rows_written=None, last_row_id=None
    ):
        try:
            from pyodide.ffi import jsnull
        except ImportError:
            jsnull = None

        result = []

        for row in data:
            row_items = ()
            if isinstance(row, list):
                for v in row:
                    if v is jsnull:
                        row_items += (None,)
                    else:
                        row_items += (v,)
            else:
                for v in row.values():
                    if v is jsnull:
                        row_items += (None,)
                    else:
                        row_items += (v,)

            result.append(row_items)

        instance = CFResult(result)

        if rows_read or rows_written:
            if "INSERT" in query.upper():
                instance.set_rowcount(rows_written or 0)
            elif "UPDATE" in query.upper() or "DELETE" in query.upper():
                instance.set_rowcount(rows_written or 0)
            else:
                instance.set_rowcount(rows_read or 0)

        if last_row_id is not None:
            instance.set_lastrowid(last_row_id)

        return instance


class CFCursor:
    def __init__(self, database):
        self.database = database
        self.lastResult: CFResult | None = None

    @property
    def _defer_foreign_keys(self):
        return self.database._defer_foreign_keys

    def defer_foreign_keys(self, state):
        self.database.defer_foreign_keys(state)

    def fetchone(self):
        return self.lastResult.fetchone()

    def fetchall(self):
        return self.lastResult.fetchall()

    def fetchmany(self, size=1):
        return self.lastResult.fetchmany(size)

    @property
    def lastrowid(self):
        return self.lastResult.lastrowid

    @property
    def rowcount(self):
        return self.lastResult.rowcount

    def execute(self, query, params=None):
        from decimal import Decimal

        # Transform django_date_trunc function calls to SQLite equivalents
        query = replace_date_trunc_in_sql(query)

        if params:
            newParams = []
            for v in list(params):
                if v is True:
                    v = 1
                elif v is False:
                    v = 0
                elif isinstance(v, Decimal):
                    v = str(v)

                newParams.append(v)

            params = tuple(newParams)

        self.lastResult = self.database.databaseWrapper.run_query(query, params)

        return self

    def close(self):
        return


class CFDatabase:
    def __init__(self, database_wrapper):
        self.databaseWrapper = database_wrapper

    DataError = DataError

    OperationalError = OperationalError

    IntegrityError = IntegrityError

    InternalError = InternalError

    ProgrammingError = ProgrammingError

    NotSupportedError = NotSupportedError
    DatabaseError = DatabaseError
    InterfaceError = InterfaceError
    Error = Error

    _defer_foreign_keys = False

    def defer_foreign_keys(self, state):
        self._defer_foreign_keys = state

    @staticmethod
    def connect(binding):
        return CFDatabase(binding)

    def cursor(self):
        return CFCursor(self)

    def commit(self):
        return  # No commits allowed

    def rollback(self):
        return  # No commits allowed

    def close(self):
        return


def is_read_only_query(query: str) -> bool:
    parsed = sqlparse.parse(query.strip())

    if not parsed:
        return False  # Invalid or empty query

    # Get the first statement
    statement = parsed[0]

    # Check if the statement is a SELECT query
    if statement.get_type().upper() == "SELECT":
        return True

    # List of modifying query types
    modifying_types = {
        "INSERT",
        "UPDATE",
        "DELETE",
        "CREATE",
        "ALTER",
        "DROP",
        "REPLACE",
    }

    return statement.get_type().upper() not in modifying_types


class CFSQLCompiler(SQLCompiler):
    def as_sql(self, with_limits=True, with_col_aliases=False):
        sql, params = super().as_sql(
            with_limits=with_limits, with_col_aliases=with_col_aliases
        )
        # Post-process the SQL to replace django_date_trunc calls with proper SQLite functions
        sql = self._replace_date_trunc_functions(sql)
        return sql, params

    def _replace_date_trunc_functions(self, sql):
        """Replace django_date_trunc function calls with SQLite equivalents."""

        # Pattern to match django_date_trunc('kind', field_name)
        pattern = r"django_date_trunc\('(\w+)',\s*([^)]+)\)"

        def replace_func(match):
            kind = match.group(1)
            field = match.group(2)

            templates = {
                "year": f'STRFTIME("%Y-01-01", {field})',
                "quarter": f'CASE ((CAST(STRFTIME("%m", {field}) AS INTEGER) - 1) / 3 + 1) WHEN 1 THEN STRFTIME("%Y-01-01", {field}) WHEN 2 THEN STRFTIME("%Y-04-01", {field}) WHEN 3 THEN STRFTIME("%Y-07-01", {field}) WHEN 4 THEN STRFTIME("%Y-10-01", {field}) END',
                "month": f'STRFTIME("%Y-%m-01", {field})',
                "week": f'DATE({field}, "-" || CAST((CAST(STRFTIME("%w", {field}) AS INTEGER) + 6) % 7 AS TEXT) || " days")',
                "day": f"DATE({field})",
                "hour": f'STRFTIME("%Y-%m-%d %H:00:00", {field})',
                "minute": f'STRFTIME("%Y-%m-%d %H:%M:00", {field})',
                "second": f'STRFTIME("%Y-%m-%d %H:%M:%S", {field})',
                "date": f"DATE({field})",
                "time": f"TIME({field})",
            }

            return templates.get(kind, match.group(0))

        return re.sub(pattern, replace_func, sql)

    def compile(self, node, **extra_context):
        if isinstance(
            node,
            (
                TruncYear,
                TruncQuarter,
                TruncMonth,
                TruncWeek,
                TruncDay,
                TruncHour,
                TruncMinute,
                TruncSecond,
                TruncDate,
                TruncTime,
            ),
        ):
            return self._compile_date_trunc(node, **extra_context)
        return super().compile(node, **extra_context)

    def _compile_date_trunc(self, func, **extra_context):
        kind = func.kind
        source_expr = func.source_expressions[0]
        field_sql, params = super().compile(source_expr)

        templates = {
            "year": f'STRFTIME("%Y-01-01", {field_sql})',
            "quarter": f'CASE ((CAST(STRFTIME("%%m", {field_sql}) AS INTEGER) - 1) / 3 + 1) WHEN 1 THEN STRFTIME("%%Y-01-01", {field_sql}) WHEN 2 THEN STRFTIME("%%Y-04-01", {field_sql}) WHEN 3 THEN STRFTIME("%%Y-07-01", {field_sql}) WHEN 4 THEN STRFTIME("%%Y-10-01", {field_sql}) END',
            "month": f'STRFTIME("%Y-%m-01", {field_sql})',
            "week": f'DATE({field_sql}, "-" || CAST((CAST(STRFTIME("%w", {field_sql}) AS INTEGER) + 6) %% 7 AS TEXT) || " days")',
            "day": f"DATE({field_sql})",
            "hour": f'STRFTIME("%Y-%m-%d %H:00:00", {field_sql})',
            "minute": f'STRFTIME("%Y-%m-%d %H:%M:00", {field_sql})',
            "second": f'STRFTIME("%Y-%m-%d %H:%M:%S", {field_sql})',
            "date": f"DATE({field_sql})",
            "time": f"TIME({field_sql})",
        }

        sql = templates.get(kind, field_sql)
        return sql, params


class CFDatabaseWrapper(SQLiteDatabaseWrapper):
    # this is defined in the class extending this one
    # vendor = "cloudflare_d1"
    # display_name = "D1"

    Database = CFDatabase
    SchemaEditorClass = CFDatabaseSchemaEditor
    client_class = CFDatabaseClient
    creation_class = CFDatabaseCreation

    # Classes instantiated in __init__().
    features_class = CFDatabaseFeatures
    introspection_class = CFDatabaseIntrospection
    ops_class = CFDatabaseOperations

    transaction_modes = frozenset([])

    connect = _unwrap_async_unsafe(BaseDatabaseWrapper.connect)
    ensure_connection = _unwrap_async_unsafe(BaseDatabaseWrapper.ensure_connection)
    cursor = _unwrap_async_unsafe(BaseDatabaseWrapper.cursor)
    commit = _unwrap_async_unsafe(BaseDatabaseWrapper.commit)
    rollback = _unwrap_async_unsafe(BaseDatabaseWrapper.rollback)
    savepoint = _unwrap_async_unsafe(BaseDatabaseWrapper.savepoint)
    savepoint_rollback = _unwrap_async_unsafe(BaseDatabaseWrapper.savepoint_rollback)
    savepoint_commit = _unwrap_async_unsafe(BaseDatabaseWrapper.savepoint_commit)
    clean_savepoints = _unwrap_async_unsafe(BaseDatabaseWrapper.clean_savepoints)

    def get_compiler(self, default_using=None, using=None, **kwargs):
        if using is None:
            using = default_using
        # The query object is passed in kwargs by Django's ORM
        query = kwargs.get("query")
        return CFSQLCompiler(query, self, using, **kwargs)

    def get_database_version(self):
        return (4,)

    def get_connection_params(self):
        raise NotImplementedError()

    def get_new_connection(self, conn_params):
        conn = CFDatabase.connect(self)
        return conn

    def create_cursor(self, name=None):
        return self.connection.cursor()

    def close(self):
        return

    def _savepoint_allowed(self):
        return False

    def _set_autocommit(self, commit):
        return

    def _start_transaction_under_autocommit(self):
        # D1/DO expose no interactive transaction; inherited SQLite BEGIN must not run.
        return

    def disable_constraint_checking(self):
        self.cursor().defer_foreign_keys(False)
        return True

    def enable_constraint_checking(self):
        self.cursor().defer_foreign_keys(True)

    def is_usable(self):
        return True

    def run_query(self, query, params=None) -> CFResult:
        raise NotImplementedError()
