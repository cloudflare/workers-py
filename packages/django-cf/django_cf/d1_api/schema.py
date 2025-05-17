from django.db.backends.sqlite3.schema import DatabaseSchemaEditor as SQLiteDatabaseSchemaEditor


class DatabaseSchemaEditor(SQLiteDatabaseSchemaEditor):
    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            for sql in self.deferred_sql:
                self.execute(sql)
        if self.atomic_migration:
            self.atomic.__exit__(exc_type, exc_value, traceback)
