"""Middleware and WSGI tests executed inside workerd."""

# pyright: reportMissingImports=false

import base64
import importlib
import json
import time
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import django.conf
import pytest
import workers


def base64url_encode(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def create_jwt_parts(header, payload):
    return base64url_encode(json.dumps(header)), base64url_encode(json.dumps(payload))


def create_test_jwt(payload, kid="test-key-1"):
    header = {"alg": "RS256", "typ": "JWT", "kid": kid}
    header_b64, payload_b64 = create_jwt_parts(header, payload)
    signature_b64 = base64url_encode(b"fake-signature")
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def make_request(path="/api/resource/"):
    return SimpleNamespace(META={}, COOKIES={}, path=path, session=MagicMock())


def middleware_module():
    return importlib.import_module("django_cf.middleware.CloudflareAccessMiddleware")


def make_middleware(
    monkeypatch,
    *,
    aud: str | None = "test-aud-12345",
    team_name: str | None = "testteam",
    exempt_paths=None,
    cache_timeout=3600,
):
    from django.conf import settings

    exempt_paths = [] if exempt_paths is None else exempt_paths
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCESS_AUD", aud, raising=False)
    monkeypatch.setattr(
        settings, "CLOUDFLARE_ACCESS_TEAM_NAME", team_name, raising=False
    )
    monkeypatch.setattr(
        settings, "CLOUDFLARE_ACCESS_EXEMPT_PATHS", exempt_paths, raising=False
    )
    monkeypatch.setattr(
        settings, "CLOUDFLARE_ACCESS_CACHE_TIMEOUT", cache_timeout, raising=False
    )
    return middleware_module().CloudflareAccessMiddleware(lambda request: request)


def unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def make_r2_storage(**kwargs):
    from django_cf.storage.r2 import R2Storage

    return R2Storage(**kwargs)


def make_live_r2_storage(**kwargs):
    pyodide_run_sync = None
    try:
        from pyodide.ffi import run_sync as pyodide_run_sync
    except ImportError:
        pytest.skip("R2Storage requires pyodide.ffi.run_sync (JSPI)")
    assert pyodide_run_sync is not None

    storage = make_r2_storage(**kwargs)
    storage._bucket = workers.env.BUCKET
    storage._run_sync = pyodide_run_sync
    return storage


def save_bytes(storage, name: str, data: bytes) -> str:
    return storage._save(name, BytesIO(data))


class TestJWTExtraction:
    def test_extract_jwt_from_header(self, monkeypatch):
        middleware = make_middleware(monkeypatch)
        request = make_request()
        request.META["HTTP_CF_ACCESS_JWT_ASSERTION"] = "header-jwt-token"

        assert middleware._extract_jwt_token(request) == "header-jwt-token"

    def test_extract_jwt_from_cookie(self, monkeypatch):
        middleware = make_middleware(monkeypatch)
        request = make_request()
        request.COOKIES["CF_Authorization"] = "cookie-jwt-token"

        assert middleware._extract_jwt_token(request) == "cookie-jwt-token"

    def test_extract_jwt_from_lowercase_cookie(self, monkeypatch):
        middleware = make_middleware(monkeypatch)
        request = make_request()
        request.COOKIES["cf_authorization"] = "lowercase-cookie-jwt-token"

        assert middleware._extract_jwt_token(request) == "lowercase-cookie-jwt-token"

    def test_extract_jwt_no_token(self, monkeypatch):
        assert make_middleware(monkeypatch)._extract_jwt_token(make_request()) is None

    def test_no_broken_dash_header_lookup(self, monkeypatch):
        middleware = make_middleware(monkeypatch)
        request = make_request()
        request.META["HTTP-CF-ACCESS-JWT-ASSERTION"] = "broken-token"

        assert middleware._extract_jwt_token(request) is None

        request.META["HTTP_CF_ACCESS_JWT_ASSERTION"] = "good-token"
        assert middleware._extract_jwt_token(request) == "good-token"

    def test_header_takes_precedence_over_cookie(self, monkeypatch):
        middleware = make_middleware(monkeypatch)
        request = make_request()
        request.META["HTTP_CF_ACCESS_JWT_ASSERTION"] = "header-token"
        request.COOKIES["CF_Authorization"] = "cookie-token"

        assert middleware._extract_jwt_token(request) == "header-token"


class TestTeamNameExtraction:
    def test_extract_team_name_from_valid_jwt(self, monkeypatch):
        middleware = make_middleware(monkeypatch)

        jwt_token = create_test_jwt(
            {
                "iss": "https://myteam.cloudflareaccess.com",
                "email": "user@example.com",
            }
        )

        assert middleware._extract_team_name_from_jwt(jwt_token) == "myteam"

    def test_extract_team_name_invalid_issuer_format(self, monkeypatch):
        middleware = make_middleware(monkeypatch)
        jwt_token = create_test_jwt(
            {"iss": "https://other-issuer.com", "email": "user@example.com"}
        )

        assert middleware._extract_team_name_from_jwt(jwt_token) is None

    def test_extract_team_name_missing_issuer(self, monkeypatch):
        middleware = make_middleware(monkeypatch)

        assert (
            middleware._extract_team_name_from_jwt(
                create_test_jwt({"email": "user@example.com"})
            )
            is None
        )

    def test_extract_team_name_malformed_jwt(self, monkeypatch):
        assert (
            make_middleware(monkeypatch)._extract_team_name_from_jwt("invalid.jwt")
            is None
        )


class TestExemptPaths:
    def test_exempt_path_matches(self, monkeypatch):
        middleware = make_middleware(monkeypatch, exempt_paths=["/health/", "/public/"])

        assert middleware._is_exempt_path("/health/") is True
        assert middleware._is_exempt_path("/health/check") is True
        assert middleware._is_exempt_path("/public/") is True
        assert middleware._is_exempt_path("/public/resource") is True

    def test_non_exempt_path(self, monkeypatch):
        middleware = make_middleware(monkeypatch, exempt_paths=["/health/", "/public/"])

        assert middleware._is_exempt_path("/api/") is False
        assert middleware._is_exempt_path("/admin/") is False
        assert middleware._is_exempt_path("/") is False

    def test_empty_exempt_paths(self, monkeypatch):
        assert make_middleware(monkeypatch)._is_exempt_path("/any/path/") is False


class TestMiddlewareInitialization:
    def test_init_with_aud_only(self, monkeypatch):
        middleware = make_middleware(monkeypatch, team_name=None)

        assert middleware.aud == "test-aud-12345"
        assert middleware.team_name is None
        assert middleware.team_domain is None
        assert middleware.certs_url is None

    def test_init_with_team_name_only(self, monkeypatch):
        middleware = make_middleware(monkeypatch, aud=None)

        assert middleware.aud is None
        assert middleware.team_name == "testteam"
        assert middleware.team_domain == "testteam.cloudflareaccess.com"
        assert (
            middleware.certs_url
            == "https://testteam.cloudflareaccess.com/cdn-cgi/access/certs"
        )

    def test_init_with_both_settings(self, monkeypatch):
        middleware = make_middleware(monkeypatch)

        assert middleware.aud == "test-aud-12345"
        assert middleware.team_name == "testteam"

    def test_init_without_required_settings(self, monkeypatch):
        with pytest.raises(ValueError) as exc_info:
            make_middleware(monkeypatch, aud=None, team_name=None)

        assert "Either CLOUDFLARE_ACCESS_AUD or CLOUDFLARE_ACCESS_TEAM_NAME" in str(
            exc_info.value
        )


class TestBase64UrlDecode:
    def test_base64url_decode_standard(self, monkeypatch):
        middleware = make_middleware(monkeypatch)
        encoded = base64url_encode(b"hello world")

        assert middleware._base64url_decode(encoded) == b"hello world"

    def test_base64url_decode_with_padding_needed(self, monkeypatch):
        assert make_middleware(monkeypatch)._base64url_decode("YWI") == b"ab"


class TestJWTDecodeAndVerify:
    def test_decode_jwt_invalid_format(self, monkeypatch):
        middleware = make_middleware(monkeypatch)

        assert (
            middleware._decode_and_verify_jwt(
                "only.two", {"kid": "test-key", "n": 123, "e": 65537}
            )
            is None
        )

    def test_decode_jwt_key_id_mismatch(self, monkeypatch):
        middleware = make_middleware(monkeypatch)
        jwt_token = create_test_jwt({"email": "test@example.com"}, kid="key-1")

        assert (
            middleware._decode_and_verify_jwt(
                jwt_token, {"kid": "key-2", "n": 123, "e": 65537}
            )
            is None
        )

    def test_decode_jwt_unsupported_algorithm(self, monkeypatch):
        middleware = make_middleware(monkeypatch)
        header = {"alg": "HS256", "typ": "JWT", "kid": "test-key"}
        payload = {"email": "test@example.com"}
        header_b64, payload_b64 = create_jwt_parts(header, payload)
        jwt_token = f"{header_b64}.{payload_b64}.{base64url_encode(b'fake-signature')}"

        assert (
            middleware._decode_and_verify_jwt(
                jwt_token, {"kid": "test-key", "n": 123, "e": 65537}
            )
            is None
        )

    def test_decode_jwt_expired_token(self, monkeypatch):
        middleware = make_middleware(monkeypatch)
        jwt_token = create_test_jwt(
            {"email": "test@example.com", "exp": int(time.time()) - 3600},
            kid="test-key",
        )

        assert (
            middleware._decode_and_verify_jwt(
                jwt_token, {"kid": "test-key", "n": 123, "e": 65537}
            )
            is None
        )

    def test_decode_jwt_not_yet_valid(self, monkeypatch):
        middleware = make_middleware(monkeypatch)
        jwt_token = create_test_jwt(
            {"email": "test@example.com", "nbf": int(time.time()) + 3600},
            kid="test-key",
        )

        assert (
            middleware._decode_and_verify_jwt(
                jwt_token, {"kid": "test-key", "n": 123, "e": 65537}
            )
            is None
        )


class TestRSAKeyProcessing:
    def test_process_rsa_key_valid(self, monkeypatch):
        middleware = make_middleware(monkeypatch)
        result = middleware._process_rsa_key(
            {
                "kty": "RSA",
                "kid": "test-key-1",
                "n": base64url_encode(b"\x00\x01\x00\x01"),
                "e": base64url_encode(b"\x01\x00\x01"),
            }
        )

        assert result is not None
        assert result["kid"] == "test-key-1"
        assert "n" in result
        assert "e" in result

    def test_process_rsa_key_missing_n(self, monkeypatch):
        middleware = make_middleware(monkeypatch)

        assert (
            middleware._process_rsa_key(
                {
                    "kty": "RSA",
                    "kid": "test-key-1",
                    "e": base64url_encode(b"\x01\x00\x01"),
                }
            )
            is None
        )

    def test_process_rsa_key_missing_e(self, monkeypatch):
        middleware = make_middleware(monkeypatch)

        assert (
            middleware._process_rsa_key(
                {
                    "kty": "RSA",
                    "kid": "test-key-1",
                    "n": base64url_encode(b"\x00\x01\x00\x01"),
                }
            )
            is None
        )


class TestUserProvisioning:
    def test_get_or_create_user_creates_user(self, monkeypatch):
        module = middleware_module()
        middleware = make_middleware(monkeypatch)

        created = {}

        class FakeDoesNotExist(Exception):
            pass

        class FakeManager:
            def get(self, email):
                raise FakeDoesNotExist()

            def create_user(self, **kwargs):
                created.update(kwargs)
                return SimpleNamespace(**kwargs)

        fake_user_model = SimpleNamespace(
            objects=FakeManager(), DoesNotExist=FakeDoesNotExist
        )
        monkeypatch.setattr(module, "User", fake_user_model)

        user = middleware._get_or_create_user("user@example.com", "Test User")

        assert user.email == "user@example.com"
        assert created["username"] == "user@example.com"
        assert created["first_name"] == "Test"
        assert created["last_name"] == "User"
        assert created["is_active"] is True

    def test_get_or_create_user_updates_existing_name(self, monkeypatch):
        module = middleware_module()
        middleware = make_middleware(monkeypatch)
        existing = SimpleNamespace(
            email="user@example.com",
            first_name="Old",
            last_name="Name",
            save=MagicMock(),
        )
        existing.get_full_name = (
            lambda: f"{existing.first_name} {existing.last_name}".strip()
        )

        class FakeManager:
            def get(self, email):
                return existing

        fake_user_model = SimpleNamespace(objects=FakeManager(), DoesNotExist=Exception)
        monkeypatch.setattr(module, "User", fake_user_model)

        user = middleware._get_or_create_user("user@example.com", "New Name")

        assert user is existing
        assert existing.first_name == "New"
        assert existing.last_name == "Name"
        existing.save.assert_called_once_with()


class TestDjangoCFErrorMessages:
    def test_djangocf_get_app_error_message(self):
        from django_cf import DjangoCF

        cf = DjangoCF()
        with pytest.raises(NotImplementedError) as exc_info:
            cf.get_app()

        assert (
            str(exc_info.value) == "Please implement get_app in your django_cf worker"
        )
        assert "implement implement" not in str(exc_info.value)


class TestR2StorageInitialization:
    def test_init_default_values(self):
        storage = make_r2_storage()

        assert storage.binding == "BUCKET"
        assert storage.location == ""
        assert storage.allow_overwrite is False
        assert storage._bucket is None

    def test_init_custom_values(self):
        storage = make_r2_storage(
            binding="MY_BUCKET", location="uploads/", allow_overwrite=True
        )

        assert storage.binding == "MY_BUCKET"
        assert storage.location == "uploads"
        assert storage.allow_overwrite is True

    def test_init_strips_slashes_from_location(self):
        assert make_r2_storage(location="/uploads/files/").location == "uploads/files"


class TestR2StoragePathsAndUrls:
    def test_full_path_no_location(self):
        assert (
            make_r2_storage(location="")._full_path("test/file.txt") == "test/file.txt"
        )

    def test_full_path_with_location(self):
        assert (
            make_r2_storage(location="uploads")._full_path("test/file.txt")
            == "uploads/test/file.txt"
        )

    def test_url_raises_without_media_url(self, monkeypatch):
        storage = make_r2_storage()

        monkeypatch.setattr(django.conf, "settings", SimpleNamespace())

        with pytest.raises(ValueError, match="MEDIA_URL must be configured"):
            storage.url("file.txt")

    def test_url_raises_with_empty_media_url(self, monkeypatch):
        storage = make_r2_storage()

        monkeypatch.setattr(django.conf, "settings", SimpleNamespace(MEDIA_URL=""))

        with pytest.raises(ValueError, match="MEDIA_URL must be configured"):
            storage.url("file.txt")

    def test_url_constructs_correct_path(self, monkeypatch):
        storage = make_r2_storage(location="uploads")
        monkeypatch.setattr(
            django.conf, "settings", SimpleNamespace(MEDIA_URL="/media/")
        )

        assert storage.url("file.txt") == "/media/uploads/file.txt"


class TestR2StorageMissingObjects:
    def test_read_returns_none_on_not_found(self):
        storage = make_live_r2_storage(location=unique_name("r2-missing-read"))

        assert storage._read("nonexistent.txt") is None

    def test_exists_returns_false_on_not_found(self):
        storage = make_live_r2_storage(location=unique_name("r2-missing-exists"))

        assert storage.exists("nonexistent.txt") is False

    def test_size_returns_zero_on_not_found(self):
        storage = make_live_r2_storage(location=unique_name("r2-missing-size"))

        assert storage.size("nonexistent.txt") == 0

    def test_get_modified_time_returns_now_for_missing_file(self):
        storage = make_live_r2_storage(location=unique_name("r2-missing-modified"))

        result = storage.get_modified_time("nonexistent.txt")

        assert abs((datetime.now() - result).total_seconds()) < 5


class TestR2StoragePersistence:
    def test_save_with_file_like_object(self):
        storage = make_live_r2_storage(location=unique_name("r2-save-filelike"))
        name = unique_name("test") + ".txt"

        assert save_bytes(storage, name, b"test content") == name
        assert storage._read(name) == b"test content"

    def test_listdir_with_empty_path(self):
        storage = make_live_r2_storage(location=unique_name("r2-empty-listdir"))

        directories, files = storage.listdir("")

        assert directories == []
        assert files == []

    def test_listdir_scopes_to_directory_prefix(self):
        storage = make_live_r2_storage(location=unique_name("r2-listdir-scope"))

        save_bytes(storage, "uploads/file.txt", b"file")
        save_bytes(storage, "uploads2/other.txt", b"other")

        directories, files = storage.listdir("uploads")

        assert directories == []
        assert files == ["file.txt"]

    def test_get_available_name_raises_on_too_long(self):
        storage = make_r2_storage()

        with pytest.raises(Exception, match="too long"):
            storage.get_available_name("a" * 300, max_length=100)

    def test_get_available_name_returns_original_when_allow_overwrite(self):
        storage = make_r2_storage(allow_overwrite=True)

        assert storage.get_available_name("file.txt") == "file.txt"

    def test_get_available_name_returns_original_when_not_exists(self):
        storage = make_live_r2_storage(location=unique_name("r2-available-original"))

        assert storage.get_available_name("file.txt") == "file.txt"

    def test_get_available_name_increments_counter(self):
        storage = make_live_r2_storage(location=unique_name("r2-available-counter"))

        save_bytes(storage, "file.txt", b"first")
        save_bytes(storage, "file_1.txt", b"second")

        assert storage.get_available_name("file.txt") == "file_2.txt"

    def test_get_accessed_time_returns_modified_time(self):
        storage = make_live_r2_storage(location=unique_name("r2-accessed-time"))
        expected = datetime(2026, 1, 1, 12, 0, 0)
        storage.get_modified_time = lambda name: expected

        assert storage.get_accessed_time("file.txt") == expected

    def test_get_created_time_returns_modified_time(self):
        storage = make_live_r2_storage(location=unique_name("r2-created-time"))
        expected = datetime(2026, 1, 1, 12, 0, 0)
        storage.get_modified_time = lambda name: expected

        assert storage.get_created_time("file.txt") == expected


class TestR2FileClass:
    def test_r2file_read_mode(self):
        from django_cf.storage.r2 import R2File

        storage = make_live_r2_storage(location=unique_name("r2file-read"))
        name = unique_name("read") + ".txt"
        save_bytes(storage, name, b"test content")

        assert R2File(name, storage, mode="rb").read() == b"test content"

    def test_r2file_write_raises_in_read_mode(self):
        from django_cf.storage.r2 import R2File

        storage = make_live_r2_storage(location=unique_name("r2file-readonly"))
        name = unique_name("readonly") + ".txt"
        save_bytes(storage, name, b"existing")
        r2file = R2File(name, storage, mode="rb")

        with pytest.raises(AttributeError, match="not opened for writing"):
            r2file.write(b"new content")

    def test_r2file_write_allowed_in_write_mode(self):
        from django_cf.storage.r2 import R2File

        storage = make_live_r2_storage(location=unique_name("r2file-write"))
        r2file = R2File(unique_name("write") + ".txt", storage, mode="wb")

        assert r2file.write(b"new content") == 11

    def test_r2file_close(self):
        from django_cf.storage.r2 import R2File

        storage = make_live_r2_storage(location=unique_name("r2file-close"))
        name = unique_name("close") + ".txt"
        save_bytes(storage, name, b"content")
        r2file = R2File(name, storage)
        _ = r2file.file

        assert r2file._file is not None

        r2file.close()
        assert r2file._file.closed is True

    def test_djangocf_durable_object_get_app_error_message(self):
        from django_cf import DjangoCFDurableObject

        with pytest.raises(NotImplementedError) as exc_info:
            DjangoCFDurableObject.get_app(None)

        assert (
            str(exc_info.value) == "Please implement get_app in your django_cf worker"
        )
        assert "implement implement" not in str(exc_info.value)
