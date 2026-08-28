try:
    import pymysql

    # Django's MySQL backend uses `mysqlclient` as the default database adapter,
    # however, we encourage using PyMySQL as an alternative option for Workers environments,
    # since mysqlclient is
    # - non-pure Python (requires cross compilation)
    # - not verified to be async compatible
    pymysql.install_as_MySQLdb()
except ImportError:
    pass


from .base import DatabaseWrapper  # noqa: E402

__all__ = ["DatabaseWrapper"]
