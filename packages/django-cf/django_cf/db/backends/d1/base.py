from django.core.exceptions import ImproperlyConfigured

from ...base_engine import CFDatabaseWrapper, is_read_only_query, CFResult, replace_date_trunc_in_sql


class DatabaseWrapper(CFDatabaseWrapper):
    vendor = "cloudflare_d1"
    display_name = "D1"
    binding: str

    def get_connection_params(self):
        settings_dict = self.settings_dict
        if not settings_dict["CLOUDFLARE_BINDING"]:
            raise ImproperlyConfigured(
                "settings.DATABASES is improperly configured. "
                "Please supply the CLOUDFLARE_BINDING value."
            )
        kwargs = {
            "binding": settings_dict["CLOUDFLARE_BINDING"],
        }
        return kwargs

    def get_new_connection(self, conn_params):
        self.binding = conn_params["binding"]
        return super().get_new_connection(conn_params)

    def __init__(self, *args):
        super().__init__(*args)

        try:
            from workers import import_from_javascript
            from pyodide.ffi import run_sync
            self.import_from_javascript = import_from_javascript
            self.run_sync = run_sync
        except ImportError as e:
            print(e)
            raise Exception("Code not running inside a worker!")


    def process_query(self, query, params=None):
        # Replace django_date_trunc and django_datetime_trunc with SQLite equivalents
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


        if self.cursor()._defer_foreign_keys:
            return f'''
            PRAGMA defer_foreign_keys = on

            {query}

            PRAGMA defer_foreign_keys = off
            '''

        return query, params

    def run_query(self, query, params=None) -> CFResult:
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
                response = self.run_sync(stmt.raw()).to_py()
                result = CFResult.from_object(query, params, response, len(response), 0)
            else:
                response = self.run_sync(stmt.all())
                result = CFResult.from_object(query, params, response.results.to_py(), response.meta.rows_read, response.meta.rows_written,
                                            response.meta.last_row_id)
        except:
            from js import Error
            Error.stackTraceLimit = 1e10
            raise Error(Error.new().stack)

        return result
