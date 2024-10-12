import datetime
import hashlib
import json

import sqlparse
import websocket  # Using websocket-client library for synchronous operations
from django.conf import settings
from django.db import IntegrityError, DatabaseError
from django.db.backends.sqlite3.base import DatabaseWrapper as SQLiteDatabaseWrapper
from django.db.backends.sqlite3.client import DatabaseClient as SQLiteDatabaseClient
from django.db.backends.sqlite3.creation import DatabaseCreation as SQLiteDatabaseCreation
from django.db.backends.sqlite3.features import DatabaseFeatures as SQLiteDatabaseFeatures
from django.db.backends.sqlite3.introspection import DatabaseIntrospection as SQLiteDatabaseIntrospection
from django.db.backends.sqlite3.operations import DatabaseOperations as SQLiteDatabaseOperations
from django.db.backends.sqlite3.schema import DatabaseSchemaEditor as SQLiteDatabaseSchemaEditor
from django.utils import timezone
from sqlparse.sql import IdentifierList, Identifier
from sqlparse.tokens import DML
from django.core.cache import cache


class DatabaseFeatures(SQLiteDatabaseFeatures):
    supports_transactions = True
    supports_savepoints = False
    max_query_params = 100


class DatabaseOperations(SQLiteDatabaseOperations):
    pragma_foreign_keys = None

    def _quote_columns(self, sql):
        """
        Ensure column names are properly quoted and aliased to avoid collisions.
        """
        parsed = sqlparse.parse(sql)
        if not parsed:
            return sql  # Unable to parse, return original SQL

        stmt = parsed[0]
        new_tokens = []
        select_seen = False

        for token in stmt.tokens:
            if token.ttype is DML and token.value.upper() == 'SELECT':
                select_seen = True
                new_tokens.append(token)
            elif select_seen:
                if isinstance(token, IdentifierList):
                    # Process each identifier in the SELECT clause
                    new_identifiers = []
                    for identifier in token.get_identifiers():
                        new_identifiers.append(self._process_identifier(identifier))
                    # Rebuild the IdentifierList
                    new_token = IdentifierList(new_identifiers)
                    new_tokens.append(new_token)
                elif isinstance(token, Identifier):
                    # Single column without commas
                    new_token = self._process_identifier(token)
                    new_tokens.append(new_token)
                else:
                    new_tokens.append(token)
                select_seen = False  # Assuming SELECT clause is only once
            else:
                new_tokens.append(token)

        # Reconstruct the SQL statement
        new_sql = ''.join(str(token) for token in new_tokens)
        return new_sql

    def _process_identifier(self, identifier):
        # Get the real name and alias if present
        real_name = identifier.get_real_name()
        alias = identifier.get_alias()
        parent_name = identifier.get_parent_name()

        if real_name:
            if parent_name:
                # Format: table.column
                table = self.quote_name(parent_name)
                column = self.quote_name(real_name)
                new_alias = f"{parent_name}_{real_name}"
                return f"{table}.{column} AS {new_alias}"
            else:
                # Simple column
                column = self.quote_name(real_name)
                new_alias = real_name
                return f"{column} AS {new_alias}"
        else:
            # Complex expression (e.g., functions), return as is
            return str(identifier)

    def _format_params(self, sql, params):
        def quote_param(param):
            if isinstance(param, str):
                return f'{param}'
            if isinstance(param, datetime.datetime):
                return f'{param.strftime("%Y-%m-%d %H:%M:%S")}'
            elif param is None:
                return None
            elif param is True:
                return 1
            elif param is False:
                return 0
            return str(param)

        sql = sql.replace('%s', '?')
        new_params = []
        for param in params:
            new_params.append(quote_param(param))

        return sql, new_params

    def _parse_datetime(self, value):
        """
        Parse the string value to a timezone-aware datetime object, if applicable.
        Handles both datetime strings with and without milliseconds.
        Uses Django's timezone utilities for proper conversion.
        """
        datetime_formats = ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"]

        for dt_format in datetime_formats:
            try:
                naive_dt = datetime.datetime.strptime(value, dt_format)
                # If Django is using timezones, convert to an aware datetime object
                if timezone.is_naive(naive_dt):
                    return timezone.make_aware(naive_dt, timezone.get_default_timezone())
                return naive_dt
            except (ValueError, TypeError):
                continue  # Try the next format if parsing fails

        return value  # If it's not a datetime string, return the original value

    def _convert_results(self, results):
        """
        Convert any datetime strings in the result set to actual timezone-aware datetime objects.
        """
        converted_results = []
        for row in results:
            converted_row = []
            for value in row:
                if isinstance(value, str):
                    value = self._parse_datetime(value)
                converted_row.append(value)
            converted_results.append(tuple(converted_row))
        return converted_results

    def generate_cache_key(self, sql_query: str) -> str:
        # Create a SHA256 hash of the combined string
        hash_object = hashlib.sha256(sql_query.encode())

        # Return the hexadecimal representation of the hash
        return f"workers_dbms_{hash_object.hexdigest()}"

    def raw_query(self, websocket, query, params=None):
        if params == None:
            if query.strip() == 'PRAGMA foreign_keys = OFF':
                self.pragma_foreign_keys = False
                return [[]], None
            elif query.strip() == 'PRAGMA foreign_keys = ON':
                self.pragma_foreign_keys = True
                return [[]], None
            elif query.strip() == 'PRAGMA foreign_keys':
                if self.pragma_foreign_keys is True:
                    return [[1]], None
                elif self.pragma_foreign_keys is False:
                    return [[0]], None
                else:
                    return [[]], None

        # Quote column names before execution
        sql = self._quote_columns(query)

        if self.pragma_foreign_keys is True:
            sql = f"PRAGMA foreign_keys = ON; {sql}"
        elif self.pragma_foreign_keys is False:
            sql = f"PRAGMA foreign_keys = OFF; {sql}"

        if params:
            sql, params = self._format_params(sql, params)

        socket_input = json.dumps({
            "type": "request",
            "request": {
                "type": "execute",
                "stmt": {
                    "arguments": params,
                    "query": sql
                }
            }
        })

        should_cache = False
        response = None
        if self.connection.cache is True:
            upper_query = query.upper()
            user_model = settings.AUTH_USER_MODEL.replace('.', '_').upper()
            try:
                if 'FROM "DJANGO_SESSION"' in upper_query or f'FROM "{user_model}"' in upper_query:
                    if "UPDATE" not in upper_query and "DELETE" not in upper_query and "INSERT" not in upper_query:
                        cache_key = self.generate_cache_key(socket_input)
                        response = cache.get(cache_key)

                        if not response:
                            should_cache = True
                    else:
                        pass  # TODO: clear cache
                        # cache.clear(prefix="workers_dbms_")
            except TypeError:
                pass

        if not response:
            websocket.send(socket_input)

            if self.connection.debug is True:
                print(sql)
                print(params)

            response = websocket.recv()

        parsed_response = json.loads(response)

        if parsed_response["type"] == "response_error":
            if "unique constraint failed" in parsed_response["error"].lower():
                raise IntegrityError(parsed_response["error"])

            raise DatabaseError(parsed_response["error"] + "\n" + sql)

        if self.connection.cache is True and should_cache is True:
            cache_key = self.generate_cache_key(socket_input)
            cache.set(cache_key, response, 300)

        results = self._convert_results(list(tuple(row) for row in parsed_response["result"]["results"]))
        meta = parsed_response["result"].get("meta")

        if self.connection.debug is True:
            print(results)
            print('---')

        return results, meta

    def quote_name(self, name):
        if '.' in name:
            # If it's in the form of "table.column", alias the column name to avoid collision
            table_name, column_name = name.split('.')
            return f'"{table_name}"."{column_name}" AS "{table_name}_{column_name}"'
        if name.startswith('"') and name.endswith('"'):
            return name
        return '"%s"' % name

    def get_db_converters(self, expression):
        return []  # Disable any automatic data type conversions

    def adapt_datefield_value(self, value):
        return value

    def adapt_datetimefield_value(self, value):
        return value

    def adapt_decimalfield_value(self, value, max_digits=None, decimal_places=None):
        return value

    # This patches some weird bugs related to the Database class
    def _quote_params_for_last_executed_query(self, params):
        """
        Only for last_executed_query! Don't use this to execute SQL queries!
        """
        sql, params = self._format_params("select 1", params)
        return params

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


