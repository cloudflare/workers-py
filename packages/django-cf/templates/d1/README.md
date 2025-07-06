# Django D1 Template for Cloudflare Workers

This template provides a starting point for running a Django application on Cloudflare Workers, utilizing Cloudflare D1 for serverless SQL database.

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/G4brym/django-cf/tree/main/templates/d1)

## Overview

This template is pre-configured to:
- Use `django-cf` to bridge Django with Cloudflare's environment.
- Employ Cloudflare D1 as the primary data store through the `django_cf.d1_binding` database engine.
- Include a basic Django project structure within the `src/` directory.
- Provide example worker entrypoint (`src/worker.py`).

## Project Structure

```
template-root/
 |-> src/
 |    |-> manage.py             # Django management script
 |    |-> worker.py             # Cloudflare Worker entrypoint
 |    |-> app/                  # Your Django project (rename as needed)
 |    |    |-> settings.py       # Django settings, configured for D1
 |    |    |-> urls.py           # Django URLs, includes management endpoints
 |    |    |-> wsgi.py           # WSGI application
 |    |-> your_django_apps/     # Add your Django apps here
 |    |-> vendor/               # Project dependencies (managed by vendor.txt)
 |-> staticfiles/              # Collected static files (after build)
 |-> .gitignore
 |-> package.json              # For Node.js dependencies like wrangler
 |-> package-lock.json
 |-> requirements-dev.txt      # Python dev dependencies
 |-> vendor.txt                # Pip requirements for vendoring
 |-> wrangler.jsonc            # Wrangler configuration
```

## Setup and Deployment

1.  **Install Dependencies:**
    *   **Node.js & Wrangler:** Ensure you have Node.js and npm installed. Then install dependencies with this command:
        ```bash
        npm install
        ```
    *   **Python Dependencies (Vendoring):**
        List your Python dependencies (including `django` and `django-cf`) in `vendor.txt`.
        ```txt
        # vendor.txt
        django~=5.0
        django-cf
        tzdata # For timezone support
        # Add other dependencies here
        ```
        Install them into the `src/vendor` directory:
        ```bash
        pip install -t src/vendor -r vendor.txt
        ```

    *   **Python Dependencies (Local Development):**
        List your Python dev dependencies (including `django` and `django-cf`) in `requirements-dev.txt`.
        ```txt
        # requirements-dev.txt
        django==5.1.2
        django-cf
        # For local D1 API access during development (e.g., running migrations)
        # Add other dev dependencies here
        ```
        Install them:
        ```bash
        pip install -r requirements-dev.txt
        ```

2.  **Configure `wrangler.jsonc`:**
    Review and update `wrangler.jsonc` for your project. Key sections:
    *   `name`: Your worker's name.
    *   `main`: Should point to `src/worker.py`.
    *   `compatibility_date`: Keep this up-to-date.
    *   `d1_databases`:
        *   `binding`: The name used to access the D1 database in your worker (e.g., "DB").
        *   `database_name`: The name of your D1 database in the Cloudflare dashboard.
        *   `database_id`: The ID of your D1 database.
    *   `site`:
        *   `bucket`: Points to `./staticfiles` for serving static assets.
    *   `build`:
        *   `command`: `"python src/manage.py collectstatic --noinput"` to automatically collect static files during deployment.

    Example `d1_databases` configuration in `wrangler.jsonc`:
    ```jsonc
    // ... other wrangler.jsonc configurations
    "d1_databases": [
      {
        "binding": "DB", // Must match CLOUDFLARE_BINDING in Django settings
        "database_name": "my-django-db",
        "database_id": "your-d1-database-id-here"
      }
    ],
    // ...
    ```

3.  **Django Settings (`src/app/settings.py`):**
    The template should be configured to use D1 binding:
    ```python
    # src/app/settings.py
    DATABASES = {
        'default': {
            'ENGINE': 'django_cf.d1_binding',
            # This name 'DB' must match the 'binding' in your wrangler.jsonc d1_databases section
            'CLOUDFLARE_BINDING': 'DB',
        }
    }

    # Static files
    import os
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    STATIC_URL = '/static/'
    # STATIC_ROOT should point to the 'bucket' directory in wrangler.jsonc,
    # often one level above the 'src' directory.
    STATIC_ROOT = os.path.join(os.path.dirname(BASE_DIR), 'staticfiles', 'static')

    # Optional: Settings for local development using D1 API
    # You can create a separate settings_dev.py or use environment variables
    # DATABASES_DEV = {
    #     'default': {
    #         'ENGINE': 'django_cf.d1_api',
    #         'CLOUDFLARE_DATABASE_ID': '<your_database_id>',
    #         'CLOUDFLARE_ACCOUNT_ID': '<your_account_id>',
    #         'CLOUDFLARE_TOKEN': '<your_d1_api_token>',
    #     }
    # }
    ```

