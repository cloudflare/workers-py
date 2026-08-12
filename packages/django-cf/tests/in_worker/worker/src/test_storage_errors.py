"""R2 storage tests executed inside workerd."""

# pyright: reportMissingImports=false

from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import django.conf
import pytest
import workers


def unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def make_r2_storage(**kwargs):
    from django_cf.storage.r2 import R2Storage

    return R2Storage(**kwargs)


def make_live_r2_storage(**kwargs):
    pyodide_run_sync = None
    try:
        from pyodide.ffi import run_sync as pyodide_run_sync
    except ImportError:
        pytest.skip("R2Storage requires pyodide.ffi.run_sync (JSPI)")
    assert pyodide_run_sync is not None

    storage = make_r2_storage(**kwargs)
    storage._bucket = workers.env.BUCKET
    storage._run_sync = pyodide_run_sync
    return storage


def save_bytes(storage, name: str, data: bytes) -> str:
    return storage._save(name, BytesIO(data))


class TestR2StorageInitialization:
    def test_init_default_values(self):
        storage = make_r2_storage()

        assert storage.binding == "BUCKET"
        assert storage.location == ""
        assert storage.allow_overwrite is False
        assert storage._bucket is None

    def test_init_custom_values(self):
        storage = make_r2_storage(
            binding="MY_BUCKET", location="uploads/", allow_overwrite=True
        )

        assert storage.binding == "MY_BUCKET"
        assert storage.location == "uploads"
        assert storage.allow_overwrite is True

    def test_init_strips_slashes_from_location(self):
        assert make_r2_storage(location="/uploads/files/").location == "uploads/files"


class TestR2StorageFullPath:
    def test_full_path_no_location(self):
        assert (
            make_r2_storage(location="")._full_path("test/file.txt") == "test/file.txt"
        )

    def test_full_path_with_location(self):
        assert (
            make_r2_storage(location="uploads")._full_path("test/file.txt")
            == "uploads/test/file.txt"
        )


class TestR2StorageUrlErrors:
    def test_url_raises_without_media_url(self, monkeypatch):
        storage = make_r2_storage()

        monkeypatch.setattr(django.conf, "settings", SimpleNamespace())

        with pytest.raises(ValueError, match="MEDIA_URL must be configured"):
            storage.url("file.txt")

    def test_url_raises_with_empty_media_url(self, monkeypatch):
        storage = make_r2_storage()

        monkeypatch.setattr(django.conf, "settings", SimpleNamespace(MEDIA_URL=""))

        with pytest.raises(ValueError, match="MEDIA_URL must be configured"):
            storage.url("file.txt")

    def test_url_constructs_correct_path(self, monkeypatch):
        storage = make_r2_storage(location="uploads")
        monkeypatch.setattr(
            django.conf, "settings", SimpleNamespace(MEDIA_URL="/media/")
        )

        assert storage.url("file.txt") == "/media/uploads/file.txt"


class TestR2StorageReadErrors:
    def test_read_returns_none_on_not_found(self):
        storage = make_live_r2_storage(location=unique_name("r2-missing-read"))

        assert storage._read("nonexistent.txt") is None


class TestR2StorageExistsErrors:
    def test_exists_returns_false_on_not_found(self):
        storage = make_live_r2_storage(location=unique_name("r2-missing-exists"))

        assert storage.exists("nonexistent.txt") is False


class TestR2StorageSizeErrors:
    def test_size_returns_zero_on_not_found(self):
        storage = make_live_r2_storage(location=unique_name("r2-missing-size"))

        assert storage.size("nonexistent.txt") == 0


class TestR2StorageGetModifiedTimeErrors:
    def test_get_modified_time_returns_now_for_missing_file(self):
        storage = make_live_r2_storage(location=unique_name("r2-missing-modified"))

        result = storage.get_modified_time("nonexistent.txt")

        assert abs((datetime.now() - result).total_seconds()) < 5


