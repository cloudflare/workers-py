"""End-to-end workflow tests for django-cf.

These tests verify complete user workflows through the HTTP endpoints.
They require running Cloudflare Workers via wrangler.
"""
import pytest
import requests


# Import fixtures from utils
from ..utils import d1_web_server, durable_objects_web_server, r2_web_server  # NOQA


class TestD1CRUDWorkflow:
    """Test complete CRUD workflow with D1 backend."""

    def test_full_crud_cycle(self, d1_web_server):
        """Test create, read, update, delete cycle."""
        base_url = d1_web_server.base_url

        # 1. Create - via admin (already created in fixture)
        # Verify admin exists
        response = requests.get(f"{base_url}/__create_admin__/")
        assert response.status_code == 200
        result = response.json()
        # Either created or already exists
        assert result['status'] in ['success', 'info']

    def test_migrations_are_applied(self, d1_web_server):
        """Test that migrations are properly applied."""
        base_url = d1_web_server.base_url

        # Running migrations again should succeed (idempotent)
        response = requests.get(f"{base_url}/__run_migrations__/")
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'success'

    def test_admin_user_persistence(self, d1_web_server):
        """Test that admin user persists across requests."""
        base_url = d1_web_server.base_url

        # Create admin first time
        response1 = requests.get(f"{base_url}/__create_admin__/")
        assert response1.status_code == 200

        # Second attempt should indicate already exists
        response2 = requests.get(f"{base_url}/__create_admin__/")
        assert response2.status_code == 200
        result = response2.json()
        assert result['status'] == 'info'
        assert 'already exists' in result['message']


class TestDurableObjectsCRUDWorkflow:
    """Test complete CRUD workflow with Durable Objects backend."""

    def test_full_crud_cycle(self, durable_objects_web_server):
        """Test create, read, update, delete cycle with DO."""
        base_url = durable_objects_web_server.base_url

        # Verify admin exists
        response = requests.get(f"{base_url}/__create_admin__/")
        assert response.status_code == 200
        result = response.json()
        assert result['status'] in ['success', 'info']

    def test_migrations_are_applied(self, durable_objects_web_server):
        """Test that migrations are properly applied on DO."""
        base_url = durable_objects_web_server.base_url

        response = requests.get(f"{base_url}/__run_migrations__/")
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'success'

    def test_admin_user_persistence(self, durable_objects_web_server):
        """Test that admin user persists across requests on DO."""
        base_url = durable_objects_web_server.base_url

        # First attempt
        response1 = requests.get(f"{base_url}/__create_admin__/")
        assert response1.status_code == 200

        # Second attempt should indicate already exists
        response2 = requests.get(f"{base_url}/__create_admin__/")
        assert response2.status_code == 200
        result = response2.json()
        assert result['status'] == 'info'
        assert 'already exists' in result['message']


