"""Tests for CloudflareAccessMiddleware."""
import base64
import hashlib
import json
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# Helper functions to create test JWTs
def base64url_encode(data):
    """Encode bytes to base64url string without padding."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')


def create_jwt_parts(header, payload):
    """Create the header and payload parts of a JWT."""
    header_b64 = base64url_encode(json.dumps(header))
    payload_b64 = base64url_encode(json.dumps(payload))
    return header_b64, payload_b64


def create_test_jwt(payload, kid='test-key-1'):
    """Create a test JWT (unsigned, for testing extraction functions)."""
    header = {'alg': 'RS256', 'typ': 'JWT', 'kid': kid}
    header_b64, payload_b64 = create_jwt_parts(header, payload)
    # Fake signature for structure testing
    signature_b64 = base64url_encode(b'fake-signature')
    return f"{header_b64}.{payload_b64}.{signature_b64}"


@pytest.fixture
def mock_django_settings():
    """Mock Django settings for middleware."""
    settings = MagicMock()
    settings.CLOUDFLARE_ACCESS_AUD = 'test-aud-12345'
    settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
    settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = ['/health/', '/public/']
    settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600
    return settings


@pytest.fixture
def mock_user_model():
    """Mock Django User model."""
    user = MagicMock()
    user.email = 'test@example.com'
    user.first_name = 'Test'
    user.last_name = 'User'
    user.get_full_name.return_value = 'Test User'
    return user


@pytest.fixture
def mock_request():
    """Create a mock Django request."""
    request = MagicMock()
    request.META = {}
    request.COOKIES = {}
    request.path = '/api/resource/'
    request.session = MagicMock()
    return request


class TestJWTExtraction:
    """Tests for JWT token extraction from request."""

    def test_extract_jwt_from_header(self, mock_request):
        """Test extracting JWT from CF-Access-Jwt-Assertion header."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                test_token = 'header-jwt-token'
                mock_request.META['HTTP_CF_ACCESS_JWT_ASSERTION'] = test_token

                result = middleware._extract_jwt_token(mock_request)
                assert result == test_token

    def test_extract_jwt_from_cookie(self, mock_request):
        """Test extracting JWT from CF_Authorization cookie."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                test_token = 'cookie-jwt-token'
                mock_request.COOKIES['CF_Authorization'] = test_token

                result = middleware._extract_jwt_token(mock_request)
                assert result == test_token

    def test_extract_jwt_from_lowercase_cookie(self, mock_request):
        """Test extracting JWT from cf_authorization cookie (lowercase)."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                test_token = 'lowercase-cookie-jwt-token'
                mock_request.COOKIES['cf_authorization'] = test_token

                result = middleware._extract_jwt_token(mock_request)
                assert result == test_token

    def test_extract_jwt_no_token(self, mock_request):
        """Test that None is returned when no JWT is present."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                result = middleware._extract_jwt_token(mock_request)
                assert result is None

    def test_header_takes_precedence_over_cookie(self, mock_request):
        """Test that header JWT takes precedence over cookie."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                mock_request.META['HTTP_CF_ACCESS_JWT_ASSERTION'] = 'header-token'
                mock_request.COOKIES['CF_Authorization'] = 'cookie-token'

                result = middleware._extract_jwt_token(mock_request)
                assert result == 'header-token'


class TestTeamNameExtraction:
    """Tests for team name extraction from JWT."""

    def test_extract_team_name_from_valid_jwt(self):
        """Test extracting team name from JWT issuer claim."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                payload = {
                    'iss': 'https://myteam.cloudflareaccess.com',
                    'email': 'user@example.com'
                }
                jwt_token = create_test_jwt(payload)

                result = middleware._extract_team_name_from_jwt(jwt_token)
                assert result == 'myteam'

    def test_extract_team_name_invalid_issuer_format(self):
        """Test that None is returned for non-Cloudflare issuer."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                payload = {
                    'iss': 'https://other-issuer.com',
                    'email': 'user@example.com'
                }
                jwt_token = create_test_jwt(payload)

                result = middleware._extract_team_name_from_jwt(jwt_token)
                assert result is None

    def test_extract_team_name_missing_issuer(self):
        """Test that None is returned when issuer is missing."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                payload = {'email': 'user@example.com'}
                jwt_token = create_test_jwt(payload)

                result = middleware._extract_team_name_from_jwt(jwt_token)
                assert result is None

    def test_extract_team_name_malformed_jwt(self):
        """Test that None is returned for malformed JWT."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                # JWT with only 2 parts instead of 3
                result = middleware._extract_team_name_from_jwt('invalid.jwt')
                assert result is None