4.  **Worker Entrypoint (`src/worker.py`):**
    This file contains the main `on_fetch` handler for your Django application.
    ```python
    from django_cf import DjangoCFAdapter

    async def on_fetch(request, env):
        # Ensure your Django project's WSGI application is importable
        # For example, if your project is 'app' inside 'src':
        from app.wsgi import application # Import application inside on_fetch

        # The DjangoCFAdapter requires the Django application and the environment (for D1 binding)
        adapter = DjangoCFAdapter(application, env)
        return await adapter.handle_request(request)
    ```

5.  **Deploy to Cloudflare:**
    ```bash
    npx wrangler deploy
    ```
    This command will also run the `collectstatic` command if configured in `wrangler.jsonc`.

## Running Management Commands

*   **Migrations & `createsuperuser` (Local Development - Recommended for D1):**
    For D1, it's often easiest and safest to run migrations and `createsuperuser` from your local machine by configuring your development Django settings to use the D1 API.

    1.  Ensure you have `django-cf` and your other dependencies installed in your local Python environment (`pip install -r requirements-dev.txt`).
    2.  Set up your Django settings for local D1 API access. You can do this by:
        *   Creating a `settings_dev.py` and using `python src/manage.py migrate --settings=app.settings_dev`.
        *   Or, by temporarily modifying your main `settings.py` (ensure you don't commit API keys).
        *   Or, by using environment variables to supply D1 API credentials to your settings.

        Example local D1 API settings in `settings_dev.py` (place it alongside your main `settings.py`):
        ```python
        # app/settings_dev.py
        from .settings import * # Inherit base settings

        DATABASES = {
            'default': {
                'ENGINE': 'django_cf.d1_api',
                'CLOUDFLARE_DATABASE_ID': 'your-actual-d1-database-id',
                'CLOUDFLARE_ACCOUNT_ID': 'your-cloudflare-account-id',
                'CLOUDFLARE_TOKEN': 'your-cloudflare-d1-api-token', # Ensure this token has D1 Read/Write permissions
            }
        }
        ```
    3.  Run commands:
        ```bash
        # From the template root directory
        python src/manage.py migrate --settings=app.settings_dev
        python src/manage.py createsuperuser --settings=app.settings_dev
        ```

*   **Via a Worker Endpoint (Use with Extreme Caution):**
    While possible, running migrations or creating users directly via a worker endpoint is generally **not recommended for D1** due to the direct database access available locally via the D1 API. If you absolutely must, you can adapt the management command endpoints from the Durable Objects template (`src/app/urls.py`), but ensure they are **extremely well-secured**.
    The main risk is exposing sensitive operations over HTTP and potential complexities with the worker environment.

    If you choose this path, remember:
    *   The worker needs the D1 binding (`env`) passed to the `DjangoCFAdapter` and accessible to your management command functions.
    *   Secure the endpoints robustly (e.g., IP restrictions, strong authentication tokens, not just Django's `is_superuser` if the admin user might not exist yet).

## Development Notes

*   **D1 Limitations:**
    *   **Transactions are disabled** for D1. Every query is committed immediately. This is a fundamental aspect of D1.
    *   The D1 backend has some limitations compared to traditional SQLite or other SQL databases. Many advanced ORM features or direct SQL functions (especially those used in Django Admin) might not be fully supported. Refer to the `django-cf` README and official Cloudflare D1 documentation.
    *   Django Admin functionality might be limited.
*   **Local Testing with D1:**
    *   Wrangler allows local development and can simulate D1 access. `npx wrangler dev --remote` can connect to your actual D1 database for more accurate testing.
    *   Using the D1 API for local management tasks (as described above) is the most common workflow.
*   **Security:**
    *   If you implement management command endpoints on your worker, secure them rigorously.
    *   Protect your Cloudflare API tokens and credentials.

---
*For more details on `django-cf` features and configurations, refer to the main [django-cf GitHub repository](https://github.com/G4brym/django-cf).*