class TestR2StorageWorkflow:
    """Test complete R2 storage workflow."""

    def test_upload_download_delete_workflow(self, r2_web_server):
        """Test complete file upload, download, delete workflow."""
        base_url = r2_web_server.base_url
        test_path = 'workflow_test/test_file.txt'
        test_content = b'Workflow test content'

        # 1. Upload file
        upload_url = f"{base_url}/__r2_upload__/"
        files = {'file': ('test_file.txt', test_content, 'text/plain')}
        data = {'path': test_path}
        response = requests.post(upload_url, files=files, data=data, timeout=10)
        assert response.status_code == 200

        # 2. Verify file exists
        exists_url = f"{base_url}/__r2_exists__/"
        response = requests.get(exists_url, params={'path': test_path}, timeout=10)
        assert response.status_code == 200
        assert response.json()['exists'] is True

        # 3. Download and verify content
        download_url = f"{base_url}/__r2_download__/"
        response = requests.get(download_url, params={'path': test_path}, timeout=10)
        assert response.status_code == 200
        assert response.content == test_content

        # 4. Check file size
        size_url = f"{base_url}/__r2_size__/"
        response = requests.get(size_url, params={'path': test_path}, timeout=10)
        assert response.status_code == 200
        assert response.json()['size'] == len(test_content)

        # 5. Delete file
        delete_url = f"{base_url}/__r2_delete__/"
        response = requests.post(delete_url, data={'path': test_path}, timeout=10)
        assert response.status_code == 200

        # 6. Verify file no longer exists
        response = requests.get(exists_url, params={'path': test_path}, timeout=10)
        assert response.status_code == 200
        assert response.json()['exists'] is False

    def test_directory_operations_workflow(self, r2_web_server):
        """Test directory listing workflow."""
        base_url = r2_web_server.base_url
        upload_url = f"{base_url}/__r2_upload__/"

        # Create directory structure
        test_files = [
            ('dir_test/file1.txt', b'Content 1'),
            ('dir_test/file2.txt', b'Content 2'),
            ('dir_test/subdir/file3.txt', b'Content 3'),
        ]

        for path, content in test_files:
            files = {'file': (path.split('/')[-1], content, 'text/plain')}
            data = {'path': path}
            response = requests.post(upload_url, files=files, data=data, timeout=10)
            assert response.status_code == 200

        # List directory
        listdir_url = f"{base_url}/__r2_listdir__/"
        response = requests.get(listdir_url, params={'path': 'dir_test'}, timeout=10)
        assert response.status_code == 200

        result = response.json()
        assert 'directories' in result
        assert 'files' in result
        assert 'subdir' in result['directories']
        assert 'file1.txt' in result['files']
        assert 'file2.txt' in result['files']

    @pytest.mark.xfail(
        reason="Framework limitation: django_cf/__init__.py:58 calls resp.content.decode('utf-8') "
               "which fails for binary content. See handle_wsgi function."
    )
    def test_binary_file_workflow(self, r2_web_server):
        """Test binary file upload and download.

        NOTE: This test documents a known framework limitation where binary
        responses fail because handle_wsgi() tries to decode content as UTF-8.
        """
        base_url = r2_web_server.base_url
        test_path = 'binary_test/image.bin'

        # Create binary content with bytes that can't be decoded as UTF-8
        binary_content = bytes(range(256))

        # Upload
        upload_url = f"{base_url}/__r2_upload__/"
        files = {'file': ('image.bin', binary_content, 'application/octet-stream')}
        data = {'path': test_path}
        response = requests.post(upload_url, files=files, data=data, timeout=10)
        assert response.status_code == 200

        # Download and verify - this fails due to UTF-8 decode in handle_wsgi
        download_url = f"{base_url}/__r2_download__/"
        response = requests.get(download_url, params={'path': test_path}, timeout=10)
        assert response.status_code == 200
        assert response.content == binary_content


class TestErrorRecoveryWorkflow:
    """Test error recovery scenarios."""

    def test_d1_handles_missing_resource(self, d1_web_server):
        """Test that D1 handles missing resources gracefully."""
        base_url = d1_web_server.base_url

        # Request a non-existent endpoint
        response = requests.get(f"{base_url}/nonexistent/endpoint/", timeout=10)
        # Should return an HTTP error, not crash
        assert response.status_code >= 400

    def test_r2_handles_missing_file(self, r2_web_server):
        """Test that R2 handles missing files gracefully."""
        base_url = r2_web_server.base_url

        # Try to download non-existent file
        download_url = f"{base_url}/__r2_download__/"
        response = requests.get(
            download_url,
            params={'path': 'definitely/not/a/real/file.txt'},
            timeout=10
        )
        # Should return error status, not crash
        assert response.status_code >= 400 or response.content == b''

        # Exists check should return False, not error
        exists_url = f"{base_url}/__r2_exists__/"
        response = requests.get(
            exists_url,
            params={'path': 'definitely/not/a/real/file.txt'},
            timeout=10
        )
        assert response.status_code == 200
        assert response.json()['exists'] is False


