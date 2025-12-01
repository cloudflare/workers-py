from .storage import get_storage
from ...base_engine import CFDatabaseWrapper, CFResult


class DatabaseWrapper(CFDatabaseWrapper):
    vendor = "cloudflare_durable_objects"
    display_name = "DO"
    binding: str

    def get_connection_params(self):
        return {}


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

    def run_query(self, query, params=None) -> CFResult:
        proc_query, params = self.process_query(query, params)

        db = get_storage()

        if params:
            stmt = db.exec(proc_query, *params);
        else:
            stmt = db.exec(proc_query);

        try:
            response = stmt.raw().toArray().to_py()
            result = CFResult.from_object(query, params, response, stmt.rowsRead, stmt.rowsWritten)
        except:
            from js import Error
            Error.stackTraceLimit = 1e10
            raise Error(Error.new().stack)

        return result
