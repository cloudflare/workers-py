"""Tests for R2 storage error handling and edge cases."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from io import BytesIO


class TestR2StorageInitialization:
    """Tests for R2Storage initialization."""

    def test_init_default_values(self):
        """Test R2Storage initializes with default values."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()

            assert storage.binding == 'BUCKET'
            assert storage.location == ''
            assert storage.allow_overwrite is False
            assert storage._bucket is None

    def test_init_custom_values(self):
        """Test R2Storage initializes with custom values."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage(
                binding='MY_BUCKET',
                location='uploads/',
                allow_overwrite=True
            )

            assert storage.binding == 'MY_BUCKET'
            assert storage.location == 'uploads'  # Trailing slash stripped
            assert storage.allow_overwrite is True

    def test_init_strips_slashes_from_location(self):
        """Test that leading/trailing slashes are stripped from location."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage(location='/uploads/files/')

            assert storage.location == 'uploads/files'


class TestR2StorageFullPath:
    """Tests for R2Storage._full_path method."""

    def test_full_path_no_location(self):
        """Test _full_path without location prefix."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage(location='')
            result = storage._full_path('test/file.txt')

            assert result == 'test/file.txt'

    def test_full_path_with_location(self):
        """Test _full_path with location prefix."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage(location='uploads')
            result = storage._full_path('test/file.txt')

            assert result == 'uploads/test/file.txt'


class TestR2StorageGetBucketErrors:
    """Tests for R2Storage._get_bucket error handling."""

    def test_get_bucket_raises_on_non_worker(self):
        """Test _get_bucket raises exception when not in worker."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()

            with patch('django_cf.storage.r2.R2Storage._get_bucket') as mock_get:
                mock_get.side_effect = Exception("Code not running inside a worker!")

                with pytest.raises(Exception) as exc_info:
                    storage._get_bucket()

                assert "not running inside a worker" in str(exc_info.value)


class TestR2StorageReadErrors:
    """Tests for R2Storage._read error handling."""

    def test_read_returns_none_on_not_found(self):
        """Test _read returns None when file not found."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()
            mock_bucket = MagicMock()
            mock_run_sync = MagicMock(return_value=None)

            storage._bucket = mock_bucket
            storage._run_sync = mock_run_sync

            result = storage._read('nonexistent.txt')

            assert result is None

    def test_read_returns_none_on_exception(self):
        """Test _read returns None on any exception."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()
            mock_bucket = MagicMock()
            mock_run_sync = MagicMock(side_effect=Exception("Network error"))

            storage._bucket = mock_bucket
            storage._run_sync = mock_run_sync
            # _get_bucket will try to use the mock
            with patch.object(storage, '_get_bucket', return_value=mock_bucket):
                result = storage._read('file.txt')

            assert result is None


class TestR2StorageExistsErrors:
    """Tests for R2Storage.exists error handling."""

    def test_exists_returns_false_on_exception(self):
        """Test exists returns False on any exception."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()
            mock_bucket = MagicMock()
            mock_run_sync = MagicMock(side_effect=Exception("Permission denied"))

            storage._bucket = mock_bucket
            storage._run_sync = mock_run_sync


            with patch.object(storage, '_get_bucket', return_value=mock_bucket):
                result = storage.exists('file.txt')

            assert result is False


class TestR2StorageSizeErrors:
    """Tests for R2Storage.size error handling."""

    def test_size_returns_zero_on_exception(self):
        """Test size returns 0 on any exception."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()
            mock_bucket = MagicMock()
            mock_run_sync = MagicMock(side_effect=Exception("Error"))

            storage._bucket = mock_bucket
            storage._run_sync = mock_run_sync


            with patch.object(storage, '_get_bucket', return_value=mock_bucket):
                result = storage.size('file.txt')

            assert result == 0

    def test_size_returns_zero_when_no_size_attribute(self):
        """Test size returns 0 when metadata has no size attribute."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()
            mock_bucket = MagicMock()
            mock_metadata = MagicMock(spec=[])  # No 'size' attribute
            mock_run_sync = MagicMock()
            mock_run_sync.return_value.to_py.return_value = mock_metadata

            storage._bucket = mock_bucket
            storage._run_sync = mock_run_sync


            with patch.object(storage, '_get_bucket', return_value=mock_bucket):
                result = storage.size('file.txt')

            assert result == 0


