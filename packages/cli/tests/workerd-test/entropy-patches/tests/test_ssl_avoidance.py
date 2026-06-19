"""Tests for packages that use the no_ssl() entropy avoidance patch.

aiohttp.connector, requests.adapters, and urllib3.util.ssl_ all call
ssl.create_default_context() at import time, which consumes entropy. The patch
temporarily hides the ssl module during import to exercise their fallback paths.
"""

import pytest
import requests
import urllib3
from aiohttp.connector import TCPConnector
from requests.adapters import HTTPAdapter


def test_requests_import_and_session():
    assert HTTPAdapter is not None

    session = requests.Session()
    assert session is not None


def test_urllib3_import():
    pool = urllib3.HTTPConnectionPool("example.com", port=80)
    assert pool is not None


@pytest.mark.asyncio
async def test_aiohttp_connector_import():
    connector = TCPConnector()
    assert connector is not None
    await connector.close()
