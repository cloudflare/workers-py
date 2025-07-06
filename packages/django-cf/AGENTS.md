## Working with the `django-cf` Repository

This document provides guidance for AI agents working on the `django-cf` repository.

### Project Overview

`django-cf` is a Django application designed to run on Cloudflare Workers. It utilizes Cloudflare D1 for its database and Durable Objects for stateful operations. The core of this example project is located in `templates/durable-objects/`.

### Running Tests

The project uses `pnpm` for managing Node.js dependencies and running scripts. The test execution process is defined in `.github/workflows/ci.yml` and can be replicated locally as follows:

1.  **Install pnpm**: If you don't have pnpm installed, you can install it globally using npm:
    ```bash
    npm install -g pnpm
    ```
2.  **Install Project Dependencies**: Navigate to the project root and run:
    ```bash
    pnpm install
    ```
    This command installs both Node.js and Python dependencies required for the project, including those for the worker in `templates/durable-objects/`.
3.  **Set up Tests**: Run the test setup script:
    ```bash
    pnpm run setup-test
    ```
    This script typically handles tasks like installing Python development dependencies (e.g., `pytest`, Django) and setting up the Django environment within the worker.
4.  **Run Tests**: Execute the tests using:
    ```bash
    pnpm run test
    ```
    This command will execute `pytest` which, in turn, uses the `WorkerFixture` in `tests/test_worker.py`. The fixture manages the Cloudflare worker lifecycle (starting `wrangler dev`) for the integration tests.

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
*   **`no tests ran` when running `pytest`**: Ensure you are running `pytest` from the root directory of the project. If you are in a subdirectory (e.g., `templates/durable-objects/`), `pytest` might not discover the tests in the `tests/` directory. Running `pytest tests/` from the root should correctly discover and run the tests.
*   **CSRF token issues**: The `get_csrf_token` helper in `tests/test_admin.py` is a basic string parser. If Django admin templates change significantly, this helper might need updating (e.g., to use a proper HTML parser).

### Continuous Integration

A GitHub Actions workflow is configured in `.github/workflows/ci.yml`. This workflow automatically runs all tests using `pytest` on every push to any branch. It tests against Python versions 3.10, 3.11, and 3.12.

By following these guidelines, agents can contribute effectively to this repository.
