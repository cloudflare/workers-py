import requests
from urllib.parse import urlparse, parse_qs

# Import the web_server fixture from test_worker
from .test_worker import web_server

def get_csrf_token(client, url):
    """Fetches a page and extracts the CSRF token from a form."""
    try:
        response = client.get(url, timeout=10)
        response.raise_for_status()
        body = response.text
        start_str = 'name="csrfmiddlewaretoken" value="'
        start_idx = body.find(start_str)
        if start_idx == -1:
            # Fallback for Django 5.0+ where token might be in a script tag or different structure
            # This is a simplified search and might need adjustment
            start_str_script = '"csrfToken":"'
            start_idx_script = body.find(start_str_script)
            if start_idx_script != -1:
                start_idx = start_idx_script + len(start_str_script)
                end_idx = body.find('"', start_idx)
                if end_idx != -1:
                    return body[start_idx:end_idx]
            raise ValueError("CSRF token not found in form or script.")

        start_idx += len(start_str)
        end_idx = body.find('"', start_idx)
        if end_idx == -1:
            raise ValueError("CSRF token not properly formatted in form.")
        return body[start_idx:end_idx]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching CSRF token from {url}: {e}")
        raise
    except ValueError as e:
        print(f"Error parsing CSRF token from {url}: {e}")
        raise


def test_admin_login_page_loads(web_server):
    """Test that the admin login page loads correctly."""
    admin_url = f"{web_server.base_url}/admin/login/"
    response = requests.get(admin_url, timeout=10)
    assert response.status_code == 200
    assert "Django administration" in response.text

def test_admin_dashboard_unauthorized_access(web_server):
    """Test that accessing the admin dashboard without login redirects to the login page."""
    admin_dashboard_url = f"{web_server.base_url}/admin/"
    login_url = f"{web_server.base_url}/admin/login/"

    client = requests.Session()
    # First check with allow_redirects=False to see the 302
    response_no_redirect = client.get(admin_dashboard_url, timeout=10, allow_redirects=False)
    assert response_no_redirect.status_code == 302
    location_header = response_no_redirect.headers.get("Location", "")
    # The location might be relative /admin/login/?next=/admin/ or absolute
    assert "admin/login" in location_header
    assert "next=/admin/" in location_header

    # Then check with allow_redirects=True (default) to ensure it lands on the login page
    response_followed = client.get(admin_dashboard_url, timeout=10)
    assert response_followed.status_code == 200
    assert response_followed.url.startswith(login_url) # Final URL should be the login page
    assert "Django administration" in response_followed.text # Should show the login page content

def test_admin_login_successful(web_server):
    """Test a successful login to the Django admin."""
    login_url = f"{web_server.base_url}/admin/login/"
    admin_dashboard_url = f"{web_server.base_url}/admin/"
    client = requests.Session()

    csrf_token = get_csrf_token(client, login_url)
    login_data = {
        "username": "admin",
        "password": "password",
        "csrfmiddlewaretoken": csrf_token,
        "next": "/admin/",
    }
    headers = {"Referer": login_url}
    response = client.post(login_url, data=login_data, headers=headers, timeout=10)

    assert response.status_code == 200
    assert response.url.rstrip('/') == admin_dashboard_url.rstrip('/')
    assert "Site administration" in response.text
    assert "Log out" in response.text


def test_admin_login_failed_wrong_password(web_server):
    """Test a failed login attempt with a wrong password."""
    login_url = f"{web_server.base_url}/admin/login/"
    client = requests.Session()
    csrf_token = get_csrf_token(client, login_url)
    login_data = {
        "username": "admin",
        "password": "wrongpassword",
        "csrfmiddlewaretoken": csrf_token,
        "next": "/admin/",
    }
    headers = {"Referer": login_url}
    response = client.post(login_url, data=login_data, headers=headers, timeout=10)

    assert response.status_code == 200
    assert "Please enter the correct username and password" in response.text
    assert "Log out" not in response.text

