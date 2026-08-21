"""WSGI D1 tests executed inside workerd.

Requests are driven through ``django_cf.handle_wsgi`` and the shared cached WSGI
app, so the synchronous ORM path is exercised end to end. ``test_asgi_d1``
covers the asynchronous equivalent.
"""

# pyright: reportMissingImports=false

import pytest
from _wsgi_client import get_json
from django.db import connections, models
from django.http import JsonResponse
from django.test import override_settings
from django.urls import path

D1_ALIAS = "d1"
D1_TABLE = "_django_cf_wsgi_d1_records"


class WsgiD1Record(models.Model):
    value = models.CharField(max_length=64)

    class Meta:
        app_label = "django_cf_in_worker"
        db_table = D1_TABLE
        managed = False


def crud_view(request):
    del request
    records = WsgiD1Record.objects.using(D1_ALIAS)

    created = records.create(value="lifecycle-created")
    records.create(value="lifecycle-other")
    records.create(value="lifecycle-zulu")

    created.value = "lifecycle-updated"
    created.save(using=D1_ALIAS, update_fields=["value"])

    loaded = records.get(pk=created.pk)
    filtered = sorted(
        records.filter(value__startswith="lifecycle-").values_list("value", flat=True)
    )
    deleted, _ = records.filter(pk=created.pk).delete()

    return JsonResponse(
        {
            "id": loaded.pk,
            "value": loaded.value,
            "filtered": filtered,
            "deleted": deleted,
            "remaining": list(
                records.order_by("value").values_list("value", flat=True)
            ),
        }
    )


urlpatterns = [path("wsgi/d1/crud/", crud_view)]


def _drop_d1_table():
    connections[D1_ALIAS].run_query(f"DROP TABLE IF EXISTS {D1_TABLE}")


def _create_d1_table():
    _drop_d1_table()
    connections[D1_ALIAS].run_query(
        f"CREATE TABLE {D1_TABLE} "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT NOT NULL)"
    )


async def _run_d1_request(path_name):
    _create_d1_table()
    try:
        with override_settings(ROOT_URLCONF=__name__):
            return await get_json(path_name)
    finally:
        _drop_d1_table()


@pytest.mark.asyncio
async def test_wsgi_d1_orm_crud_lifecycle():
    response, payload = await _run_d1_request("/wsgi/d1/crud/")

    assert response.status == 200
    assert payload is not None
    assert isinstance(payload["id"], int)
    assert payload["id"] > 0
    assert payload["value"] == "lifecycle-updated"
    assert payload["filtered"] == [
        "lifecycle-other",
        "lifecycle-updated",
        "lifecycle-zulu",
    ]
    assert payload["deleted"] == 1
    assert payload["remaining"] == ["lifecycle-other", "lifecycle-zulu"]
