import pytest
from _client import get_json


@pytest.mark.asyncio
async def test_versioning_cases(django_asgi_app):
    cases = [
        ("/drf/versioned/?version=2.0", None, "2.0"),
        ("/drf/versioned/", None, None),
        ("/drf/versioned/", {"Accept": "application/json; version=3.0"}, None),
        ("/drf/versioned/?version=1.0", None, None),
    ]

    for path, headers, expected_version in cases:
        response, payload = await get_json(django_asgi_app, path, headers=headers)
        assert response.status == 200
        if expected_version is not None:
            assert payload["version"] == expected_version
        elif path.endswith("version=1.0"):
            assert isinstance(payload, dict)
            assert "version" in payload
        elif headers:
            assert payload["version"] in {"3.0", "default"}
        else:
            assert payload["version"]
