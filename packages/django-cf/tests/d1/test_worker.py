import requests

from ..utils import d1_web_server  # NOQA

def test_migrations(d1_web_server):
    """Run migrations."""
    response = requests.get(f"{d1_web_server.base_url}/__run_migrations__/")
    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Migrations applied."}

def test_create_admin(d1_web_server):
    """Create an admin user a second time should return different state."""
    response = requests.get(f"{d1_web_server.base_url}/__create_admin__/")
    assert response.status_code == 200
    assert response.json() == {"status": "info", "message": f"Admin user 'admin' already exists."}

