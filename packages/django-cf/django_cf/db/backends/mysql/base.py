from django.db.backends.mysql.base import DatabaseWrapper as MySQLDatabaseWrapper

from ..._async_unsafe import _unwrap_async_unsafe


class DatabaseWrapper(MySQLDatabaseWrapper):
    # Everything else (vendor, features, operations, transaction support) is
    # inherited unchanged from Django's MySQL backend; only the async_unsafe
    # guards are removed, because Workers always run inside an event loop.
    connect = _unwrap_async_unsafe(MySQLDatabaseWrapper.connect)
    ensure_connection = _unwrap_async_unsafe(MySQLDatabaseWrapper.ensure_connection)
    cursor = _unwrap_async_unsafe(MySQLDatabaseWrapper.cursor)
    commit = _unwrap_async_unsafe(MySQLDatabaseWrapper.commit)
    rollback = _unwrap_async_unsafe(MySQLDatabaseWrapper.rollback)
    close = _unwrap_async_unsafe(MySQLDatabaseWrapper.close)
    savepoint = _unwrap_async_unsafe(MySQLDatabaseWrapper.savepoint)
    savepoint_rollback = _unwrap_async_unsafe(MySQLDatabaseWrapper.savepoint_rollback)
    savepoint_commit = _unwrap_async_unsafe(MySQLDatabaseWrapper.savepoint_commit)
    clean_savepoints = _unwrap_async_unsafe(MySQLDatabaseWrapper.clean_savepoints)
    get_new_connection = _unwrap_async_unsafe(MySQLDatabaseWrapper.get_new_connection)
    create_cursor = _unwrap_async_unsafe(MySQLDatabaseWrapper.create_cursor)
