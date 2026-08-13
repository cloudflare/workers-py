"""ASGI D1 tests executed inside workerd."""

# pyright: reportMissingImports=false

import pytest
from _asgi_client import get_json
from django.core.handlers.asgi import ASGIHandler
from django.db import connections, models
from django.http import JsonResponse
from django.test import override_settings
from django.urls import path

D1_TABLE = "_django_cf_asgi_d1_records"


class AsgiD1Record(models.Model):
    value = models.CharField(max_length=64)

    class Meta:
        app_label = "django_cf_in_worker"
        db_table = D1_TABLE
        managed = False


async def create_and_read_view(request):
    del request
    created = await AsgiD1Record.objects.using("d1").acreate(value="d1-ok")
    loaded = await AsgiD1Record.objects.using("d1").aget(pk=created.pk)
    return JsonResponse({"id": loaded.pk, "value": loaded.value})


async def count_view(request):
    del request
    await AsgiD1Record.objects.using("d1").acreate(value="alpha")
    await AsgiD1Record.objects.using("d1").acreate(value="beta")
    count = await AsgiD1Record.objects.using("d1").acount()  # codespell:ignore acount
    return JsonResponse({"count": count})


async def exists_view(request):
    del request
    await AsgiD1Record.objects.using("d1").acreate(value="present")
    matching = await AsgiD1Record.objects.using("d1").filter(value="present").aexists()
    missing = await AsgiD1Record.objects.using("d1").filter(value="missing").aexists()
    return JsonResponse({"matching": matching, "missing": missing})


async def update_view(request):
    del request
    created = await AsgiD1Record.objects.using("d1").acreate(value="before-update")
    updated = (
        await AsgiD1Record.objects.using("d1")
        .filter(pk=created.pk)
        .aupdate(value="after-update")
    )
    loaded = await AsgiD1Record.objects.using("d1").aget(pk=created.pk)
    return JsonResponse({"id": loaded.pk, "updated": updated, "value": loaded.value})


async def iterate_view(request):
    for value in ["charlie", "alpha", "bravo"]:
        await AsgiD1Record.objects.using("d1").acreate(value=value)

    order_field = "-value" if request.GET.get("direction") == "desc" else "value"

    values = []
    queryset = AsgiD1Record.objects.using("d1").order_by(order_field)
    async for record in queryset:
        values.append(record.value)

    return JsonResponse({"values": values})


urlpatterns = [
    path("asgi/d1/create-read/", create_and_read_view),
    path("asgi/d1/count/", count_view),
    path("asgi/d1/exists/", exists_view),
    path("asgi/d1/update/", update_view),
    path("asgi/d1/iterate/", iterate_view),
]


async def _fetch_d1_response(path_name):
    with override_settings(ROOT_URLCONF=__name__):
        app = ASGIHandler()
        return await get_json(app, path_name)


def _d1_connection():
    return connections["d1"]


def _drop_d1_table():
    _d1_connection().run_query(f"DROP TABLE IF EXISTS {D1_TABLE}")


def _create_d1_table():
    _drop_d1_table()
    _d1_connection().run_query(
        f"CREATE TABLE {D1_TABLE} (id INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT NOT NULL)"
    )


async def _run_d1_request(path_name):
    _create_d1_table()
    try:
        return await _fetch_d1_response(path_name)
    finally:
        _drop_d1_table()


@pytest.mark.asyncio
async def test_asgi_d1_orm_create_and_read():
    response, payload = await _run_d1_request("/asgi/d1/create-read/")

    assert response.status == 200
    assert payload is not None
    assert payload["value"] == "d1-ok"
    assert isinstance(payload["id"], int)
    assert payload["id"] > 0


@pytest.mark.asyncio
async def test_asgi_d1_orm_count_returns_row_total():
    response, payload = await _run_d1_request("/asgi/d1/count/")

    assert response.status == 200
    assert payload == {"count": 2}


@pytest.mark.asyncio
async def test_asgi_d1_orm_exists_reports_matching_and_missing_filters():
    response, payload = await _run_d1_request("/asgi/d1/exists/")

    assert response.status == 200
    assert payload == {"matching": True, "missing": False}


@pytest.mark.asyncio
async def test_asgi_d1_orm_update_returns_affected_rows_and_persists_value():
    response, payload = await _run_d1_request("/asgi/d1/update/")

    assert response.status == 200
    assert payload is not None
    assert payload["updated"] == 1
    assert payload["value"] == "after-update"
    assert isinstance(payload["id"], int)
    assert payload["id"] > 0


@pytest.mark.asyncio
async def test_asgi_d1_orm_async_iteration_returns_all_rows_ascending():
    response, payload = await _run_d1_request("/asgi/d1/iterate/")

    assert response.status == 200
    assert payload is not None
    assert payload["values"] == ["alpha", "bravo", "charlie"]


@pytest.mark.asyncio
async def test_asgi_d1_orm_async_iteration_returns_all_rows_descending():
    response, payload = await _run_d1_request("/asgi/d1/iterate/?direction=desc")

    assert response.status == 200
    assert payload is not None
    assert payload["values"] == ["charlie", "bravo", "alpha"]
