from django.db.backends.sqlite3.features import DatabaseFeatures as SQLiteDatabaseFeatures


class DatabaseFeatures(SQLiteDatabaseFeatures):
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

    minimum_database_version = (1,)
