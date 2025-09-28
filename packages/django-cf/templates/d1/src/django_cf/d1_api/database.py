import json
import http.client

from django.db import DatabaseError, Error, DataError, OperationalError, \
IntegrityError, InternalError, ProgrammingError, NotSupportedError, InterfaceError

def retry(times, exceptions):
    """
    Retry Decorator
    Retries the wrapped function/method `times` times if the exceptions listed
    in ``exceptions`` are thrown
    :param times: The number of times to repeat the wrapped function/method
    :type times: Int
    :param Exceptions: Lists of exceptions that trigger a retry attempt
    :type Exceptions: Tuple of Exceptions
    """
    def decorator(func):
        def newfn(*args, **kwargs):
            attempt = 0
            while attempt < times:
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    print(
                        'Exception thrown when attempting to run %s, attempt '
                        '%d of %d' % (func, attempt, times)
                    )
                    attempt += 1
            return func(*args, **kwargs)
        return newfn
    return decorator

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

    def process_query(self, query):
        query = query.replace('%s', '?')

        if self._defer_foreign_keys:
            return f'''
            PRAGMA defer_foreign_keys = on
            
            {query}

            PRAGMA defer_foreign_keys = off
            '''

        return query

    @retry(times=3, exceptions=(InternalError,))
    def run_query(self, query, params=None):
        proc_query = self.process_query(query)

        conn = http.client.HTTPSConnection("api.cloudflare.com", timeout=20.0)

        payload = {
            "params": params,
            "sql": proc_query
        }

        headers = {
            'Content-Type': "application/json",
            'Authorization': f"Bearer {self.token}"
        }

        conn.request("POST", f"/client/v4/accounts/{self.account_id}/d1/database/{self.database_id}/query", json.dumps(payload), headers)

        res = conn.getresponse()
        data = res.read()

        decoded = data.decode("utf-8")
        try:
            response = json.loads(decoded)
        except:
            # Couldn't parse the json, probably an internal error
            raise InternalError(decoded)

        if response["success"] == False:
            errorMsg = response["errors"][0]["message"]
            if "unique constraint failed" in errorMsg.lower():
                raise IntegrityError(errorMsg)

            raise DatabaseError(errorMsg)

        query_result = response["result"][0]
        if query_result["success"] == False:
            raise DatabaseError(query_result)

        result = D1Result.from_dict(query_result["results"])

        meta = query_result.get("meta")
        if query_result["meta"]:
            if meta["last_row_id"]:
                result.set_lastrowid(meta["last_row_id"])
                self.set_lastrowid(meta["last_row_id"])

            if meta["rows_read"] or meta["rows_written"]:
                result.set_rowcount(meta.get("rows_read", 0) + meta.get("rows_read", 0))
                self.set_rowcount(meta.get("rows_read", 0) + meta.get("rows_read", 0))

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

        self.results = self.run_query(query, params)

        return self

    def fetchone(self):
        if len(self.results.data) > 0:
            return self.results.data.pop()
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
