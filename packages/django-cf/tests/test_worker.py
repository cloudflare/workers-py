import os
import signal
import socket
import subprocess
import time

import pytest
import requests


def get_free_port():
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


class WorkerFixture:
    def __init__(self):
        self.process = None
        self.port = None
        self.base_url = None

    def start(self):
        """Start the worker in a subprocess."""
        self.port = get_free_port()
        self.base_url = f"http://localhost:{self.port}"

        # Start the worker as a subprocess
        # Use the wrangler version from package.json by omitting @latest
        cmd = f"cd templates/durable-objects/ && npm install && npx wrangler dev --port {self.port}"
        self.process = subprocess.Popen(
            cmd,
            shell=True,
            preexec_fn=os.setsid,  # So we can kill the process group later
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Wait for server to start
        server_started = self._wait_for_server()

        if not server_started:
            stdout, stderr = self.process.communicate()
            self.stop() # Ensure process is stopped
            raise Exception(
                f"worker failed to start on port {self.port}.\n"
                f"Stdout:\n{stdout}\n"
                f"Stderr:\n{stderr}"
            )

        return self

    def _wait_for_server(self, max_retries=20, retry_interval=1): # Increased max_retries
        """Wait until the server is responding to requests. Returns True if server started, False otherwise."""
        for i in range(max_retries):
            # Check if the process terminated unexpectedly
            if self.process.poll() is not None:
                # Process has terminated
                print(f"Wrangler process terminated prematurely with code {self.process.returncode}.")
                return False
            try:
                response = requests.get(self.base_url, timeout=10) # Reduced individual timeout
                if response.status_code < 500:  # Accept any non-server error response
                    print(f"Server started on {self.base_url} after {i+1} retries.")
                    return True
            except requests.exceptions.RequestException as e:
                # print(f"Retry {i+1}/{max_retries}: Server not up yet ({e})")
                pass

            time.sleep(retry_interval)

        print(f"Server did not start on {self.base_url} after {max_retries} retries.")
        return False

    def stop(self):
        """Stop the worker."""
        if self.process:
            # Kill the process group (including any child processes)
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self.process = None


@pytest.fixture(scope="session")
def web_server():
    """Pytest fixture that starts the worker for the entire test session."""
    server = WorkerFixture()
    server.start()
    yield server
    server.stop()


def test_migrations(web_server):
    """Run migrations."""
    response = requests.get(f"{web_server.base_url}/__run_migrations__/")
    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Migrations applied."}

def test_create_admin(web_server):
    """Create an admin user."""
    response = requests.get(f"{web_server.base_url}/__create_admin__/")
    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": f"Admin user 'admin' created."}

def test_create_admin_again(web_server):
    """Create an admin user a second time should return different state."""
    response = requests.get(f"{web_server.base_url}/__create_admin__/")
    assert response.status_code == 200
    assert response.json() == {"status": "info", "message": f"Admin user 'admin' already exists."}

