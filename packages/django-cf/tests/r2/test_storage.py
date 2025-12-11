import requests

from ..utils import r2_web_server  # NOQA


def test_r2_upload_file(r2_web_server):
    """Test uploading a file to R2 storage."""
    upload_url = f"{r2_web_server.base_url}/__r2_upload__/"
    
    # Upload a test file
    files = {'file': ('test.txt', b'Hello, R2 Storage!', 'text/plain')}
    data = {'path': 'test_uploads/test.txt'}
    response = requests.post(upload_url, files=files, data=data, timeout=10)
    
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'success'
    assert 'path' in result
    assert result['path'] == 'test_uploads/test.txt'


def test_r2_download_file(r2_web_server):
    """Test downloading a file from R2 storage."""
    # First upload a file
    upload_url = f"{r2_web_server.base_url}/__r2_upload__/"
    files = {'file': ('download_test.txt', b'Download test content', 'text/plain')}
    data = {'path': 'test_downloads/download_test.txt'}
    upload_response = requests.post(upload_url, files=files, data=data, timeout=10)
    assert upload_response.status_code == 200
    
    # Now download it
    download_url = f"{r2_web_server.base_url}/__r2_download__/"
    params = {'path': 'test_downloads/download_test.txt'}
    response = requests.get(download_url, params=params, timeout=10)
    
    assert response.status_code == 200
    assert response.content == b'Download test content'


def test_r2_file_exists(r2_web_server):
    """Test checking if a file exists in R2 storage."""
    # Upload a file first
    upload_url = f"{r2_web_server.base_url}/__r2_upload__/"
    files = {'file': ('exists_test.txt', b'Exists test', 'text/plain')}
    data = {'path': 'test_exists/exists_test.txt'}
    upload_response = requests.post(upload_url, files=files, data=data, timeout=10)
    assert upload_response.status_code == 200
    
    # Check if file exists
    exists_url = f"{r2_web_server.base_url}/__r2_exists__/"
    params = {'path': 'test_exists/exists_test.txt'}
    response = requests.get(exists_url, params=params, timeout=10)
    
    assert response.status_code == 200
    result = response.json()
    assert result['exists'] is True
    
    # Check non-existent file
    params = {'path': 'test_exists/nonexistent.txt'}
    response = requests.get(exists_url, params=params, timeout=10)
    
    assert response.status_code == 200
    result = response.json()
    assert result['exists'] is False


def test_r2_delete_file(r2_web_server):
    """Test deleting a file from R2 storage."""
    # Upload a file first
    upload_url = f"{r2_web_server.base_url}/__r2_upload__/"
    files = {'file': ('delete_test.txt', b'Delete me', 'text/plain')}
    data = {'path': 'test_delete/delete_test.txt'}
    upload_response = requests.post(upload_url, files=files, data=data, timeout=10)
    assert upload_response.status_code == 200
    
    # Verify it exists
    exists_url = f"{r2_web_server.base_url}/__r2_exists__/"
    params = {'path': 'test_delete/delete_test.txt'}
    exists_response = requests.get(exists_url, params=params, timeout=10)
    assert exists_response.json()['exists'] is True
    
    # Delete the file
    delete_url = f"{r2_web_server.base_url}/__r2_delete__/"
    data = {'path': 'test_delete/delete_test.txt'}
    response = requests.post(delete_url, data=data, timeout=10)
    
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'success'
    
    # Verify it no longer exists
    exists_response = requests.get(exists_url, params=params, timeout=10)
    assert exists_response.json()['exists'] is False


