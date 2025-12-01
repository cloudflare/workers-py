## Working with the `django-cf` Repository

This document provides guidance for AI agents working on the `django-cf` repository.

### Project Overview

`django-cf` is a Python package that integrates Django with Cloudflare services. It provides database backends for Cloudflare D1 and Durable Objects, plus middleware for Cloudflare Access authentication. Two complete example projects are provided in the `templates/` directory: one using D1 and one using Durable Objects.

### Running Tests

The project uses `npm` for Node.js dependencies and `uv` for Python dependencies. The test execution process is defined in `.github/workflows/ci.yml` and can be replicated locally as follows:

1.  **Install Dependencies**: Navigate to the project root and run:
    ```bash
    npm install
    uv sync
    ```
    This installs both Node.js and Python dependencies required for the project.
2.  **Run Tests**: Execute the tests using:
    ```bash
    pytest
    ```
    This command will execute `pytest` which uses the `WorkerFixture` in `tests/test_worker.py`. The fixture manages the Cloudflare worker lifecycle (starting `wrangler dev`) for the integration tests.

**Test Structure Details**:
*   Integration tests are located in the `tests/` directory. This directory must contain an `__init__.py` file to be treated as a package.
*   Tests use the `requests` library to make HTTP calls to the worker.
*   The `web_server` fixture (defined in `tests/test_worker.py` and available to all test files) provides the base URL for the running worker.
*   Special management URLs (e.g., `/__run_migrations__/`, `/__create_admin__/` in `templates/durable-objects/src/app/urls.py`) are available for test setup. These create an admin user with username `admin` and password `password`.

### Coding Conventions

*   Follow PEP 8 for Python code.
*   Use Ruff for linting and formatting if configured.
*   Keep tests focused and independent where possible. The admin tests in `tests/test_admin.py` rely on the admin user created via the management endpoint.

### Key Files and Directories

*   `pyproject.toml`: Defines project metadata, Python dependencies, and build settings.
*   `AGENTS.md`: This file.
*   `django_cf/`: Main package containing database backends and middleware.
    *   `db/backends/d1/`: D1 database backend implementation.
    *   `db/backends/do/`: Durable Objects database backend implementation.
    *   `middleware/`: Cloudflare Access authentication middleware.
*   `templates/d1/`: Complete Django example using D1 database.
    *   `package.json`: Node.js dependencies and npm scripts (`dev`, `deploy`).
    *   `wrangler.jsonc`: Wrangler configuration.
    *   `pyproject.toml`: Python project configuration.
    *   `src/index.py`: Worker entrypoint.
    *   `src/app/`: Django project directory.
*   `templates/durable-objects/`: Complete Django example using Durable Objects.
    *   `package.json`: Node.js dependencies and npm scripts (`dev`, `deploy`).
    *   `wrangler.jsonc`: Wrangler configuration.
    *   `pyproject.toml`: Python project configuration.
    *   `src/index.py`: Worker entrypoint.
    *   `src/app/`: Django project directory.
*   `tests/`: Contains integration tests.
    *   `__init__.py`: Makes `tests/` a Python package.
    *   `test_worker.py`: Defines the worker fixture and basic setup tests.
    *   `test_admin.py`: Contains tests for the Django admin interface.

### Workflow for Future Agents

1.  **Understand the Setup**: The `django-cf` package provides backends and middleware for Django on Cloudflare Workers. Two complete templates are provided for reference.
2.  **Dependencies First**: Always ensure both Python (`uv sync`) and Node (`npm install`) dependencies are up to date.
3.  **Database Backends**: The package supports D1 (via `django_cf.db.backends.d1`) and Durable Objects (via `django_cf.db.backends.do`).
4.  **Write Tests**: For new features, add corresponding integration tests in the `tests/` directory.
5.  **Run Tests**: Execute `pytest` to verify changes. Debug any worker startup issues by examining output from the `WorkerFixture`.
6.  **Update AGENTS.md**: If you make significant changes to the testing process, dependency management, or project structure, update this document.

### Troubleshooting Tests

*   **`worker failed to start`**:
    *   Check the `stdout` and `stderr` printed by the test fixture for errors from `wrangler dev`.
    *   Ensure `npm install` and `uv sync` completed successfully.
    *   Verify that the port selected by `get_free_port()` is indeed available.
*   **`ImportError: attempted relative import with no known parent package`**: Ensure `tests/__init__.py` exists.
*   **`no tests ran` when running `pytest`**: Ensure you are running `pytest` from the root directory of the project. If you are in a subdirectory (e.g., `templates/d1/` or `templates/durable-objects/`), `pytest` might not discover the tests in the `tests/` directory. Running `pytest tests/` from the root should correctly discover and run the tests.
*   **CSRF token issues**: The `get_csrf_token` helper in `tests/test_admin.py` is a basic string parser. If Django admin templates change significantly, this helper might need updating (e.g., to use a proper HTML parser).
*   **Database backend issues**: Remember that both D1 and Durable Objects have transactions disabled. All queries are committed immediately with no rollback capability.

### Continuous Integration

A GitHub Actions workflow is configured in `.github/workflows/ci.yml`. This workflow automatically runs all tests using `pytest` on every push to any branch. It tests against Python versions 3.10, 3.11, and 3.12.

By following these guidelines, agents can contribute effectively to this repository.
