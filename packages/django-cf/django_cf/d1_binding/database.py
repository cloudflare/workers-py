import json
import http.client
import datetime
import re

from django.db import DatabaseError, Error, DataError, OperationalError, \
IntegrityError, InternalError, ProgrammingError, NotSupportedError, InterfaceError
from django.conf import settings
from django.utils import timezone

try:
    from workers import import_from_javascript
    from pyodide.ffi import run_sync
except ImportError:
    raise Exception("Code not running inside a worker, please change to django_cf.d1_api database backend")

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


class D1Database:
    def __init__(self, database_id, account_id, token):
        self.database_id = database_id
        self.account_id = account_id
        self.token = token

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
    def connect(database_id, account_id, token):
        return D1Database(database_id, account_id, token)

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

        print(query)
        print(params)

        cf_workers = import_from_javascript("cloudflare:workers")
        # print(dir(cf_workers))
        db = cf_workers.env.DB

        if params:
            stmt = db.prepare(proc_query).bind(*params);
        else:
            stmt = db.prepare(proc_query);

        try:
            resp = run_sync(stmt.all())
        except:
            from js import Error
            Error.stackTraceLimit = 1e10
            raise Error(Error.new().stack)

        results = self._convert_results(resp.results.to_py())

        # print(results)
        # print(f'rowsRead: {resp.meta.rows_read}')
        # print(f'rowsWritten: {resp.meta.rows_written}')
        # print('---')

        return results, {
            "rows_read": resp.meta.rows_read,
            "rows_written": resp.meta.rows_written,
        }

    def _convert_results(self, data):
        """
        Convert any datetime strings in the result set to actual timezone-aware datetime objects.
        """
        print('before')
        print(data)
        result = []

        for row in data:
            row_items = ()
            for k, v in row.items():
                if isinstance(v, str):
                    v = self._parse_datetime(v)
                row_items += (v,)

            result.append(row_items)

        print('after')
        print(result)
        return result

    query = None
    params = None

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
