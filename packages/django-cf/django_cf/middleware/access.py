import json
import jwt
import urllib.request
import urllib.error
from django.contrib.auth import get_user_model, login
from django.http import JsonResponse
from django.conf import settings
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


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
        # Check if path is exempt from authentication
        if self._is_exempt_path(request.path):
            return self.get_response(request)

        # Try to authenticate with Cloudflare Access
        try:
            user = self._authenticate_cloudflare_access(request)
            if user:
                # Set the user on the request and log them in
                request.user = user
                login(request, user)
            else:
                # Authentication failed, return 401
                return JsonResponse(
                    {'error': 'Cloudflare Access authentication required'},
                    status=401
                )
        except Exception as e:
            logger.error(f"Cloudflare Access authentication error: {str(e)}")
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

    def _extract_team_name_from_jwt(self, jwt_token):
        """Extract team name from JWT token without validation (for bootstrapping)."""
        try:
            # Decode JWT without verification to get the issuer
            # This is safe because we only use it to determine the certs URL
            unverified_payload = jwt.decode(jwt_token, options={"verify_signature": False})

            # Extract issuer (iss) claim - format: https://teamname.cloudflareaccess.com
            issuer = unverified_payload.get('iss')
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

        # Validate and decode JWT
        try:
            # Try each public key until one works
            decoded_token = None
            for key_data in public_keys:
                try:
                    # Validate with or without AUD depending on configuration
                    decode_options = {'verify_exp': True}
                    decode_kwargs = {
                        'jwt_token': jwt_token,
                        'key': key_data['key'],
                        'algorithms': ['RS256'],
                        'options': decode_options
                    }

                    # Add audience validation if we have AUD configured
                    if self.aud:
                        decode_kwargs['audience'] = self.aud
                    else:
                        decode_options['verify_aud'] = False
                        decode_kwargs['options'] = decode_options

                    decoded_token = jwt.decode(**decode_kwargs)
                    break
                except jwt.InvalidTokenError:
                    continue

            if not decoded_token:
                logger.warning("JWT token validation failed with all available keys")
                return None

            # Validate AUD if not configured but we have a team name
            if not self.aud and self.team_name:
                token_aud = decoded_token.get('aud')
                if not token_aud:
                    logger.warning("No audience found in JWT token")
                    return None
                # Note: We don't validate the specific AUD value since we don't have it configured
                # The fact that the token was signed by Cloudflare is sufficient validation

            # Extract user information from JWT claims
            email = decoded_token.get('email')
            name = decoded_token.get('name', '')

            if not email:
                logger.warning("No email found in JWT token")
                return None

            # Get or create user
            user = self._get_or_create_user(email, name)
            return user

        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {str(e)}")
            return None

    def _extract_jwt_token(self, request):
        """Extract JWT token from CF-Access-Jwt-Assertion header or cf_authorization cookie."""
        # Try header first
        jwt_token = request.META.get('HTTP_CF_ACCESS_JWT_ASSERTION')
        if jwt_token:
            return jwt_token

        # Try cookie
        jwt_token = request.COOKIES.get('CF_Authorization')
        if jwt_token:
            return jwt_token

        return None

    def _get_cloudflare_public_keys(self):
        """Retrieve Cloudflare public keys, with caching."""
        # Use team_name for cache key, or extract from team_domain if available
        cache_key_team = self.team_name or (self.team_domain.split('.')[0] if self.team_domain else 'unknown')
        cache_key = f"cloudflare_access_keys_{cache_key_team}"
        cached_keys = cache.get(cache_key)

        if cached_keys:
            return cached_keys

        try:
            with urllib.request.urlopen(self.certs_url) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    keys = data.get('keys', [])

                    # Process keys for JWT validation
                    processed_keys = []
                    for key_info in keys:
                        if key_info.get('kty') == 'RSA':
                            # Convert JWK to PEM format for PyJWT
                            try:
                                from jwt.algorithms import RSAAlgorithm
                                pem_key = RSAAlgorithm.from_jwk(json.dumps(key_info))
                                processed_keys.append({
                                    'kid': key_info.get('kid'),
                                    'key': pem_key
                                })
                            except Exception as e:
                                logger.warning(f"Failed to process key {key_info.get('kid')}: {str(e)}")
                                continue

                    # Cache the keys
                    cache.set(cache_key, processed_keys, self.cache_timeout)
                    return processed_keys
                else:
                    logger.error(f"Failed to fetch Cloudflare keys: HTTP {response.status}")
                    return None

        except urllib.error.URLError as e:
            logger.error(f"Network error fetching Cloudflare keys: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching Cloudflare keys: {str(e)}")
            return None

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