class DatabaseWrapper(SQLiteDatabaseWrapper):
    vendor = 'websocket'
    debug = False
    cache = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.features = DatabaseFeatures(self)
        self.ops = DatabaseOperations(self)
        self.client = SQLiteDatabaseClient(self)
        self.creation = SQLiteDatabaseCreation(self)
        self.introspection = SQLiteDatabaseIntrospection(self)
        self._websocket = None

    def get_connection_params(self):
        settings_dict = self.settings_dict
        if not settings_dict['WORKERS_DBMS_ENDPOINT']:
            raise ValueError("Please specify WORKERS_DBMS_ENDPOINT in database settings")
        return {
            'endpoint_url': settings_dict['WORKERS_DBMS_ENDPOINT'],
            'access_id': settings_dict.get('WORKERS_DBMS_ACCESS_ID'),
            'access_secret': settings_dict.get('WORKERS_DBMS_ACCESS_SECRET'),
            'cache': settings_dict.get('WORKERS_DBMS_CACHE', True),
            'debug': settings_dict.get('WORKERS_DBMS_DEBUG'),
        }

    def get_new_connection(self, conn_params):
        headers = []
        if conn_params['cache']:
            self.cache = conn_params['cache']
        if conn_params['debug']:
            self.debug = conn_params['debug'] is True

        if conn_params['access_id'] and conn_params['access_secret']:
            headers = [
                f"CF-Access-Client-Id: {conn_params['access_id']}",
                f"CF-Access-Client-Secret: {conn_params['access_secret']}"
            ]

        try:
            self._websocket = websocket.create_connection(
                url=conn_params['endpoint_url'],
                header=headers
            )
        except Exception as e:
            raise ValueError(
                "Unable to connect to websocket, please check your credentials and make sure you have websockets enabled in your domain")

        return self._websocket

    def init_connection_state(self):
        pass  # No initialization needed for WebSocket

    def create_cursor(self, name=None):
        return WebSocketCursor(self._websocket, self.ops)

    def is_usable(self):
        return self._websocket and self._websocket.connected

    def close(self):
        if self._websocket:
            self._websocket.close()
        super().close()

    def _savepoint_allowed(self):
        return False

    def _start_transaction_under_autocommit(self):
        if self.connection is not None:
            with self.wrap_database_errors:
                self.ops.raw_query(self._websocket, "begin;")

    def _commit(self):
        if self.connection is not None:
            with self.wrap_database_errors:
                self.ops.raw_query(self._websocket, "commit;")

    def _rollback(self):
        if self.connection is not None:
            with self.wrap_database_errors:
                self.ops.raw_query(self._websocket, "rollback;")