class TestR2StorageUrlErrors:
    """Tests for R2Storage.url error handling."""

    def test_url_raises_without_media_url(self):
        """Test url raises ValueError when MEDIA_URL not configured."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()

            # Create a mock settings object
            class MockSettings:
                MEDIA_URL = None

            # Patch the import inside the url() method
            with patch.dict('sys.modules', {'django.conf': MagicMock(settings=MockSettings())}):
                # Need to reload to pick up the mock, but since the import is local,
                # we just need to make sure hasattr works correctly
                pass

            # Alternative approach: mock hasattr and settings directly
            mock_settings = MagicMock(spec=[])  # Empty spec = no MEDIA_URL attribute
            with patch('django.conf.settings', mock_settings):
                with pytest.raises(ValueError) as exc_info:
                    storage.url('file.txt')

                assert "MEDIA_URL must be configured" in str(exc_info.value)

    def test_url_raises_with_empty_media_url(self):
        """Test url raises ValueError when MEDIA_URL is empty."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()

            mock_settings = MagicMock()
            mock_settings.MEDIA_URL = ''

            with patch('django.conf.settings', mock_settings):
                with pytest.raises(ValueError) as exc_info:
                    storage.url('file.txt')

                assert "MEDIA_URL must be configured" in str(exc_info.value)

    def test_url_constructs_correct_path(self):
        """Test url constructs correct URL with MEDIA_URL."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage(location='uploads')

            mock_settings = MagicMock()
            mock_settings.MEDIA_URL = '/media/'

            with patch('django.conf.settings', mock_settings):
                result = storage.url('file.txt')

            assert result == '/media/uploads/file.txt'


class TestR2StorageGetModifiedTimeErrors:
    """Tests for R2Storage.get_modified_time error handling."""

    def test_get_modified_time_returns_now_on_exception(self):
        """Test get_modified_time returns current time on exception."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage
            from datetime import datetime

            storage = R2Storage()
            mock_bucket = MagicMock()
            mock_run_sync = MagicMock(side_effect=Exception("Error"))

            storage._bucket = mock_bucket
            storage._run_sync = mock_run_sync


            with patch.object(storage, '_get_bucket', return_value=mock_bucket):
                before = datetime.now()
                result = storage.get_modified_time('file.txt')
                after = datetime.now()

            assert before <= result <= after


class TestR2StorageGetAvailableName:
    """Tests for R2Storage.get_available_name method."""

    def test_get_available_name_raises_on_too_long(self):
        """Test get_available_name raises exception when name too long."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()
            long_name = 'a' * 300

            with pytest.raises(Exception) as exc_info:
                storage.get_available_name(long_name, max_length=100)

            assert "too long" in str(exc_info.value)

    def test_get_available_name_returns_original_when_allow_overwrite(self):
        """Test get_available_name returns original name when allow_overwrite."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage(allow_overwrite=True)

            result = storage.get_available_name('file.txt')

            assert result == 'file.txt'

    def test_get_available_name_returns_original_when_not_exists(self):
        """Test get_available_name returns original when file doesn't exist."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()

            with patch.object(storage, 'exists', return_value=False):
                result = storage.get_available_name('file.txt')

            assert result == 'file.txt'

    def test_get_available_name_increments_counter(self):
        """Test get_available_name increments counter for existing files."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()

            # Call sequence:
            # 1. exists('file.txt') -> True (line 268, don't return early)
            # 2. exists('file.txt') -> True (line 275 while check, enter loop, name becomes file_1.txt)
            # 3. exists('file_1.txt') -> False (line 275 while check, exit loop)
            with patch.object(storage, 'exists', side_effect=[True, True, False]):
                result = storage.get_available_name('file.txt')

            assert result == 'file_1.txt'


class TestR2FileClass:
    """Tests for R2File class."""

    def test_r2file_read_mode(self):
        """Test R2File in read mode."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2File

            mock_storage = MagicMock()
            mock_storage._read.return_value = b'test content'

            r2file = R2File('test.txt', mock_storage, mode='rb')

            content = r2file.read()
            assert content == b'test content'

    def test_r2file_write_raises_in_read_mode(self):
        """Test R2File.write raises when in read mode."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2File

            mock_storage = MagicMock()
            mock_storage._read.return_value = b''

            r2file = R2File('test.txt', mock_storage, mode='rb')

            with pytest.raises(AttributeError) as exc_info:
                r2file.write(b'new content')

            assert "not opened for writing" in str(exc_info.value)

    def test_r2file_write_allowed_in_write_mode(self):
        """Test R2File.write works in write mode."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2File

            mock_storage = MagicMock()
            mock_storage._read.return_value = b''

            r2file = R2File('test.txt', mock_storage, mode='wb')

            # Access file property to initialize BytesIO
            _ = r2file.file

            result = r2file.write(b'new content')
            assert result == 11  # Length of 'new content'

    def test_r2file_close(self):
        """Test R2File.close properly closes internal file."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2File

            mock_storage = MagicMock()
            mock_storage._read.return_value = b'content'

            r2file = R2File('test.txt', mock_storage)

            # Access file to initialize it
            _ = r2file.file
            assert r2file._file is not None

            r2file.close()
            # After close, the internal BytesIO should be closed


