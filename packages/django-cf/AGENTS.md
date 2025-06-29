## Working with the `django-cf` Repository

This document provides guidance for AI agents working on the `django-cf` repository.

### Project Overview

`django-cf` is a Django application designed to run on Cloudflare Workers. It utilizes Cloudflare D1 for its database and Durable Objects for stateful operations. The core of this example project is located in `templates/durable-objects/`.

### Dependencies

*   **Node.js/npm:** Required for the Cloudflare Wrangler CLI.
    *   The main `npm install` in the project root is for general tooling if specified.
    *   The worker itself, located in `templates/durable-objects/`, has its own `package.json`. Ensure dependencies there (especially `wrangler`) are installed by running `npm install` within the `templates/durable-objects/` directory.
*   **Python/pip:** Required for Django and other Python packages.
    *   Install project and development dependencies from the root `pyproject.toml` using `pip install -e .[dev]`.
    *   Ensure `pyproject.toml` correctly defines `[project.optional-dependencies]` for the `dev` group (e.g., `pytest`, `django`).

### Running Tests

1.  **Prerequisites**: Ensure all dependencies are installed as per the "Dependencies" section.
2.  **Worker Server**: Tests rely on a running Cloudflare worker. The `tests/test_worker.py` file includes a `WorkerFixture` that handles:
    *   Running `npm install` in `templates/durable-objects/`.
    *   Starting the `npx wrangler dev` server using the version of `wrangler` specified in `templates/durable-objects/package.json`.
3.  **Execute Pytest**: Run tests using the `pytest` command from the root of the repository.
4.  **Test Structure**:
    *   Integration tests are located in the `tests/` directory. This directory must contain an `__init__.py` file to be treated as a package.
    *   Tests use the `requests` library to make HTTP calls to the worker.
    *   The `web_server` fixture (defined in `tests/test_worker.py` and available to all test files) provides the base URL for the running worker.
    *   Special management URLs (e.g., `/__run_migrations__/`, `/__create_admin__/` in `templates/durable-objects/src/app/urls.py`) are available for test setup. These create an admin user with username `admin` and password `password`.

### Coding Conventions

*   Follow PEP 8 for Python code.
*   Use Ruff for linting and formatting if configured.
*   Keep tests focused and independent where possible. The admin tests in `tests/test_admin.py` rely on the admin user created via the management endpoint.

### Key Files and Directories

*   `pyproject.toml`: Defines project metadata, Python dependencies, and build settings for the wrapper/library aspects.
*   `AGENTS.md`: This file.
*   `templates/durable-objects/`: Contains the actual Django application deployed to Cloudflare.
    *   `package.json`: Node.js dependencies for the worker, including `wrangler`.
    *   `wrangler.toml` (or `wrangler.jsonc`): Wrangler configuration file.
    *   `src/worker.py`: Python entry point for the worker, using `django-cf` library components.
    *   `src/app/`: Standard Django project directory.
        *   `settings.py`: Django settings.
        *   `urls.py`: Django URL configurations, including admin and management endpoints.
*   `tests/`: Contains integration tests.
    *   `__init__.py`: Makes `tests/` a Python package.
    *   `test_worker.py`: Defines the worker fixture and basic setup tests (migrations, admin creation).
    *   `test_admin.py`: Contains tests for the Django admin interface (login, logout, etc.).

### Workflow for Future Agents

1.  **Understand the Setup**: The Django app runs inside a Cloudflare Worker, managed by Wrangler. Tests interact with this via HTTP.
2.  **Dependencies First**: Always ensure both Python (`pip install -e .[dev]`) and Node (`npm install` in the root and `templates/durable-objects/`) dependencies are up to date.
3.  **Write Tests**: For new Django views or functionalities within `templates/durable-objects/src/app/`, add corresponding integration tests in the `tests/` directory.
4.  **Run Tests**: Execute `pytest` to verify changes. Debug any worker startup issues by examining output from the `WorkerFixture`.
5.  **Update AGENTS.md**: If you make significant changes to the testing process, dependency management, or project structure, update this document.

### Troubleshooting Tests

*   **`worker failed to start`**:
    *   Check the `stdout` and `stderr` printed by the test fixture for errors from `wrangler dev`.
    *   Ensure `npm install` completed successfully in `templates/durable-objects/`.
    *   Verify that the port selected by `get_free_port()` is indeed available.
*   **`ImportError: attempted relative import with no known parent package`**: Ensure `tests/__init__.py` exists.
*   **CSRF token issues**: The `get_csrf_token` helper in `tests/test_admin.py` is a basic string parser. If Django admin templates change significantly, this helper might need updating (e.g., to use a proper HTML parser).

By following these guidelines, agents can contribute effectively to this repository.
