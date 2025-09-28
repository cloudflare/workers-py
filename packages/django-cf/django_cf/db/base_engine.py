import sqlparse
from django.db import DatabaseError, Error, DataError, OperationalError, \
    IntegrityError, InternalError, ProgrammingError, NotSupportedError, InterfaceError
from django.db.backends.sqlite3.base import DatabaseWrapper as SQLiteDatabaseWrapper
from django.db.backends.sqlite3.client import DatabaseClient as SQLiteDatabaseClient
from django.db.backends.sqlite3.creation import DatabaseCreation as SQLiteDatabaseCreation
from django.db.backends.sqlite3.features import DatabaseFeatures as SQLiteDatabaseFeatures
from django.db.backends.sqlite3.introspection import DatabaseIntrospection as SQLiteDatabaseIntrospection
from django.db.backends.sqlite3.operations import DatabaseOperations as SQLiteDatabaseOperations
from django.db.backends.sqlite3.schema import DatabaseSchemaEditor as SQLiteDatabaseSchemaEditor


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
                chunk = params[index: index + BATCH_SIZE]
                results += self._quote_params_for_last_executed_query(chunk)
            return results

        sql = "SELECT " + ", ".join(["QUOTE(?)"] * len(params))
        # Bypass Django's wrappers and use the underlying sqlite3 connection
        # to avoid logging this query - it would trigger infinite recursion.

        cursor = self.connection.connection.cursor()
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
            except:
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
    can_clone_databases = False
    can_rollback_ddl = False
    supports_atomic_references_rename = False
    supports_forward_references = False
    supports_transactions = False
    has_bulk_insert = True
    # supports_select_union = False
    # supports_select_intersection = False
    # supports_select_difference = False
    can_return_columns_from_insert = True

    minimum_database_version = (4,)


class D1Result:
    lastrowid = None
    rowcount = -1

    def __init__(self, data):
        self.data = data

    def __iter__(self):
        return iter(self.data)

    def set_lastrowid(self, value):
        self.lastrowid = value

    def set_rowcount(self, value):
        self.rowcount = value

    @staticmethod
    def from_dict(data):
        result = []

        for row in data:
            row_items = ()
            for k, v in row.items():
                row_items += (v,)

            result.append(row_items)

        return D1Result(result)


class CFDatabase:
    def __init__(self, binding):
        self.binding = binding

        try:
            from workers import import_from_javascript
            from pyodide.ffi import run_sync
            self.import_from_javascript = import_from_javascript
            self.run_sync = run_sync
        except ImportError as e:
            print(e)
            raise Exception("Code not running inside a worker, please change to django_cf.d1_api database backend")

    DataError = DataError

    OperationalError = OperationalError

    IntegrityError = IntegrityError

    InternalError = InternalError

    ProgrammingError = ProgrammingError

    NotSupportedError = NotSupportedError
    DatabaseError = DatabaseError
    InterfaceError = InterfaceError
    Error = Error

    lastrowid = None

    def set_lastrowid(self, value):
        self.lastrowid = value

    rowcount = None

    def set_rowcount(self, value):
        self.rowcount = value

    _defer_foreign_keys = False

    def defer_foreign_keys(self, state):
        _defer_foreign_keys = state

    @staticmethod
    def connect(binding):
        return CFDatabase(binding)

    def cursor(self):
        return self

    def commit(self):
        return  # No commits allowed

    def rollback(self):
        return  # No commits allowed

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

        if self._defer_foreign_keys:
            return f'''
            PRAGMA defer_foreign_keys = on

            {query}

            PRAGMA defer_foreign_keys = off
            '''

        return query, params

    def run_query(self, query, params=None):
        proc_query, params = self.process_query(query, params)

        cf_workers = self.import_from_javascript("cloudflare:workers")
        db = getattr(cf_workers.env, self.binding)

        if params:
            stmt = db.prepare(proc_query).bind(*params);
        else:
            stmt = db.prepare(proc_query);

        read_only = is_read_only_query(proc_query)
        print('----')
        print(proc_query)
        try:
            print(0)
            if read_only:
                resp = self.run_sync(stmt.raw())
                print(1)
                print(resp)
            else:
                resp = self.run_sync(stmt.all())
                print(2)
                print(resp)
        except:
            from js import Error
            Error.stackTraceLimit = 1e10
            raise Error(Error.new().stack)

        # this is a hack, because D1 Raw method (required for reading rows) doesn't return metadata
        if read_only:
            results = self._convert_results_list(resp.to_py())
            rows_read = len(results)
            rows_written = 0
        else:
            results = self._convert_results_dict(resp.results.to_py())
            rows_read = resp.meta.rows_read
            rows_written = resp.meta.rows_written
        print(results)

        return results, {
            "rows_read": rows_read,
            "rows_written": rows_written,
        }

    def _convert_results_dict(self, data):
        from pyodide.ffi import jsnull
        print(jsnull)
        print(dir(jsnull))
        result = []

        for row in data:
            row_items = ()
            for k, v in row.items():
                if v is jsnull:
                    print(3)
                    row_items += (None,)
                else:
                    row_items += (v,)

            result.append(row_items)

        return result

    def _convert_results_list(self, data):
        from pyodide.ffi import jsnull
        print(jsnull)
        print(dir(jsnull))
        result = []

        for row in data:
            row_items = ()
            for v in row:
                if v is jsnull:
                    print(3)
                    row_items += (None,)
                else:
                    row_items += (v,)

            result.append(row_items)

        return result

    query = None
    params = None

    def execute(self, query, params=None):
        if params:
            newParams = []
            for v in list(params):
                if v is True:
                    v = 1
                elif v is False:
                    v = 0

                newParams.append(v)

            params = tuple(newParams)

        result, meta = self.run_query(query, params)

        self.results = result

        if meta:
            if "INSERT" in query.upper():
                self.rowcount = meta.get("rows_written", 0)
                # self.connection.ops.last_insert_id = meta.get("last_insert_id")  # TODO: implement last insert id
            elif "UPDATE" in query.upper() or "DELETE" in query.upper():
                self.rowcount = meta.get("rows_written", 0)
            else:
                self.rowcount = meta.get("rows_read", 0)

        return self

    def fetchone(self):
        if len(self.results) > 0:
            return self.results.pop()
        return None

    def fetchall(self):
        ret = []
        while True:
            row = self.fetchone()
            if row is None:
                break
            ret.append(row)
        return ret

    def fetchmany(self, size=1):
        ret = []
        while size > 0:
            row = self.fetchone()
            if row is None:
                break
            ret.append(row)
            if size is not None:
                size -= 1

        return ret

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
    modifying_types = {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "REPLACE"}

    return statement.get_type().upper() not in modifying_types


class CFDatabaseWrapper(SQLiteDatabaseWrapper):
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

    def get_database_version(self):
        return (4,)

    def get_connection_params(self):
        raise NotImplementedError()

    def get_new_connection(self, conn_params):
        conn = CFDatabase.connect(**conn_params)
        return conn

    def create_cursor(self, name=None):
        return self.connection.cursor()

    def close(self):
        return

    def _savepoint_allowed(self):
        return False

    def _set_autocommit(self, commit):
        return

    def set_autocommit(
            self, autocommit, force_begin_transaction_with_broken_autocommit=False
    ):
        return

    def disable_constraint_checking(self):
        self.cursor().defer_foreign_keys(False)
        return True

    def enable_constraint_checking(self):
        self.cursor().defer_foreign_keys(True)

    def is_usable(self):
        return True
