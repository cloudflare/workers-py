"""Cloudflare Access tests executed inside workerd."""

# pyright: reportMissingImports=false

import base64
import importlib
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


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