class TestR2StorageGetAvailableName:
    def test_get_available_name_raises_on_too_long(self):
        storage = make_r2_storage()

        with pytest.raises(Exception, match="too long"):
            storage.get_available_name("a" * 300, max_length=100)

    def test_get_available_name_returns_original_when_allow_overwrite(self):
        storage = make_r2_storage(allow_overwrite=True)

        assert storage.get_available_name("file.txt") == "file.txt"

    def test_get_available_name_returns_original_when_not_exists(self):
        storage = make_live_r2_storage(location=unique_name("r2-available-original"))

        assert storage.get_available_name("file.txt") == "file.txt"

    def test_get_available_name_increments_counter(self):
        storage = make_live_r2_storage(location=unique_name("r2-available-counter"))

        save_bytes(storage, "file.txt", b"first")
        save_bytes(storage, "file_1.txt", b"second")

        assert storage.get_available_name("file.txt") == "file_2.txt"


class TestR2FileClass:
    def test_r2file_read_mode(self):
        from django_cf.storage.r2 import R2File

        storage = make_live_r2_storage(location=unique_name("r2file-read"))
        name = unique_name("read") + ".txt"
        save_bytes(storage, name, b"test content")

        assert R2File(name, storage, mode="rb").read() == b"test content"

    def test_r2file_write_raises_in_read_mode(self):
        from django_cf.storage.r2 import R2File

        storage = make_live_r2_storage(location=unique_name("r2file-readonly"))
        name = unique_name("readonly") + ".txt"
        save_bytes(storage, name, b"existing")
        r2file = R2File(name, storage, mode="rb")

        with pytest.raises(AttributeError, match="not opened for writing"):
            r2file.write(b"new content")

    def test_r2file_write_allowed_in_write_mode(self):
        from django_cf.storage.r2 import R2File

        storage = make_live_r2_storage(location=unique_name("r2file-write"))
        r2file = R2File(unique_name("write") + ".txt", storage, mode="wb")

        assert r2file.write(b"new content") == 11

    def test_r2file_close(self):
        from django_cf.storage.r2 import R2File

        storage = make_live_r2_storage(location=unique_name("r2file-close"))
        name = unique_name("close") + ".txt"
        save_bytes(storage, name, b"content")
        r2file = R2File(name, storage)
        _ = r2file.file

        assert r2file._file is not None

        r2file.close()
        assert r2file._file.closed is True


class TestR2StorageSaveEdgeCases:
    def test_save_with_file_like_object(self):
        storage = make_live_r2_storage(location=unique_name("r2-save-filelike"))
        name = unique_name("test") + ".txt"

        assert save_bytes(storage, name, b"test content") == name
        assert storage._read(name) == b"test content"


class TestR2StorageListdirEdgeCases:
    def test_listdir_with_empty_path(self):
        storage = make_live_r2_storage(location=unique_name("r2-empty-listdir"))

        directories, files = storage.listdir("")

        assert directories == []
        assert files == []

    def test_listdir_scopes_to_directory_prefix(self):
        storage = make_live_r2_storage(location=unique_name("r2-listdir-scope"))

        save_bytes(storage, "uploads/file.txt", b"file")
        save_bytes(storage, "uploads2/other.txt", b"other")

        directories, files = storage.listdir("uploads")

        assert directories == []
        assert files == ["file.txt"]


class TestR2StorageTimeMethodsFallback:
    def test_get_accessed_time_returns_modified_time(self):
        storage = make_live_r2_storage(location=unique_name("r2-accessed-time"))
        expected = datetime(2026, 1, 1, 12, 0, 0)
        storage.get_modified_time = lambda name: expected

        assert storage.get_accessed_time("file.txt") == expected

    def test_get_created_time_returns_modified_time(self):
        storage = make_live_r2_storage(location=unique_name("r2-created-time"))
        expected = datetime(2026, 1, 1, 12, 0, 0)
        storage.get_modified_time = lambda name: expected

        assert storage.get_created_time("file.txt") == expected
