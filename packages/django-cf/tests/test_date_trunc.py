import requests
from datetime import datetime, timedelta
from .utils import r2_web_server  # NOQA


def test_date_trunc_month(r2_web_server):
    """Test truncating dates to month."""
    base_url = r2_web_server.base_url
    
    # Clear any existing transactions
    requests.post(f"{base_url}/__date_trunc_clear_transactions__/", timeout=10)
    
    # Create test transactions
    requests.post(f"{base_url}/__date_trunc_create_transaction__/", data={'description': 'Transaction 1'}, timeout=10)
    requests.post(f"{base_url}/__date_trunc_create_transaction__/", data={'description': 'Transaction 2'}, timeout=10)
    
    # Test month truncation
    response = requests.get(f"{base_url}/__date_trunc_test__/", params={'type': 'month'}, timeout=10)
    
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'success'
    assert result['type'] == 'month'
    assert len(result['results']) > 0
    assert all(isinstance(r, str) for r in result['results'])


def test_date_trunc_year(r2_web_server):
    """Test truncating dates to year."""
    base_url = r2_web_server.base_url
    
    # Clear any existing transactions
    requests.post(f"{base_url}/__date_trunc_clear_transactions__/", timeout=10)
    
    # Create test transactions
    requests.post(f"{base_url}/__date_trunc_create_transaction__/", data={'description': 'Transaction 1'}, timeout=10)
    
    # Test year truncation
    response = requests.get(f"{base_url}/__date_trunc_test__/", params={'type': 'year'}, timeout=10)
    
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'success'
    assert result['type'] == 'year'
    assert len(result['results']) > 0


def test_date_trunc_day(r2_web_server):
    """Test truncating dates to day."""
    base_url = r2_web_server.base_url
    
    # Clear any existing transactions
    requests.post(f"{base_url}/__date_trunc_clear_transactions__/", timeout=10)
    
    # Create test transactions
    requests.post(f"{base_url}/__date_trunc_create_transaction__/", data={'description': 'Transaction 1'}, timeout=10)
    
    # Test day truncation
    response = requests.get(f"{base_url}/__date_trunc_test__/", params={'type': 'day'}, timeout=10)
    
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'success'
    assert result['type'] == 'day'
    assert len(result['results']) > 0


def test_date_trunc_quarter(r2_web_server):
    """Test truncating dates to quarter."""
    base_url = r2_web_server.base_url
    
    # Clear any existing transactions
    requests.post(f"{base_url}/__date_trunc_clear_transactions__/", timeout=10)
    
    # Create test transactions
    requests.post(f"{base_url}/__date_trunc_create_transaction__/", data={'description': 'Transaction 1'}, timeout=10)
    
    # Test quarter truncation
    response = requests.get(f"{base_url}/__date_trunc_test__/", params={'type': 'quarter'}, timeout=10)
    
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'success'
    assert result['type'] == 'quarter'
    assert len(result['results']) > 0


def test_date_trunc_week(r2_web_server):
    """Test truncating dates to week."""
    base_url = r2_web_server.base_url
    
    # Clear any existing transactions
    requests.post(f"{base_url}/__date_trunc_clear_transactions__/", timeout=10)
    
    # Create test transactions
    requests.post(f"{base_url}/__date_trunc_create_transaction__/", data={'description': 'Transaction 1'}, timeout=10)
    
    # Test week truncation
    response = requests.get(f"{base_url}/__date_trunc_test__/", params={'type': 'week'}, timeout=10)
    
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'success'
    assert result['type'] == 'week'
    assert len(result['results']) > 0


def test_date_trunc_hour(r2_web_server):
    """Test truncating dates to hour."""
    base_url = r2_web_server.base_url
    
    # Clear any existing transactions
    requests.post(f"{base_url}/__date_trunc_clear_transactions__/", timeout=10)
    
    # Create test transactions
    requests.post(f"{base_url}/__date_trunc_create_transaction__/", data={'description': 'Transaction 1'}, timeout=10)
    
    # Test hour truncation
    response = requests.get(f"{base_url}/__date_trunc_test__/", params={'type': 'hour'}, timeout=10)
    
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'success'
    assert result['type'] == 'hour'
    assert len(result['results']) > 0


def test_date_trunc_invalid_type(r2_web_server):
    """Test that invalid truncation type returns error."""
    base_url = r2_web_server.base_url
    
    # Test invalid truncation type
    response = requests.get(f"{base_url}/__date_trunc_test__/", params={'type': 'invalid'}, timeout=10)
    
    assert response.status_code == 400
    result = response.json()
    assert result['status'] == 'error'
    assert 'Invalid truncation type' in result['message']


def test_date_trunc_create_and_clear_transactions(r2_web_server):
    """Test creating and clearing transactions."""
    base_url = r2_web_server.base_url
    
    # Clear any existing transactions
    response = requests.post(f"{base_url}/__date_trunc_clear_transactions__/", timeout=10)
    assert response.status_code == 200
    assert response.json()['status'] == 'success'
    
    # Create a transaction
    response = requests.post(f"{base_url}/__date_trunc_create_transaction__/", data={'description': 'Test Transaction'}, timeout=10)
    assert response.status_code == 200
    assert response.json()['status'] == 'success'
    
    # Verify transaction was created by querying
    response = requests.get(f"{base_url}/__date_trunc_test__/", params={'type': 'month'}, timeout=10)
    assert response.status_code == 200
    assert len(response.json()['results']) > 0
    
    # Clear transactions
    response = requests.post(f"{base_url}/__date_trunc_clear_transactions__/", timeout=10)
    assert response.status_code == 200
    
    # Verify transactions were cleared
    response = requests.get(f"{base_url}/__date_trunc_test__/", params={'type': 'month'}, timeout=10)
    assert response.status_code == 200
    assert len(response.json()['results']) == 0
