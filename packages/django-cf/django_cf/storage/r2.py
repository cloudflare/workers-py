import os
from datetime import datetime
from io import BytesIO
from django.core.files.storage import Storage
from django.core.files.base import File
from django.utils.deconstruct import deconstructible
from js import Uint8Array

class R2File(File):
    """
    A file-like object for R2 storage.
    """
    def __init__(self, name, storage, mode='rb'):
        self.name = name
        self._storage = storage
        self._mode = mode
        self._file = None

    @property
    def file(self):
        if self._file is None:
            content = self._storage._read(self.name)
            self._file = BytesIO(content) if content is not None else BytesIO()
        return self._file

    def read(self, num_bytes=None):
        return self.file.read(num_bytes)

    def write(self, content):
        if 'w' not in self._mode and 'a' not in self._mode:
            raise AttributeError("File not opened for writing")
        return self.file.write(content)

    def close(self):
        if self._file is not None:
            self._file.close()


@deconstructible
class R2Storage(Storage):
    """
    Django storage backend for Cloudflare R2.

    Configuration in Django settings:
        STORAGES = {
            "default": {
                "BACKEND": "django_cf.storage.R2Storage",
                "OPTIONS": {
                    "binding": "BUCKET",  # The R2 binding name from wrangler.jsonc
                    "location": "",  # Optional prefix for all files
                }
            }
        }

    In your wrangler.jsonc, configure the R2 bucket binding:
        {
            "r2_buckets": [
                {
                    "binding": "BUCKET",
                    "bucket_name": "<YOUR_BUCKET_NAME>"
                }
            ]
        }
    """

    def __init__(self, binding='BUCKET', location='', allow_overwrite=False):
        self.binding = binding
        self.location = location.strip('/')
        self.allow_overwrite = allow_overwrite
        self._bucket = None
        self._import_from_javascript = None
        self._run_sync = None

    def _get_bucket(self):
        """Lazy initialization of the R2 bucket binding."""
        if self._bucket is None:
            if self._import_from_javascript is None:
                try:
                    from workers import import_from_javascript
                    from pyodide.ffi import run_sync
                    self._import_from_javascript = import_from_javascript
                    self._run_sync = run_sync

                except ImportError as e:
                    raise Exception("Code not running inside a worker!")

            cf_workers = self._import_from_javascript("cloudflare:workers")
            self._bucket = getattr(cf_workers.env, self.binding)

        return self._bucket

    def _full_path(self, name):
        """Generate the full path including location prefix."""
        if self.location:
            return f"{self.location}/{name}"
        return name

    def _open(self, name, mode='rb'):
        """
        Retrieve the file from R2.
        """
        return R2File(name, self, mode)

    def _read(self, name):
        """
        Read the content of a file from R2.
        """
        full_path = self._full_path(name)
        try:
            bucket = self._get_bucket()
            r2_object = self._run_sync(bucket.get(full_path))

            if r2_object is None:
                return None

            return self._run_sync(r2_object.arrayBuffer()).to_bytes()
        except Exception:
            return None

    def _save(self, name, content):
        """
        Save a file to R2.
        """
        full_path = self._full_path(name)

        if hasattr(content, 'read'):
            file_content = content.read()
            file_content = Uint8Array.new(file_content)
        else:
            file_content = content

        bucket = self._get_bucket()

        options = {}
        if hasattr(content, 'content_type') and content.content_type:
            options['httpMetadata'] = {'contentType': content.content_type}

        self._run_sync(bucket.put(full_path, file_content, options if options else None))
        return name

    def delete(self, name):
        """
        Delete a file from R2.
        """
        full_path = self._full_path(name)
        bucket = self._get_bucket()
        self._run_sync(bucket.delete(full_path))

    def exists(self, name):
        """
        Check if a file exists in R2.
        """
        full_path = self._full_path(name)
        try:
            bucket = self._get_bucket()
            result = self._run_sync(bucket.head(full_path)).to_py()
            return result is not None
        except Exception:
            return False

    def listdir(self, path):
        """
        List the contents of a directory in R2.

        Returns:
            tuple: (directories, files)
        """
        full_path = self._full_path(path)
        if full_path and not full_path.endswith('/'):
            full_path += '/'

        bucket = self._get_bucket()
        result = self._run_sync(bucket.list({'prefix': full_path, 'delimiter': '/'})).to_py()

        directories = []
        files = []

        delimited_prefixes = result.get('delimitedPrefixes', [])
        for delimited_prefix in delimited_prefixes:
            directories.append(os.path.basename(delimited_prefix.replace(full_path, "", 1).rstrip('/')))


        objects = result.get('objects', [])
        for obj in objects:
            _obj = obj.to_py()

            if not obj.key.endswith('/'):
                files.append(os.path.basename(obj.key))

        return directories, files

    def size(self, name):
        """
        Return the size of a file in bytes.
        """
        full_path = self._full_path(name)
        try:
            bucket = self._get_bucket()
            metadata = self._run_sync(bucket.head(full_path)).to_py()
            if metadata and hasattr(metadata, 'size'):
                return metadata.size
            return 0
        except Exception:
            return 0

    def url(self, name):
        """
        Return the URL for accessing the file.
        R2 objects are not publicly accessible by default.
        You'll need to set up R2 public buckets or use signed URLs.
        """
        raise NotImplementedError(
            "R2Storage does not support public URLs by default. "
            "Configure R2 public buckets or implement signed URLs."
        )

    def get_accessed_time(self, name):
        """
        Return the last accessed time of a file.
        R2 doesn't provide access time, so return modified time.
        """
        return self.get_modified_time(name)

    def get_created_time(self, name):
        """
        Return the creation time of a file.
        R2 doesn't provide creation time, so return modified time.
        """
        return self.get_modified_time(name)

    def get_modified_time(self, name):
        """
        Return the last modified time of a file.
        """
        full_path = self._full_path(name)
        try:
            bucket = self._get_bucket()
            metadata = self._run_sync(bucket.head(full_path)).to_py()

            if metadata and hasattr(metadata, 'uploaded'):
                uploaded = metadata.uploaded
                if isinstance(uploaded, datetime):
                    return uploaded
                return datetime.fromisoformat(str(uploaded))

            return datetime.now()
        except Exception:
            return datetime.now()

    def get_available_name(self, name, max_length=None):
        """
        Return a filename that's available in R2.
        """
        if max_length and len(name) > max_length:
            raise Exception(f"File name is too long (max {max_length} characters)")

        if self.allow_overwrite:
            return name

        if not self.exists(name):
            return name

        dir_name, file_name = os.path.split(name)
        file_root, file_ext = os.path.splitext(file_name)
        count = 1

        while self.exists(name) and (max_length is None or len(name) <= max_length):
            name = os.path.join(dir_name, f"{file_root}_{count}{file_ext}")
            count += 1

        return name
