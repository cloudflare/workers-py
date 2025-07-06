import sqlparse

from django.db import DatabaseError, Error, DataError, OperationalError, \
IntegrityError, InternalError, ProgrammingError, NotSupportedError, InterfaceError

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
    def __init__(self, binding):
        self.binding = binding

        try:
            from workers import import_from_javascript
            from pyodide.ffi import run_sync
            self.import_from_javascript = import_from_javascript
            self.run_sync = run_sync
        except ImportError:
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
        return D1Database(binding)

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

        try:
            if read_only:
                resp = self.run_sync(stmt.raw())
            else:
                resp = self.run_sync(stmt.all())
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

        return results, {
            "rows_read": rows_read,
            "rows_written": rows_written,
        }

    def _convert_results_dict(self, data):
        result = []

        for row in data:
            row_items = ()
            for k, v in row.items():
                row_items += (v,)

            result.append(row_items)

        return result

    def _convert_results_list(self, data):
        result = []

        for row in data:
            row_items = ()
            for v in row:
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
