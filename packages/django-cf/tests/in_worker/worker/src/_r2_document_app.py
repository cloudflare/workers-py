# pyright: reportMissingImports=false

from uuid import uuid4

from django.core.files.base import ContentFile
from django.db import connections, models
from django.http import JsonResponse

D1_ALIAS = "d1"
R2_TABLE = "_django_cf_r2_documents"
R2_UPLOAD_TO = "r2-documents"
R2_CONTENT = b"r2-document-content"
CREATE_R2_TABLE_SQL = (
    f"CREATE TABLE {R2_TABLE} "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, attachment TEXT NOT NULL)"
)
DROP_R2_TABLE_SQL = f"DROP TABLE IF EXISTS {R2_TABLE}"


class R2Document(models.Model):
    attachment = models.FileField(upload_to=R2_UPLOAD_TO, max_length=200)

    class Meta:
        app_label = "django_cf_in_worker"
        db_table = R2_TABLE
        managed = False


def drop_r2_table():
    connections[D1_ALIAS].run_query(DROP_R2_TABLE_SQL)


def create_r2_table():
    drop_r2_table()
    connections[D1_ALIAS].run_query(CREATE_R2_TABLE_SQL)


def document_lifecycle_payload():
    documents = R2Document.objects.using(D1_ALIAS)
    document = R2Document()
    document.attachment.save(
        f"payload-{uuid4().hex}.bin", ContentFile(R2_CONTENT), save=False
    )
    name = document.attachment.name
    storage = document.attachment.storage

    try:
        document.save(using=D1_ALIAS)
        loaded = documents.get(pk=document.pk)
        attachment = loaded.attachment
        attachment.open("rb")
        try:
            content = attachment.read()
        finally:
            attachment.close()

        payload = {
            "id": loaded.pk,
            "name": name,
            "content": content.decode(),
            "size": attachment.size,
            "url": attachment.url,
            "exists_before_delete": storage.exists(name),
        }

        attachment.delete(save=False)
        payload["exists_after_delete"] = storage.exists(name)
        loaded.delete(using=D1_ALIAS)
        payload["rows_after_delete"] = documents.count()
        return payload
    finally:
        if storage.exists(name):
            storage.delete(name)
        if document.pk is not None:
            documents.filter(pk=document.pk).delete()


def sync_document_view(request):
    del request
    return JsonResponse(document_lifecycle_payload())


async def async_document_view(request):
    del request
    return JsonResponse(document_lifecycle_payload())
