# pyright: reportMissingImports=false

from django.db import models
from django.http import JsonResponse
from django.urls import path

DO_ALIAS = "do"
DO_TABLE = "_django_cf_do_orm_records"
CREATE_DO_TABLE_SQL = (
    f"CREATE TABLE {DO_TABLE} ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "value TEXT NOT NULL, "
    "weight INTEGER NOT NULL)"
)
DROP_DO_TABLE_SQL = f"DROP TABLE IF EXISTS {DO_TABLE}"


class DoOrmRecord(models.Model):
    value = models.CharField(max_length=64)
    weight = models.IntegerField()

    class Meta:
        app_label = "django_cf_in_worker"
        db_table = DO_TABLE
        managed = False


def _records():
    return DoOrmRecord.objects.using(DO_ALIAS)


def do_orm_crud_view(request):
    del request
    created = _records().create(value="alpha", weight=3)
    _records().create(value="bravo", weight=1)
    _records().create(value="charlie", weight=2)

    loaded = _records().get(pk=created.pk)
    loaded.value = "alpha-updated"
    loaded.save(using=DO_ALIAS, update_fields=["value"])

    deleted, _ = _records().filter(value="bravo").delete()

    return JsonResponse(
        {
            "created_id": created.pk,
            "updated_value": _records().get(pk=created.pk).value,
            "deleted": deleted,
            "remaining": list(
                _records().order_by("value").values_list("value", flat=True)
            ),
        }
    )


def do_orm_query_view(request):
    del request
    for value, weight in (("one", 1), ("two", 2), ("three", 3)):
        _records().create(value=value, weight=weight)

    ascending = list(_records().order_by("weight").values_list("value", flat=True))
    descending = list(_records().order_by("-weight").values_list("value", flat=True))
    excluded = list(
        _records().exclude(weight=2).order_by("weight").values_list("value", flat=True)
    )
    matching = _records().filter(value="two").exists()
    missing = _records().filter(value="four").exists()
    deleted, _ = _records().all().delete()

    return JsonResponse(
        {
            "count": len(ascending),
            "matching": matching,
            "missing": missing,
            "ascending": ascending,
            "descending": descending,
            "excluded": excluded,
            "deleted": deleted,
            "remaining": _records().count(),
        }
    )


urlpatterns = [
    path("do/orm/crud/", do_orm_crud_view),
    path("do/orm/query/", do_orm_query_view),
]
