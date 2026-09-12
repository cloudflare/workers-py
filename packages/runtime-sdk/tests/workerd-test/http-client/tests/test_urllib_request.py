import io
import json
import os
import tempfile
import urllib.error
import urllib.request
import urllib.response
from email.message import Message
from http.cookiejar import CookieJar

import pytest

BASE_URL = "http://example.com:80"


def test_urlopen_string_request_and_context_manager():
    with urllib.request.urlopen(f"{BASE_URL}/final") as response:
        assert response.status == 200
        assert response.read() == b"redirected"


def test_request_method_headers_and_data():
    request = urllib.request.Request(
        f"{BASE_URL}/echo",
        data=b"request body",
        headers={"X-Custom": "urllib"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        assert json.loads(response.read()) == {
            "method": "POST",
            "url": "http://example.com:80/echo",
            "custom": "urllib",
            "content_type": "application/x-www-form-urlencoded",
            "body": "request body",
        }


def test_build_opener_with_http_handler():
    opener = urllib.request.build_opener(urllib.request.HTTPHandler())
    with opener.open(f"{BASE_URL}/final") as response:
        assert response.read() == b"redirected"


def test_install_opener_is_restored():
    opener_state = vars(urllib.request)
    previous = opener_state["_opener"]
    opener = urllib.request.build_opener(urllib.request.HTTPHandler())
    try:
        urllib.request.install_opener(opener)
        with urllib.request.urlopen(f"{BASE_URL}/final") as response:
            assert response.read() == b"redirected"
    finally:
        urllib.request.install_opener(previous)


def test_urlopen_follows_redirects():
    with urllib.request.urlopen(f"{BASE_URL}/redirect") as response:
        assert response.geturl() == f"{BASE_URL}/final"
        assert response.read() == b"redirected"


def test_http_error_exposes_readable_body_and_metadata():
    with pytest.raises(urllib.error.HTTPError) as raised:
        urllib.request.urlopen(f"{BASE_URL}/error")

    error = raised.value
    try:
        assert error.code == 418
        assert error.reason == "I'm a Teapot"
        assert error.headers["X-Error"] == "expected"
        assert error.read() == b"teapot body"
    finally:
        error.close()


def test_basic_auth_password_manager():
    password_manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_manager.add_password(None, BASE_URL, "user", "pass")
    opener = urllib.request.build_opener(
        urllib.request.HTTPBasicAuthHandler(password_manager)
    )
    with opener.open(f"{BASE_URL}/auth") as response:
        assert response.read() == b"authenticated"


def test_cookie_processor_persists_cookies():
    cookie_jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    with opener.open(f"{BASE_URL}/set-cookie"):
        pass
    with opener.open(f"{BASE_URL}/cookie") as response:
        assert response.read() == b"session=abc"


def test_urlretrieve_writes_response_to_filesystem():
    descriptor, path = tempfile.mkstemp()
    os.close(descriptor)
    try:
        filename, headers = urllib.request.urlretrieve(f"{BASE_URL}/final", path)
        assert filename == path
        assert headers.get_content_type() == "text/plain"
        with open(path, "rb") as downloaded:
            assert downloaded.read() == b"redirected"
    finally:
        os.unlink(path)


def test_url_error_and_custom_handler_behavior():
    class LocalHandler(urllib.request.BaseHandler):
        def default_open(self, request):
            return urllib.response.addinfourl(
                io.BytesIO(b"handled locally"), Message(), request.full_url, code=200
            )

    opener = urllib.request.build_opener(LocalHandler())
    with opener.open("custom://example.invalid/resource") as response:
        assert response.read() == b"handled locally"

    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen("ftp://example.com/resource")
