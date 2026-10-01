"""ORM assertions shared by the independent Django backend suites."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from django.db import connections, models, transaction
from django.test.utils import isolate_apps


class Rollback(Exception):
    """Raised to roll back an atomic block."""


def _table_name() -> str:
    return f"dht_{uuid.uuid4().hex}"


@contextmanager
def _temporary_model(alias: str) -> Iterator[type[models.Model]]:
    table_name = _table_name()
    connection = connections[alias]

    with isolate_apps():

        class TemporaryModel(models.Model):
            name = models.CharField(max_length=100)
            value = models.IntegerField()
            float_value = models.FloatField(default=0.0)
            is_active = models.BooleanField(default=False)

            class Meta:
                app_label = "hyperdrive_tests"
                db_table = table_name

        created = False
        try:
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(TemporaryModel)
            created = True
            yield TemporaryModel
        finally:
            if created:
                with connection.schema_editor() as schema_editor:
                    schema_editor.delete_model(TemporaryModel)


def assert_connectivity(alias: str) -> None:
    connection = connections[alias]
    connection.ensure_connection()
    assert connection.is_usable()


def assert_crud(alias: str) -> None:
    with _temporary_model(alias) as model:
        objects = model.objects.using(alias)
        objects.create(name="alpha", value=1)
        objects.create(name="beta", value=2)

        assert list(
            objects.filter(name__in=["alpha", "beta"])
            .order_by("name")
            .values_list("name", "value")
        ) == [("alpha", 1), ("beta", 2)]

        assert objects.filter(name="alpha").update(value=11) == 1
        assert objects.get(name="alpha").value == 11

        assert objects.filter(name="alpha").delete()[0] == 1
        assert objects.count() == 1
        assert objects.get(name="beta").value == 2


def assert_data_types(alias: str) -> None:
    with _temporary_model(alias) as model:
        objects = model.objects.using(alias)
        created = objects.create(
            name="hello",
            value=42,
            float_value=3.14,
            is_active=True,
        )
        row = objects.get(pk=created.pk)

        assert row.name == "hello"
        assert row.value == 42
        assert abs(row.float_value - 3.14) < 0.001
        assert row.is_active is True


def assert_transaction_rollback(alias: str) -> None:
    with _temporary_model(alias) as model:
        objects = model.objects.using(alias)

        with pytest.raises(Rollback), transaction.atomic(using=alias):
            objects.create(name="should_disappear", value=1)
            raise Rollback

        assert objects.count() == 0