class TestExemptPaths:
    """Tests for exempt path functionality."""

    def test_exempt_path_matches(self):
        """Test that exempt paths are correctly identified."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = ['/health/', '/public/']
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                assert middleware._is_exempt_path('/health/') is True
                assert middleware._is_exempt_path('/health/check') is True
                assert middleware._is_exempt_path('/public/') is True
                assert middleware._is_exempt_path('/public/resource') is True

    def test_non_exempt_path(self):
        """Test that non-exempt paths are correctly identified."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = ['/health/', '/public/']
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                assert middleware._is_exempt_path('/api/') is False
                assert middleware._is_exempt_path('/admin/') is False
                assert middleware._is_exempt_path('/') is False

    def test_empty_exempt_paths(self):
        """Test behavior with no exempt paths configured."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                assert middleware._is_exempt_path('/any/path/') is False


class TestMiddlewareInitialization:
    """Tests for middleware initialization."""

    def test_init_with_aud_only(self):
        """Test initialization with only AUD setting."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = None
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                assert middleware.aud == 'test-aud'
                assert middleware.team_name is None
                assert middleware.team_domain is None
                assert middleware.certs_url is None

    def test_init_with_team_name_only(self):
        """Test initialization with only team name setting."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = None
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                assert middleware.aud is None
                assert middleware.team_name == 'testteam'
                assert middleware.team_domain == 'testteam.cloudflareaccess.com'
                assert middleware.certs_url == 'https://testteam.cloudflareaccess.com/cdn-cgi/access/certs'

    def test_init_with_both_settings(self):
        """Test initialization with both AUD and team name."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                assert middleware.aud == 'test-aud'
                assert middleware.team_name == 'testteam'

    def test_init_without_required_settings(self):
        """Test that ValueError is raised without required settings."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = None
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = None
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                with pytest.raises(ValueError) as exc_info:
                    CloudflareAccessMiddleware(lambda r: r)

                assert "Either CLOUDFLARE_ACCESS_AUD or CLOUDFLARE_ACCESS_TEAM_NAME" in str(exc_info.value)


class TestBase64UrlDecode:
    """Tests for base64url decoding."""

    def test_base64url_decode_standard(self):
        """Test standard base64url decoding."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                # Test with known value
                encoded = base64url_encode(b'hello world')
                result = middleware._base64url_decode(encoded)
                assert result == b'hello world'

    def test_base64url_decode_with_padding_needed(self):
        """Test base64url decoding with padding that needs to be added."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                # 'ab' encodes to 'YWI' which needs 1 padding char
                result = middleware._base64url_decode('YWI')
                assert result == b'ab'


class TestJWTDecodeAndVerify:
    """Tests for JWT decoding and verification."""

    def test_decode_jwt_invalid_format(self):
        """Test that invalid JWT format returns None."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                key_data = {'kid': 'test-key', 'n': 123, 'e': 65537}

                # JWT with wrong number of parts
                result = middleware._decode_and_verify_jwt('only.two', key_data)
                assert result is None

    def test_decode_jwt_key_id_mismatch(self):
        """Test that key ID mismatch returns None."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                # Create JWT with one key ID
                payload = {'email': 'test@example.com'}
                jwt_token = create_test_jwt(payload, kid='key-1')

                # Try to verify with different key ID
                key_data = {'kid': 'key-2', 'n': 123, 'e': 65537}

                result = middleware._decode_and_verify_jwt(jwt_token, key_data)
                assert result is None

    def test_decode_jwt_unsupported_algorithm(self):
        """Test that unsupported algorithm returns None."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                # Create JWT with HS256 algorithm
                header = {'alg': 'HS256', 'typ': 'JWT', 'kid': 'test-key'}
                payload = {'email': 'test@example.com'}
                header_b64, payload_b64 = create_jwt_parts(header, payload)
                signature_b64 = base64url_encode(b'fake-signature')
                jwt_token = f"{header_b64}.{payload_b64}.{signature_b64}"

                key_data = {'kid': 'test-key', 'n': 123, 'e': 65537}

                result = middleware._decode_and_verify_jwt(jwt_token, key_data)
                assert result is None

    def test_decode_jwt_expired_token(self):
        """Test that expired token returns None."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                # Create expired JWT
                payload = {
                    'email': 'test@example.com',
                    'exp': int(time.time()) - 3600  # Expired 1 hour ago
                }
                jwt_token = create_test_jwt(payload, kid='test-key')

                key_data = {'kid': 'test-key', 'n': 123, 'e': 65537}

                result = middleware._decode_and_verify_jwt(jwt_token, key_data)
                assert result is None

    def test_decode_jwt_not_yet_valid(self):
        """Test that not-yet-valid token returns None."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                # Create JWT with nbf in the future
                payload = {
                    'email': 'test@example.com',
                    'nbf': int(time.time()) + 3600  # Valid in 1 hour
                }
                jwt_token = create_test_jwt(payload, kid='test-key')

                key_data = {'kid': 'test-key', 'n': 123, 'e': 65537}

                result = middleware._decode_and_verify_jwt(jwt_token, key_data)
                assert result is None


