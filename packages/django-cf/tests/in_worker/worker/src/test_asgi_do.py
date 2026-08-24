"""Durable Objects WSGI ORM tests executed inside workerd.

``stub.fetch`` reaches ``DjangoCFDurableObject.fetch``, which hands the request
to ``django_cf.handle_wsgi``, so these are WSGI requests served by
``TestDurableObject`` with the synchronous ORM running against the Durable
Object storage the object configures in its constructor.
"""

# pyright: reportMissingImports=false

import pytest
from _wsgi_client import read_json

DO_BASE_URL = "http://django-cf-do"


async def get_do_stub(env):
    namespace = env.DO_STORAGE
    object_id = namespace.idFromName("django-cf-backend-tests")
    return namespace.get(object_id)


async def _run_do_request(env, path_name):
    stub = await get_do_stub(env)
    await stub.create_orm_table()
    try:
        response = await stub.fetch(f"{DO_BASE_URL}{path_name}")
        return response, await read_json(response)
    finally:
        await stub.drop_orm_table()


@pytest.mark.asyncio
async def test_do_orm_wsgi_crud_lifecycle_through_django_url(env):
    response, payload = await _run_do_request(env, "/do/orm/crud/")

    assert response.status == 200
    assert payload is not None
    assert isinstance(payload["created_id"], int)
    assert payload["created_id"] > 0
    assert payload["updated_value"] == "alpha-updated"
    assert payload["deleted"] == 1
    assert payload["remaining"] == ["alpha-updated", "charlie"]


@pytest.mark.asyncio
async def test_do_orm_wsgi_filter_order_and_delete_through_django_url(env):
    response, payload = await _run_do_request(env, "/do/orm/query/")

    assert response.status == 200
    assert payload is not None
    assert payload["count"] == 3
    assert payload["matching"] is True
    assert payload["missing"] is False
    assert payload["ascending"] == ["one", "two", "three"]
    assert payload["descending"] == ["three", "two", "one"]
    assert payload["excluded"] == ["one", "three"]
    assert payload["deleted"] == 3
    assert payload["remaining"] == 0
