import http.client
import io
import json

import pytest

HOST = "example.com"
PORT = 80


def connection():
    return http.client.HTTPConnection(HOST, PORT)


def get_json(response):
    return json.loads(response.read())


def test_http_connection_explicit_connect_and_close():
    conn = connection()
    try:
        conn.connect()
        assert conn.sock is not None
    finally:
        conn.close()
    assert conn.sock is None


def test_http_connection_lazy_connect_get_path_query_and_headers():
    conn = connection()
    try:
        conn.request("GET", "/echo?name=workers", headers={"X-Custom": "present"})
        payload = get_json(conn.getresponse())
    finally:
        conn.close()

    assert payload == {
        "method": "GET",
        "url": "http://example.com/echo?name=workers",
        "custom": "present",
        "content_type": None,
        "body": "",
    }


@pytest.mark.parametrize(
    "body", ["text body", b"bytes body", bytearray(b"bytearray body")]
)
def test_http_connection_post_string_and_bytes_like_bodies(body):
    conn = connection()
    try:
        conn.request("POST", "/body", body=body)
        expected = bytes(body, "latin-1") if isinstance(body, str) else bytes(body)
        assert conn.getresponse().read() == expected
    finally:
        conn.close()


def test_http_connection_post_file_like_and_iterable_bodies():
    for body in (io.BytesIO(b"file body"), [b"iter", b"able"]):
        conn = connection()
        try:
            conn.request("POST", "/body", body=body, encode_chunked=True)
            expected = b"file body" if hasattr(body, "read") else b"iterable"
            assert conn.getresponse().read() == expected
        finally:
            conn.close()


def test_http_connection_low_level_request_assembly_and_send():
    conn = connection()
    try:
        conn.putrequest("POST", "/echo")
        conn.putheader("Content-Length", "3")
        conn.putheader("X-Custom", "low-level")
        conn.endheaders()
        conn.send(b"raw")
        assert get_json(conn.getresponse()) == {
            "method": "POST",
            "url": "http://example.com/echo",
            "custom": "low-level",
            "content_type": None,
            "body": "raw",
        }
    finally:
        conn.close()


def test_http_response_metadata_and_headers():
    conn = connection()
    try:
        conn.request("GET", "/echo")
        response = conn.getresponse()
        assert response.status == 200
        assert response.reason == "OK"
        assert response.version == 11
        assert response.getheader("content-type") == "application/json"
        assert response.getheaders()
        response.read()
    finally:
        conn.close()


def test_http_response_read_methods_and_peek():
    conn = connection()
    try:
        conn.request("GET", "/lines")
        response = conn.getresponse()
        assert response.peek(5).startswith(b"first")
        assert response.read(5) == b"first"
        target = bytearray(1)
        assert response.readinto(target) == 1
        assert target == b"\n"
        assert response.read1(6) == b"second"
        assert response.read() == b"\nthird\n"
    finally:
        conn.close()


def test_http_response_line_iteration():
    conn = connection()
    try:
        conn.request("GET", "/lines")
        assert list(conn.getresponse()) == [b"first\n", b"second\n", b"third\n"]
    finally:
        conn.close()


def test_http_connection_head_has_no_response_body():
    conn = connection()
    try:
        conn.request("HEAD", "/head")
        response = conn.getresponse()
        assert response.status == 200
        assert response.getheader("X-Origin") == "head"
        assert response.read() == b""
    finally:
        conn.close()


def test_http_connection_reuse_and_reconnect_after_close():
    conn = connection()
    try:
        conn.request("GET", "/body")
        assert conn.getresponse().read() == b""
        conn.request("GET", "/lines")
        assert conn.getresponse().read() == b"first\nsecond\nthird\n"
        conn.close()
        conn.request("GET", "/final")
        assert conn.getresponse().read() == b"redirected"
    finally:
        conn.close()


def test_http_connection_state_and_validation_errors():
    conn = connection()
    with pytest.raises(http.client.ResponseNotReady):
        conn.getresponse()
    with pytest.raises(http.client.CannotSendHeader):
        conn.putheader("X-Test", "value")
    with pytest.raises(ValueError):
        conn.request("GET\n", "/echo")
