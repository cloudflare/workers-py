# ruff: noqa: F401
# boto3 does `from urllib3.util.ssl_ import ssl`, but `urllib3.util.ssl_` is
# imported without ssl to avoid entropy calls, which leaves `ssl` unbound there.
import boto3


def test_import():
    pass
