# pyright: reportMissingImports=false

"""
This test requires a PostgreSQL server to be running on localhost.

Run postgresql with docker:

docker run -d --name postgres \
    -e POSTGRES_USER=testuser \
    -e POSTGRES_PASSWORD=testpass \
    -e POSTGRES_DB=testdb \
    -e POSTGRES_HOST_AUTH_METHOD=md5 \
    -e POSTGRES_INITDB_ARGS="--auth-host=md5" \
    -p 5432:5432 \
    --health-cmd="pg_isready -U testuser -d testdb" \
    --health-interval=10s \
    --health-timeout=5s \
    --health-retries=5 \
    postgres:16

Then run the test:

uv run pytest tests/test_bindings.py -m hyperdrive -k postgresql

Note: "POSTGRES_HOST_AUTH_METHOD=md5" is required for PostgreSQL to work with pg8000, since the
      default `scram-sha-256` is not available in the pg8000 with Python workers (missing openssl)
"""

import sys

import pg8000
import pytest
from conftest import unique_table_name


@pytest.fixture(autouse=True)
def skip_if_no_socket_support():
    if sys.version_info.minor < 14:
        pytest.skip("Socket support requires Python 3.14+")


def _connect(env):
    hd = env.HYPERDRIVE_PG
    return pg8000.connect(
        host=hd.host,
        port=int(hd.port),
        user=hd.user,
        password=hd.password,
        database=hd.database,
        # Hyperdrive terminates TLS to the origin, so this hop is plaintext.
        ssl_context=False,
    )


@pytest.mark.asyncio
async def test_connect(env):
    conn = _connect(env)
    cur = conn.cursor()
    cur.execute("SELECT 1")
    assert cur.fetchone() == [1]
    conn.close()


@pytest.mark.asyncio
async def test_create_insert_select(env):
    conn = _connect(env)
    table = unique_table_name()
    cur = conn.cursor()
    try:
        cur.execute(
            f"CREATE TABLE {table} (id SERIAL PRIMARY KEY, name TEXT, value INT)"
        )
        cur.execute(f"INSERT INTO {table} (name, value) VALUES (%s, %s)", ("alpha", 1))
        cur.execute(f"INSERT INTO {table} (name, value) VALUES (%s, %s)", ("beta", 2))
        conn.commit()

        cur.execute(f"SELECT name, value FROM {table} ORDER BY name")
        assert list(cur.fetchall()) == [["alpha", 1], ["beta", 2]]
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
            f"CREATE TABLE {table} (id SERIAL PRIMARY KEY, name TEXT, value INT)"
        )
        cur.execute(f"INSERT INTO {table} (name, value) VALUES (%s, %s)", ("alpha", 1))
        conn.commit()

        cur.execute(
            f"UPDATE {table} SET value = value + 10 WHERE name = %s", ("alpha",)
        )
        conn.commit()

        cur.execute(f"SELECT value FROM {table} WHERE name = %s", ("alpha",))
        assert cur.fetchone() == [11]
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
        cur.execute(f"CREATE TABLE {table} (id SERIAL PRIMARY KEY, name TEXT)")
        cur.execute(f"INSERT INTO {table} (name) VALUES (%s)", ("alpha",))
        cur.execute(f"INSERT INTO {table} (name) VALUES (%s)", ("beta",))
        conn.commit()

        cur.execute(f"DELETE FROM {table} WHERE name = %s", ("alpha",))
        conn.commit()

        cur.execute(f"SELECT name FROM {table}")
        assert list(cur.fetchall()) == [["beta"]]
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
        cur.execute(f"CREATE TABLE {table} (id SERIAL PRIMARY KEY, name TEXT)")
        conn.commit()

        cur.execute(f"INSERT INTO {table} (name) VALUES (%s)", ("should_disappear",))
        conn.rollback()

        cur.execute(f"SELECT COUNT(*) FROM {table}")
        assert cur.fetchone() == [0]
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
            "id SERIAL PRIMARY KEY, "
            "text_col TEXT, "
            "int_col INT, "
            "float_col DOUBLE PRECISION, "
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
        assert row[3] is True
    finally:
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.close()