class WebSocketCursor:
    def __init__(self, websocket, ops):
        self.websocket = websocket
        self.ops = ops
        self.results = None
        self._arraysize = 1  # Default arraysize

    def close(self):
        pass
        # self.websocket.close()

    def execute(self, sql, params=None):
        try:
            result, meta = self.ops.raw_query(self.websocket, sql, params)

            self.results = result

            # Update rowcount based on the operation type
            if meta:
                if "INSERT" in sql.upper():
                    self.rowcount = meta.get("rows_written", 0)
                    # self.connection.ops.last_insert_id = meta.get("last_insert_id")  # TODO: implement last insert id
                elif "UPDATE" in sql.upper() or "DELETE" in sql.upper():
                    self.rowcount = meta.get("rows_written", 0)
                else:
                    self.rowcount = meta.get("rows_read", 0)
        except Exception as e:
            self.results = []
            raise DatabaseError(str(e))

        return self

    def fetchone(self):
        if self.results and len(self.results) > 0:
            return self.results.pop(0)
        return None

    def fetchmany(self, size=None):
        if not self.results:
            return []
        if size is None:
            size = self._arraysize
        result = self.results[:size]
        self.results = self.results[size:]
        return result

    def fetchall(self):
        if self.results:
            results = self.results
            self.results = []  # Clear the results after fetching
            return results
        return []

    def __iter__(self):
        while self.results:
            yield self.fetchone()

    @property
    def rowcount(self):
        return self._rowcount

    @rowcount.setter
    def rowcount(self, value):
        if not isinstance(value, int) or value < 0:
            raise ValueError("rowcount must be a positive integer")
        self._rowcount = value

    @property
    def arraysize(self):
        return self._arraysize

    @arraysize.setter
    def arraysize(self, value):
        if not isinstance(value, int) or value <= 0:
            raise ValueError("arraysize must be a positive integer")
        self._arraysize = value


class DatabaseSchemaEditor(SQLiteDatabaseSchemaEditor):
    def _remake_table(self, model, create_field=None, delete_field=None, alter_fields=None):
        """
        Overrides the SQLite _remake_table method to use WebSocket communication instead of direct SQLite operations.
        """
        # Generate the SQL for creating a new table
        new_model = model._meta.clone()
        current_table_name = model._meta.db_table
        new_table_name = self.connection.ops.quote_name(f"new__{current_table_name}")

        # Create the new table
        create_table_sql = self.sql_create_table % {
            "table": new_table_name,
            "definition": self.connection.ops.table_definition(new_model),
        }
        self.execute(create_table_sql)

        # Copy data from the old table to the new one
        copy_sql = f"INSERT INTO {new_table_name} SELECT * FROM {current_table_name}"
        self.execute(copy_sql)

        # Drop the old table
        self.execute(f"DROP TABLE {current_table_name}")

        # Rename the new table to the original name
        self.execute(f"ALTER TABLE {new_table_name} RENAME TO {current_table_name}")

    def alter_db_table(self, model, old_db_table, new_db_table):
        if old_db_table == new_db_table:
            return
        self.execute(f"ALTER TABLE {self.quote_name(old_db_table)} RENAME TO {self.quote_name(new_db_table)}")