def test_admin_login_failed_wrong_username(web_server):
    """Test a failed login attempt with a non-existent username."""
    login_url = f"{web_server.base_url}/admin/login/"
    client = requests.Session()
    csrf_token = get_csrf_token(client, login_url)
    login_data = {
        "username": "nonexistentuser",
        "password": "password",
        "csrfmiddlewaretoken": csrf_token,
        "next": "/admin/",
    }
    headers = {"Referer": login_url}
    response = client.post(login_url, data=login_data, headers=headers, timeout=10)

    assert response.status_code == 200
    assert "Please enter the correct username and password" in response.text
    assert "Log out" not in response.text

def test_admin_logout(web_server):
    """Test logging out from the Django admin."""
    login_url = f"{web_server.base_url}/admin/login/"
    logout_url = f"{web_server.base_url}/admin/logout/"
    admin_dashboard_url = f"{web_server.base_url}/admin/"
    client = requests.Session()

    # 1. Log in first
    csrf_token_login = get_csrf_token(client, login_url)
    login_data = {
        "username": "admin",
        "password": "password",
        "csrfmiddlewaretoken": csrf_token_login,
        "next": "/admin/",
    }
    headers_login = {"Referer": login_url}
    response_login = client.post(login_url, data=login_data, headers=headers_login, timeout=10)
    assert response_login.status_code == 200
    assert response_login.url.rstrip('/') == admin_dashboard_url.rstrip('/')
    assert "Log out" in response_login.text

    # 2. Logout
    # Django's admin logout is a POST request.
    # We need a CSRF token. The logout link is usually on an admin page.
    # We are already on the admin dashboard (response_login.text).
    # We need a CSRF token to POST to the logout URL.
    # Django's admin pages typically have the CSRF token available in forms.
    # The `get_csrf_token` function can be used on the current page content (admin dashboard).

    # Instead of fetching logout_url via GET (which might log out prematurely or not be a page),
    # get the CSRF token from the admin dashboard page content we received after login.
    # Note: If the logout button/form is not directly on the dashboard, this might need adjustment.
    # However, CSRF token is usually available in hidden input fields on any admin page with forms.
    # A more robust way might be to parse response_login.text if get_csrf_token needs a URL.
    # For simplicity, let's assume get_csrf_token can work with the client's current cookie state
    # and fetching a known admin page (like dashboard itself again, or a specific sub-page known to have a form).
    # Re-fetching admin_dashboard_url to get a CSRF token is a safe bet.

    csrf_token_logout = get_csrf_token(client, admin_dashboard_url)

    headers_logout = {"Referer": admin_dashboard_url} # Referer should be the page from which the POST is made
    response_logout = client.post(logout_url, data={"csrfmiddlewaretoken": csrf_token_logout}, headers=headers_logout, timeout=10)

    # After a successful POST to /admin/logout/, Django typically redirects to the login page.
    # The status code of the POST response itself might be 200 (if it renders a "Logged out" page)
    # or 302 (if it immediately redirects). We should check the content of the page it lands on.
    # If it's 302, the client will follow it if allow_redirects is True (default for client.post).

    assert response_logout.status_code == 200 # Django's default logout view returns 200
    # Check for text that appears on the "Logged out" confirmation page, which is often the login page with a message.
    # For Django < 4.0, it's "Logged out". For Django 4.0+, it's "Logged out". Django 5.0 shows "Log in again" on the login page.
    assert "Logged out" in response_logout.text or "Log in again" in response_logout.text


    # 3. Verify user is logged out by trying to access an authenticated page
    response_dashboard_after_logout = client.get(admin_dashboard_url, timeout=10, allow_redirects=True) # allow_redirects is True by default for GET too
    assert response_dashboard_after_logout.status_code == 200
    assert response_dashboard_after_logout.url.startswith(login_url)
    assert "Django administration" in response_dashboard_after_logout.text
    assert "Log out" not in response_dashboard_after_logout.text
