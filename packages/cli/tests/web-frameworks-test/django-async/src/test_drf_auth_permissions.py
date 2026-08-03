import pytest
from _client import fetch, get_json


@pytest.mark.asyncio
async def test_auth_and_permission_cases(django_asgi_app):
    cases = [
        ("/drf/auth/", None, {401, 403}, None),
        ("/drf/public/", None, 200, {"public": True}),
        (
            "/drf/admin/",
            {"Authorization": "Bearer test-token-123"},
            403,
            None,
        ),
        (
            "/drf/admin/",
            {"Authorization": "Bearer admin-token-456"},
            200,
            {"admin": True},
        ),
        (
            "/drf/custom-auth/",
            {"Authorization": "Bearer test-token-123"},
            200,
            {"user": "testuser", "auth": "token"},
        ),
        (
            "/drf/custom-auth/",
            {"Authorization": "Bearer invalid-token"},
            401,
            None,
        ),
        ("/drf/custom-auth/", None, {401, 403}, None),
    ]

    for path, headers, status, expected in cases:
        if expected is None:
            response = await fetch(django_asgi_app, path, headers=headers)
            if isinstance(status, set):
                assert response.status in status
            else:
                assert response.status == status
        else:
            response, payload = await get_json(django_asgi_app, path, headers=headers)
            assert response.status == status
            assert payload == expected