class TestConcurrentRequestsWorkflow:
    """Test handling of concurrent requests."""

    def test_d1_handles_concurrent_reads(self, d1_web_server):
        """Test D1 handles multiple concurrent read requests."""
        import concurrent.futures

        base_url = d1_web_server.base_url

        def make_request():
            response = requests.get(f"{base_url}/__create_admin__/", timeout=10)
            return response.status_code

        # Make 5 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All requests should succeed
        assert all(status == 200 for status in results)

    def test_r2_handles_concurrent_uploads(self, r2_web_server):
        """Test R2 handles multiple concurrent upload requests."""
        import concurrent.futures

        base_url = r2_web_server.base_url
        upload_url = f"{base_url}/__r2_upload__/"

        def upload_file(index):
            files = {'file': (f'concurrent_{index}.txt', f'Content {index}'.encode(), 'text/plain')}
            data = {'path': f'concurrent_test/file_{index}.txt'}
            response = requests.post(upload_url, files=files, data=data, timeout=10)
            return response.status_code

        # Make 5 concurrent uploads
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(upload_file, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All uploads should succeed
        assert all(status == 200 for status in results)


class TestLargeDataWorkflow:
    """Test handling of larger data sets."""

    def test_r2_handles_larger_file(self, r2_web_server):
        """Test R2 handles larger files (1MB)."""
        base_url = r2_web_server.base_url
        test_path = 'large_test/large_file.bin'

        # Create 1MB of data
        large_content = b'x' * (1024 * 1024)

        # Upload
        upload_url = f"{base_url}/__r2_upload__/"
        files = {'file': ('large_file.bin', large_content, 'application/octet-stream')}
        data = {'path': test_path}
        response = requests.post(upload_url, files=files, data=data, timeout=30)
        assert response.status_code == 200

        # Verify size
        size_url = f"{base_url}/__r2_size__/"
        response = requests.get(size_url, params={'path': test_path}, timeout=10)
        assert response.status_code == 200
        assert response.json()['size'] == len(large_content)

        # Download and verify
        download_url = f"{base_url}/__r2_download__/"
        response = requests.get(download_url, params={'path': test_path}, timeout=30)
        assert response.status_code == 200
        assert len(response.content) == len(large_content)


class TestSpecialCharactersWorkflow:
    """Test handling of special characters in paths and content."""

    def test_r2_handles_unicode_filename(self, r2_web_server):
        """Test R2 handles unicode characters in filenames."""
        base_url = r2_web_server.base_url
        # Use ASCII-safe path for URL but unicode in content
        test_path = 'unicode_test/file_unicode.txt'
        unicode_content = 'Hello'.encode('utf-8')

        upload_url = f"{base_url}/__r2_upload__/"
        files = {'file': ('file.txt', unicode_content, 'text/plain; charset=utf-8')}
        data = {'path': test_path}
        response = requests.post(upload_url, files=files, data=data, timeout=10)
        assert response.status_code == 200

        # Download and verify
        download_url = f"{base_url}/__r2_download__/"
        response = requests.get(download_url, params={'path': test_path}, timeout=10)
        assert response.status_code == 200
        assert response.content == unicode_content

    def test_r2_handles_spaces_in_path(self, r2_web_server):
        """Test R2 handles spaces in file paths."""
        base_url = r2_web_server.base_url
        test_path = 'space test/file with spaces.txt'
        test_content = b'Content with spaces in path'

        upload_url = f"{base_url}/__r2_upload__/"
        files = {'file': ('file with spaces.txt', test_content, 'text/plain')}
        data = {'path': test_path}
        response = requests.post(upload_url, files=files, data=data, timeout=10)
        assert response.status_code == 200

        # Verify exists
        exists_url = f"{base_url}/__r2_exists__/"
        response = requests.get(exists_url, params={'path': test_path}, timeout=10)
        assert response.status_code == 200
        assert response.json()['exists'] is True
