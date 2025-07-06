from django.db import DatabaseError, Error, DataError, OperationalError, \
    IntegrityError, InternalError, ProgrammingError, NotSupportedError, InterfaceError

from .storage import get_storage


class DOResult:
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

        return DOResult(result)


class DODatabase:
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
    def connect():
        return DODatabase()

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

        db = get_storage()

        if params:
            stmt = db.exec(proc_query, *params);
        else:
            stmt = db.exec(proc_query);

        try:
            resp = stmt.raw().toArray()
        except:
            from js import Error
            Error.stackTraceLimit = 1e10
            raise Error(Error.new().stack)

        results = self._convert_results(resp.to_py())

        return results, {
            "rows_read": stmt.rowsRead,
            "rows_written": stmt.rowsWritten,
        }

    def _convert_results(self, data):
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
