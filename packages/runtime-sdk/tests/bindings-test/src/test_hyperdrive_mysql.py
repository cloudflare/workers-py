# pyright: reportMissingImports=false

import pymysql
import pytest
from _hyperdrive import requires_sockets, unique_table_name

pytestmark = requires_sockets


def _connect(env):
    hd = env.HYPERDRIVE_MYSQL
    return pymysql.connect(
        host=hd.host,
        port=int(hd.port),
        user=hd.user,
        password=hd.password,
        database=hd.database,
        unix_socket=False,
        # Hyperdrive terminates TLS to the origin, so this hop is plaintext.
        # pymysql would otherwise upgrade via STARTTLS, which `cloudflare:sockets`
        # rejects unless the socket was opened with secureTransport="starttls".
        ssl_disabled=True,
    )


@pytest.mark.asyncio
async def test_connect(env):
    conn = _connect(env)
    cur = conn.cursor()
    cur.execute("SELECT 1")
    assert cur.fetchone() == (1,)
    conn.close()


@pytest.mark.asyncio
async def test_create_insert_select(env):
    conn = _connect(env)
    table = unique_table_name()
    cur = conn.cursor()
    try:
        cur.execute(
            f"CREATE TABLE {table} "
            "(id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100), value INT)"
        )
        cur.execute(f"INSERT INTO {table} (name, value) VALUES (%s, %s)", ("alpha", 1))
        cur.execute(f"INSERT INTO {table} (name, value) VALUES (%s, %s)", ("beta", 2))
        conn.commit()

        cur.execute(f"SELECT name, value FROM {table} ORDER BY name")
        assert cur.fetchall() == (("alpha", 1), ("beta", 2))
    finally:
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_update(env):
    conn = _connect(env)
    table = unique_table_name()
    cur = conn.cursor()
    try:
        cur.execute(
            f"CREATE TABLE {table} "
            "(id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100), value INT)"
        )
        cur.execute(f"INSERT INTO {table} (name, value) VALUES (%s, %s)", ("alpha", 1))
        conn.commit()

        cur.execute(
            f"UPDATE {table} SET value = value + 10 WHERE name = %s", ("alpha",)
        )
        conn.commit()

        cur.execute(f"SELECT value FROM {table} WHERE name = %s", ("alpha",))
        assert cur.fetchone() == (11,)
    finally:
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_delete(env):
    conn = _connect(env)
    table = unique_table_name()
    cur = conn.cursor()
    try:
        cur.execute(
            f"CREATE TABLE {table} (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100))"
        )
        cur.execute(f"INSERT INTO {table} (name) VALUES (%s)", ("alpha",))
        cur.execute(f"INSERT INTO {table} (name) VALUES (%s)", ("beta",))
        conn.commit()

        cur.execute(f"DELETE FROM {table} WHERE name = %s", ("alpha",))
        conn.commit()

        cur.execute(f"SELECT name FROM {table}")
        assert cur.fetchall() == (("beta",),)
    finally:
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_transaction_rollback(env):
    conn = _connect(env)
    table = unique_table_name()
    cur = conn.cursor()
    try:
        cur.execute(
            f"CREATE TABLE {table} "
            "(id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100)) ENGINE=InnoDB"
        )
        conn.commit()

        cur.execute(f"INSERT INTO {table} (name) VALUES (%s)", ("should_disappear",))
        conn.rollback()

        cur.execute(f"SELECT COUNT(*) FROM {table}")
        assert cur.fetchone() == (0,)
    finally:
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_multiple_data_types(env):
    conn = _connect(env)
    table = unique_table_name()
    cur = conn.cursor()
    try:
        cur.execute(
            f"CREATE TABLE {table} ("
            "id INT AUTO_INCREMENT PRIMARY KEY, "
            "text_col VARCHAR(255), "
            "int_col INT, "
            "float_col DOUBLE, "
            "bool_col BOOLEAN)"
        )
        cur.execute(
            f"INSERT INTO {table} (text_col, int_col, float_col, bool_col) "
            "VALUES (%s, %s, %s, %s)",
            ("hello", 42, 3.14, True),
        )
        conn.commit()

        cur.execute(f"SELECT text_col, int_col, float_col, bool_col FROM {table}")
        row = cur.fetchone()
        assert row[0] == "hello"
        assert row[1] == 42
        assert abs(row[2] - 3.14) < 0.001
        assert row[3] == 1
    finally:
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_executemany(env):
    conn = _connect(env)
    table = unique_table_name()
    cur = conn.cursor()
    try:
        cur.execute(
            f"CREATE TABLE {table} (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100))"
        )
        cur.executemany(
            f"INSERT INTO {table} (name) VALUES (%s)", [("a",), ("b",), ("c",)]
        )
        conn.commit()

        cur.execute(f"SELECT name FROM {table} ORDER BY name")
        assert cur.fetchall() == (("a",), ("b",), ("c",))
    finally:
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.close()
