import json
import base64
import hashlib
import time
import urllib.request
import urllib.error
from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse
from django.conf import settings
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

try:
    from js import fetch
    from pyodide.ffi import run_sync

    IS_WORKER = True
except ImportError:
    IS_WORKER = False
    fetch = None
    run_sync = None


class CloudflareAccessMiddleware:
    """
    Django middleware for Cloudflare Access authentication.

    This middleware:
    1. Extracts JWT from CF-Access-Jwt-Assertion header or cf_authorization cookie
    2. Validates the JWT against Cloudflare's public keys
    3. Creates or retrieves user based on JWT claims
    4. Logs the user in automatically

    Settings required (at least one):
    - CLOUDFLARE_ACCESS_AUD: Your Cloudflare Access Application Audience (AUD) tag
    - CLOUDFLARE_ACCESS_TEAM_NAME: Your Cloudflare team name (e.g., 'yourteam')

    If only AUD is provided, team name will be extracted from JWT claims.
    If only team name is provided, AUD will be validated from JWT claims.
    """

    def __init__(self, get_response):
        self.get_response = get_response

        # Validate required settings - at least one must be provided
        self.aud = getattr(settings, 'CLOUDFLARE_ACCESS_AUD', None)
        self.team_name = getattr(settings, 'CLOUDFLARE_ACCESS_TEAM_NAME', None)

        if not self.aud and not self.team_name:
            raise ValueError("Either CLOUDFLARE_ACCESS_AUD or CLOUDFLARE_ACCESS_TEAM_NAME setting is required")

        # If team_name is provided, use it to construct the certs URL
        if self.team_name:
            self.team_domain = f"{self.team_name}.cloudflareaccess.com"
            self.certs_url = f"https://{self.team_domain}/cdn-cgi/access/certs"
        else:
            # We'll determine the team domain from the JWT later
            self.team_domain = None
            self.certs_url = None

        # Optional settings
        self.exempt_paths = getattr(settings, 'CLOUDFLARE_ACCESS_EXEMPT_PATHS', [])
        self.cache_timeout = getattr(settings, 'CLOUDFLARE_ACCESS_CACHE_TIMEOUT', 3600)  # 1 hour

    def __call__(self, request):
        # Always try to authenticate with Cloudflare Access if JWT is present
        # This ensures users stay logged in even after Django logout
        try:
            user = self._authenticate_cloudflare_access(request)
            if user:
                # Set the user on the request (this overrides any logged-out state)
                request.user = user
                # Clear any logout-related session data
                if hasattr(request, 'session'):
                    # User was logged out but CF Access is still valid, re-authenticate
                    try:
                        login(request, user)
                        logger.info("Logged in user %s", user)
                    except Exception as e:
                        logger.warning(f"Failed to re-login user after logout: {str(e)}")
            else:
                # Check if path is exempt from authentication
                if not self._is_exempt_path(request.path):
                    # Authentication failed and path is not exempt, return 401
                    return JsonResponse(
                        {'error': 'Cloudflare Access authentication required'},
                        status=401
                    )
                # Path is exempt, continue with anonymous user

        except Exception as e:
            logger.error(f"Cloudflare Access authentication error: {repr(e)}")
            # Only return 500 for non-exempt paths
            if not self._is_exempt_path(request.path):
                return JsonResponse(
                    {'error': 'Authentication error'},
                    status=500
                )

        return self.get_response(request)

    def _is_exempt_path(self, path):
        """Check if the current path is exempt from authentication."""
        for exempt_path in self.exempt_paths:
            if path.startswith(exempt_path):
                return True
        return False

    def _authenticate_cloudflare_access(self, request):
        """
        Authenticate user using Cloudflare Access JWT.
        Returns User object if valid, None otherwise.
        """
        # Extract JWT token from header or cookie
        jwt_token = self._extract_jwt_token(request)
        if not jwt_token:
            return None

        # If we don't have team_name, try to extract it from JWT first
        if not self.team_name:
            team_name = self._extract_team_name_from_jwt(jwt_token)
            if not team_name:
                logger.error("Unable to determine team name from JWT")
                return None
            self.team_domain = f"{team_name}.cloudflareaccess.com"
            self.certs_url = f"https://{self.team_domain}/cdn-cgi/access/certs"

        # Get Cloudflare public keys
        public_keys = self._get_cloudflare_public_keys()
        if not public_keys:
            logger.error("Failed to retrieve Cloudflare public keys")
            return None

        email = None
        name = None

        # Validate and decode JWT
        try:
            # Try each public key until one works
            decoded_token = None
            for key_data in public_keys:
                try:
                    decoded_token = self._decode_and_verify_jwt(jwt_token, key_data)
                    if decoded_token:
                        break
                except Exception as e:
                    logger.debug(f"Key {key_data.get('kid')} failed: {str(e)}")
                    continue

            if not decoded_token:
                logger.warning("JWT token validation failed with all available keys")
                return None

            # Validate AUD if configured
            if self.aud:
                token_aud = decoded_token.get('aud')
                if isinstance(token_aud, list):
                    if self.aud not in token_aud:
                        logger.warning(f"JWT audience mismatch. Expected: {self.aud}, Got: {token_aud}")
                        return None
                elif token_aud != self.aud:
                    logger.warning(f"JWT audience mismatch. Expected: {self.aud}, Got: {token_aud}")
                    return None

            # Validate AUD if not configured but we have a team name
            if not self.aud and self.team_name:
                token_aud = decoded_token.get('aud')
                if not token_aud:
                    logger.warning("No audience found in JWT token")
                    return None

            # Extract user information from JWT claims
            email = decoded_token.get('email')
            name = decoded_token.get('name', '')

            # Try to get name from custom claims if not in standard claims
            if not name:
                custom_claims = decoded_token.get('custom', {})
                first_name = custom_claims.get('firstName', '')
                last_name = custom_claims.get('lastName', '')
                if first_name or last_name:
                    name = f"{first_name} {last_name}".strip()

            if not email:
                logger.warning("No email found in JWT token")
                return None

        except Exception as e:
            logger.warning(f"JWT token validation error: {repr(e)}")
            return None

        # Get or create user
        user = self._get_or_create_user(email, name)
        return user

    def _extract_jwt_token(self, request):
        """Extract JWT token from CF-Access-Jwt-Assertion header or cf_authorization cookie."""
        # Try header first (most common)
        jwt_token = request.META.get('HTTP_CF_ACCESS_JWT_ASSERTION')
        if jwt_token:
            return jwt_token

        # Try alternative header format
        jwt_token = request.META.get('HTTP_CF_ACCESS_JWT_ASSERTION'.replace('_', '-'))
        if jwt_token:
            return jwt_token

        # Try cookie
        jwt_token = request.COOKIES.get('CF_Authorization')
        if jwt_token:
            return jwt_token

        # Try alternative cookie name
        jwt_token = request.COOKIES.get('cf_authorization')
        if jwt_token:
            return jwt_token

        return None

    def _extract_team_name_from_jwt(self, jwt_token):
        """Extract team name from JWT token without validation (for bootstrapping)."""
        try:
            # Split JWT into parts
            parts = jwt_token.split('.')
            if len(parts) != 3:
                return None

            # Decode payload (add padding if needed)
            payload_part = parts[1]
            payload_part += '=' * (4 - len(payload_part) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_part)
            payload = json.loads(payload_bytes.decode('utf-8'))

            # Extract issuer (iss) claim - format: https://teamname.cloudflareaccess.com
            issuer = payload.get('iss')
            if not issuer:
                return None

            # Extract team name from issuer URL
            if issuer.startswith('https://') and issuer.endswith('.cloudflareaccess.com'):
                team_name = issuer.replace('https://', '').replace('.cloudflareaccess.com', '')
                return team_name

            return None
        except Exception as e:
            logger.error(f"Failed to extract team name from JWT: {str(e)}")
            return None

    def _get_cloudflare_public_keys(self):
        """Retrieve Cloudflare public keys, with caching."""
        # Use team_name for cache key, or extract from team_domain if available
        cache_key_team = self.team_name or (self.team_domain.split('.')[0] if self.team_domain else 'unknown')
        cache_key = f"cloudflare_access_keys_{cache_key_team}"
        cached_keys = cache.get(cache_key)

        if cached_keys:
            return cached_keys

        if IS_WORKER:
            response = run_sync(fetch(self.certs_url))
            if response.status == 200:
                data = run_sync(response.json()).to_py()
            else:
                logger.error(f"Failed to fetch Cloudflare keys: HTTP {response.status}")
                return None
        else:
            try:
                with urllib.request.urlopen(self.certs_url) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode('utf-8'))
                    else:
                        logger.error(f"Failed to fetch Cloudflare keys: HTTP {response.status}")
                        return None
            except urllib.error.URLError as e:
                logger.error(f"Network error fetching Cloudflare keys: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error fetching Cloudflare keys: {str(e)}")
                return None

        keys = data.get('keys', [])

        # Process keys for JWT validation
        processed_keys = []
        for key_info in keys:
            if key_info.get('kty') == 'RSA':
                # Extract RSA components
                try:
                    processed_key = self._process_rsa_key(key_info)
                    if processed_key:
                        processed_keys.append(processed_key)
                except Exception as e:
                    logger.warning(f"Failed to process key {key_info.get('kid')}: {str(e)}")
                    continue

        # Cache the keys
        cache.set(cache_key, processed_keys, self.cache_timeout)
        return processed_keys

    def _process_rsa_key(self, key_info):
        """Process RSA key from JWK format to usable format."""
        try:
            # Extract RSA components from JWK
            n = key_info.get('n')  # modulus
            e = key_info.get('e')  # exponent
            kid = key_info.get('kid')

            if not n or not e:
                return None

            # Decode base64url encoded values
            n_bytes = self._base64url_decode(n)
            e_bytes = self._base64url_decode(e)

            return {
                'kid': kid,
                'n': int.from_bytes(n_bytes, 'big'),
                'e': int.from_bytes(e_bytes, 'big')
            }
        except Exception as e:
            logger.warning(f"Failed to process RSA key: {str(e)}")
            return None

    def _base64url_decode(self, data):
        """Decode base64url encoded data."""
        # Add padding if needed
        data += '=' * (4 - len(data) % 4)
        return base64.urlsafe_b64decode(data)

    def _decode_and_verify_jwt(self, jwt_token, key_data):
        """Decode and verify JWT token using RSA key."""
        try:
            # Split JWT into parts
            parts = jwt_token.split('.')
            if len(parts) != 3:
                raise ValueError("Invalid JWT format")

            header_part, payload_part, signature_part = parts

            # Decode header
            header_bytes = self._base64url_decode(header_part)
            header = json.loads(header_bytes.decode('utf-8'))

            # Check if this key matches the kid in the header
            if header.get('kid') != key_data.get('kid'):
                raise ValueError("Key ID mismatch")

            # Check algorithm
            if header.get('alg') != 'RS256':
                raise ValueError("Unsupported algorithm")

            # Decode payload
            payload_bytes = self._base64url_decode(payload_part)
            payload = json.loads(payload_bytes.decode('utf-8'))

            # Check expiration
            exp = payload.get('exp')
            if exp and exp < time.time():
                raise ValueError("Token expired")

            # Check not before
            nbf = payload.get('nbf')
            if nbf and nbf > time.time():
                raise ValueError("Token not yet valid")

            # Verify signature
            message = f"{header_part}.{payload_part}".encode('utf-8')
            signature = self._base64url_decode(signature_part)

            if not self._verify_rsa_signature(message, signature, key_data):
                raise ValueError("Invalid signature")

            return payload

        except Exception as e:
            logger.debug(f"JWT verification failed: {str(e)}")
            return None

    def _verify_rsa_signature(self, message, signature, key_data):
        """Verify RSA signature using PKCS#1 v1.5 with SHA-256."""
        try:
            # Hash the message
            hash_obj = hashlib.sha256()
            hash_obj.update(message)
            message_hash = hash_obj.digest()

            # Create PKCS#1 v1.5 padding for SHA-256
            # DigestInfo for SHA-256: 30 31 30 0d 06 09 60 86 48 01 65 03 04 02 01 05 00 04 20
            digest_info = bytes.fromhex('3031300d060960864801650304020105000420')
            padded_hash = digest_info + message_hash

            # RSA signature verification
            n = key_data['n']
            e = key_data['e']

            # Convert signature to integer
            sig_int = int.from_bytes(signature, 'big')

            # RSA verification: sig^e mod n
            decrypted_int = pow(sig_int, e, n)

            # Convert back to bytes with proper padding
            # The key length in bytes
            key_length = (n.bit_length() + 7) // 8

            # Ensure we have the right number of bytes
            decrypted_bytes = decrypted_int.to_bytes(key_length, 'big')

            # Check minimum length
            if len(decrypted_bytes) < len(padded_hash) + 11:
                logger.debug(f"Decrypted bytes too short: {len(decrypted_bytes)} < {len(padded_hash) + 11}")
                return False

            # PKCS#1 v1.5 padding format: 0x00 0x01 [0xFF padding] 0x00 [DigestInfo + Hash]
            if len(decrypted_bytes) == 0 or decrypted_bytes[0] != 0x00:
                logger.debug(f"Invalid padding: first byte is {decrypted_bytes[0]:02x}, expected 0x00")
                return False

            if len(decrypted_bytes) < 2 or decrypted_bytes[1] != 0x01:
                logger.debug(f"Invalid padding: second byte is {decrypted_bytes[1]:02x}, expected 0x01")
                return False

            # Find the 0x00 separator
            separator_idx = -1
            for i in range(2, len(decrypted_bytes)):
                if decrypted_bytes[i] == 0x00:
                    separator_idx = i
                    break
                elif decrypted_bytes[i] != 0xFF:
                    logger.debug(f"Invalid padding byte at position {i}: {decrypted_bytes[i]:02x}, expected 0xFF")
                    return False

            if separator_idx == -1:
                logger.debug("No separator found in padding")
                return False

            # Ensure minimum padding length (at least 8 bytes of 0xFF)
            if separator_idx - 2 < 8:
                logger.debug(f"Padding too short: {separator_idx - 2} < 8")
                return False

            # Extract and compare the hash
            extracted_hash = decrypted_bytes[separator_idx + 1:]

            if len(extracted_hash) != len(padded_hash):
                logger.debug(f"Hash length mismatch: {len(extracted_hash)} != {len(padded_hash)}")
                return False

            result = extracted_hash == padded_hash
            if not result:
                logger.debug("Hash comparison failed")
                logger.debug(f"Expected: {padded_hash.hex()}")
                logger.debug(f"Got:      {extracted_hash.hex()}")

            return result

        except Exception as e:
            logger.debug(f"RSA signature verification failed: {str(e)}")
            return False

    def _get_or_create_user(self, email, name):
        """Get or create Django user from Cloudflare Access claims."""
        try:
            # Try to get existing user by email
            user = User.objects.get(email=email)

            # Update name if it has changed
            if name and user.get_full_name() != name:
                # Split name into first and last name
                name_parts = name.split(' ', 1)
                user.first_name = name_parts[0]
                user.last_name = name_parts[1] if len(name_parts) > 1 else ''
                user.save()

            return user

        except User.DoesNotExist:
            # Create new user
            name_parts = name.split(' ', 1) if name else ['', '']

            user = User.objects.create_user(
                username=email,  # Use email as username
                email=email,
                first_name=name_parts[0],
                last_name=name_parts[1] if len(name_parts) > 1 else '',
                is_active=True
            )

            logger.info(f"Created new user from Cloudflare Access: {email}")
            return user