def test_r2_list_files(r2_web_server):
    """Test listing files in R2 storage."""
    # Upload multiple files
    upload_url = f"{r2_web_server.base_url}/__r2_upload__/"
    
    test_files = [
        ('test_list/file1.txt', b'Content 1'),
        ('test_list/file2.txt', b'Content 2'),
        ('test_list/subdir/file3.txt', b'Content 3'),
    ]
    
    for path, content in test_files:
        files = {'file': (path.split('/')[-1], content, 'text/plain')}
        data = {'path': path}
        response = requests.post(upload_url, files=files, data=data, timeout=10)
        assert response.status_code == 200
    
    # List files in test_list directory
    listdir_url = f"{r2_web_server.base_url}/__r2_listdir__/"
    params = {'path': 'test_list'}
    response = requests.get(listdir_url, params=params, timeout=10)
    
    assert response.status_code == 200
    result = response.json()
    assert 'directories' in result
    assert 'files' in result
    assert 'subdir' in result['directories']
    assert 'file1.txt' in result['files']
    assert 'file2.txt' in result['files']


def test_r2_file_size(r2_web_server):
    """Test getting file size from R2 storage."""
    # Upload a file with known size
    upload_url = f"{r2_web_server.base_url}/__r2_upload__/"
    content = b'This content has a specific size.'
    files = {'file': ('size_test.txt', content, 'text/plain')}
    data = {'path': 'test_size/size_test.txt'}
    upload_response = requests.post(upload_url, files=files, data=data, timeout=10)
    assert upload_response.status_code == 200
    
    # Get file size
    size_url = f"{r2_web_server.base_url}/__r2_size__/"
    params = {'path': 'test_size/size_test.txt'}
    response = requests.get(size_url, params=params, timeout=10)
    
    assert response.status_code == 200
    result = response.json()
    assert result['size'] == len(content)


def test_r2_content_type_preservation(r2_web_server):
    """Test that content type is preserved when uploading files."""
    upload_url = f"{r2_web_server.base_url}/__r2_upload__/"
    
    # Upload a JSON file
    files = {'file': ('data.json', b'{"key": "value"}', 'application/json')}
    data = {'path': 'test_content_type/data.json'}
    response = requests.post(upload_url, files=files, data=data, timeout=10)
    assert response.status_code == 200
    
    # Download and check content type (if your endpoint returns it)
    download_url = f"{r2_web_server.base_url}/__r2_download__/"
    params = {'path': 'test_content_type/data.json'}
    response = requests.get(download_url, params=params, timeout=10)
    
    assert response.status_code == 200
    assert response.content == b'{"key": "value"}'


def test_r2_overwrite_file(r2_web_server):
    """Test overwriting an existing file in R2 storage."""
    upload_url = f"{r2_web_server.base_url}/__r2_upload__/"
    path = 'test_overwrite/overwrite_test.txt'
    
    # Upload original file
    files = {'file': ('overwrite_test.txt', b'Original content', 'text/plain')}
    data = {'path': path}
    response = requests.post(upload_url, files=files, data=data, timeout=10)
    assert response.status_code == 200
    
    # Download and verify original content
    download_url = f"{r2_web_server.base_url}/__r2_download__/"
    params = {'path': path}
    response = requests.get(download_url, params=params, timeout=10)
    assert response.content == b'Original content'
    
    # Overwrite with new content
    files = {'file': ('overwrite_test.txt', b'New content', 'text/plain')}
    data = {'path': path}
    response = requests.post(upload_url, files=files, data=data, timeout=10)
    assert response.status_code == 200
    
    # Download and verify new content
    response = requests.get(download_url, params=params, timeout=10)
    assert response.content == b'New content'


def test_r2_empty_file(r2_web_server):
    """Test uploading and downloading an empty file."""
    upload_url = f"{r2_web_server.base_url}/__r2_upload__/"
    
    # Upload empty file
    files = {'file': ('empty.txt', b'', 'text/plain')}
    data = {'path': 'test_empty/empty.txt'}
    response = requests.post(upload_url, files=files, data=data, timeout=10)
    assert response.status_code == 200
    
    # Download and verify it's empty
    download_url = f"{r2_web_server.base_url}/__r2_download__/"
    params = {'path': 'test_empty/empty.txt'}
    response = requests.get(download_url, params=params, timeout=10)
    assert response.status_code == 200
    assert response.content == b''
    
    # Check size
    size_url = f"{r2_web_server.base_url}/__r2_size__/"
    response = requests.get(size_url, params=params, timeout=10)
    assert response.status_code == 200
    assert response.json()['size'] == 0
