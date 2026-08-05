from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

TOKENS = {
    "test-token-123": "testuser",
    "admin-token-456": "admin",
}


class TokenAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:]
        username = TOKENS.get(token)
        if username is None:
            raise AuthenticationFailed("Invalid token")
        from django_app.auth_backend import InMemoryUser

        return (InMemoryUser(username), token)