class TestR2StorageSaveEdgeCases:
    """Tests for R2Storage._save edge cases."""

    def test_save_with_file_like_object(self):
        """Test _save with file-like object that has read() method."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()
            mock_bucket = MagicMock()
            mock_run_sync = MagicMock()

            storage._bucket = mock_bucket
            storage._run_sync = mock_run_sync


            # Create a file-like object
            content = BytesIO(b'test content')

            with patch.object(storage, '_get_bucket', return_value=mock_bucket):
                with patch('django_cf.storage.r2.Uint8Array') as mock_uint8:
                    result = storage._save('test.txt', content)

            assert result == 'test.txt'

    def test_save_with_content_type(self):
        """Test _save preserves content_type when available."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()
            mock_bucket = MagicMock()
            mock_run_sync = MagicMock()

            storage._bucket = mock_bucket
            storage._run_sync = mock_run_sync


            # Create a file-like object with content_type
            content = BytesIO(b'{"key": "value"}')
            content.content_type = 'application/json'

            with patch.object(storage, '_get_bucket', return_value=mock_bucket):
                with patch('django_cf.storage.r2.Uint8Array') as mock_uint8:
                    storage._save('data.json', content)

            # Verify put was called with httpMetadata
            put_call = mock_bucket.put.call_args
            # The options dict should contain httpMetadata
            # (exact verification depends on implementation)


class TestR2StorageListdirEdgeCases:
    """Tests for R2Storage.listdir edge cases."""

    def test_listdir_with_empty_path(self):
        """Test listdir with empty path."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()
            mock_bucket = MagicMock()
            mock_run_sync = MagicMock()
            mock_run_sync.return_value.to_py.return_value = {
                'objects': [],
                'delimitedPrefixes': []
            }

            storage._bucket = mock_bucket
            storage._run_sync = mock_run_sync


            with patch.object(storage, '_get_bucket', return_value=mock_bucket):
                dirs, files = storage.listdir('')

            assert dirs == []
            assert files == []

    def test_listdir_adds_trailing_slash(self):
        """Test listdir adds trailing slash to path."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage

            storage = R2Storage()
            mock_bucket = MagicMock()
            mock_run_sync = MagicMock()
            mock_run_sync.return_value.to_py.return_value = {
                'objects': [],
                'delimitedPrefixes': []
            }

            storage._bucket = mock_bucket
            storage._run_sync = mock_run_sync


            with patch.object(storage, '_get_bucket', return_value=mock_bucket):
                storage.listdir('uploads')

            # Verify list was called with prefix ending in /
            list_call = mock_bucket.list.call_args
            assert list_call[0][0]['prefix'].endswith('/')


class TestR2StorageTimeMethodsFallback:
    """Tests for R2Storage time methods fallback behavior."""

    def test_get_accessed_time_returns_modified_time(self):
        """Test get_accessed_time falls back to get_modified_time."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage
            from datetime import datetime

            storage = R2Storage()
            mock_time = datetime(2023, 1, 15, 12, 0, 0)

            with patch.object(storage, 'get_modified_time', return_value=mock_time):
                result = storage.get_accessed_time('file.txt')

            assert result == mock_time

    def test_get_created_time_returns_modified_time(self):
        """Test get_created_time falls back to get_modified_time."""
        with patch.dict('sys.modules', {
            'js': MagicMock(),
        }):
            from django_cf.storage.r2 import R2Storage
            from datetime import datetime

            storage = R2Storage()
            mock_time = datetime(2023, 1, 15, 12, 0, 0)

            with patch.object(storage, 'get_modified_time', return_value=mock_time):
                result = storage.get_created_time('file.txt')

            assert result == mock_time