class TestRSAKeyProcessing:
    """Tests for RSA key processing from JWK format."""

    def test_process_rsa_key_valid(self):
        """Test processing valid RSA key from JWK."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                # Sample JWK with small values for testing
                key_info = {
                    'kty': 'RSA',
                    'kid': 'test-key-1',
                    'n': base64url_encode(b'\x00\x01\x00\x01'),  # Small modulus for testing
                    'e': base64url_encode(b'\x01\x00\x01')  # Exponent (65537)
                }

                result = middleware._process_rsa_key(key_info)

                assert result is not None
                assert result['kid'] == 'test-key-1'
                assert 'n' in result
                assert 'e' in result

    def test_process_rsa_key_missing_n(self):
        """Test that missing modulus returns None."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                key_info = {
                    'kty': 'RSA',
                    'kid': 'test-key-1',
                    'e': base64url_encode(b'\x01\x00\x01')
                    # 'n' is missing
                }

                result = middleware._process_rsa_key(key_info)
                assert result is None

    def test_process_rsa_key_missing_e(self):
        """Test that missing exponent returns None."""
        with patch.dict('sys.modules', {'django.contrib.auth': MagicMock(),
                                         'django.contrib.auth.models': MagicMock(),
                                         'django.http': MagicMock(),
                                         'django.conf': MagicMock(),
                                         'django.core.cache': MagicMock()}):
            with patch('django.conf.settings') as mock_settings:
                mock_settings.CLOUDFLARE_ACCESS_AUD = 'test-aud'
                mock_settings.CLOUDFLARE_ACCESS_TEAM_NAME = 'testteam'
                mock_settings.CLOUDFLARE_ACCESS_EXEMPT_PATHS = []
                mock_settings.CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600

                from django_cf.middleware.CloudflareAccessMiddleware import CloudflareAccessMiddleware

                middleware = CloudflareAccessMiddleware(lambda r: r)

                key_info = {
                    'kty': 'RSA',
                    'kid': 'test-key-1',
                    'n': base64url_encode(b'\x00\x01\x00\x01')
                    # 'e' is missing
                }

                result = middleware._process_rsa_key(key_info)
                assert result is None
