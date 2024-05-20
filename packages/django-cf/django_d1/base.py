from django.core.exceptions import ImproperlyConfigured
from django.db.backends.sqlite3.base import DatabaseWrapper as SQLiteDatabaseWrapper

from .client import DatabaseClient
from .creation import DatabaseCreation
from .database import D1Database as Database
from .features import DatabaseFeatures
from .introspection import DatabaseIntrospection
from .operations import DatabaseOperations
from .schema import DatabaseSchemaEditor


class DatabaseWrapper(SQLiteDatabaseWrapper):
    vendor = "sqlite"
    display_name = "D1"

    Database = Database
    SchemaEditorClass = DatabaseSchemaEditor
    client_class = DatabaseClient
    creation_class = DatabaseCreation
    # Classes instantiated in __init__().
    features_class = DatabaseFeatures
    introspection_class = DatabaseIntrospection
    ops_class = DatabaseOperations

    transaction_modes = frozenset([])

    def get_database_version(self):
        return (4,)

    def get_connection_params(self):
        settings_dict = self.settings_dict
        if not settings_dict["CLOUDFLARE_DATABASE_ID"]:
            raise ImproperlyConfigured(
                "settings.DATABASES is improperly configured. "
                "Please supply the CLOUDFLARE_DATABASE_ID value."
            )
        if not settings_dict["CLOUDFLARE_ACCOUNT_ID"]:
            raise ImproperlyConfigured(
                "settings.DATABASES is improperly configured. "
                "Please supply the CLOUDFLARE_ACCOUNT_ID value."
            )
        if not settings_dict["CLOUDFLARE_TOKEN"]:
            raise ImproperlyConfigured(
                "settings.DATABASES is improperly configured. "
                "Please supply the CLOUDFLARE_TOKEN value."
            )
        kwargs = {
            "database_id": settings_dict["CLOUDFLARE_DATABASE_ID"],
            "account_id": settings_dict["CLOUDFLARE_ACCOUNT_ID"],
            "token": settings_dict["CLOUDFLARE_TOKEN"],
        }
        return kwargs

    def get_new_connection(self, conn_params):
        conn = Database.connect(**conn_params)
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
