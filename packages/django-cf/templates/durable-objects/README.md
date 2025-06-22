# Django Durable Objects Template for Cloudflare Workers

This template provides a starting point for running a Django application on Cloudflare Workers, utilizing Cloudflare Durable Objects for stateful data persistence.

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/G4brym/django-cf/tree/main/templates/durable-objects)

## Overview

This template is pre-configured to:
- Use `django-cf` to bridge Django with Cloudflare's environment.
- Employ Durable Objects as the primary data store through the `django_cf.do_binding` database engine.
- Include a basic Django project structure within the `src/` directory.
- Provide example worker entrypoint (`src/worker.py`) and Durable Object class.

## Project Structure

```
template-root/
 |-> src/
 |    |-> manage.py             # Django management script
 |    |-> worker.py             # Cloudflare Worker entrypoint & Durable Object class
 |    |-> app/                  # Your Django project (rename as needed)
 |    |    |-> settings.py       # Django settings, configured for DO
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
    *   `durable_objects`:
        *   `bindings`: Ensure `name` (e.g., "DO_STORAGE") and `class_name` (e.g., "DjangoDO") are correctly set.
        *   `migrations`: Define migrations for your Durable Object classes if you add or change them.
    *   `site`:
        *   `bucket`: Points to `./staticfiles` for serving static assets.
    *   `build`: (To be added if not present)
        *   `command`: `"python src/manage.py collectstatic --noinput"` to automatically collect static files during deployment.

3.  **Django Settings (`src/app/settings.py`):**
    The template is pre-configured to use Durable Objects:
    ```python
    # src/app/settings.py
    DATABASES = {
        'default': {
            'ENGINE': 'django_cf.do_binding',
        }
    }

    # Static files
    import os
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    STATIC_URL = '/static/'
    # STATIC_ROOT should point to the 'bucket' directory in wrangler.jsonc,
    # often one level above the 'src' directory.
    STATIC_ROOT = os.path.join(os.path.dirname(BASE_DIR), 'staticfiles', 'static')
    ```

4.  **Worker Entrypoint (`src/worker.py`):**
    This file contains your Durable Object class (`DjangoDO`) and the main `on_fetch` handler.
    ```python
    from django_cf import DjangoCFDurableObject
    from workers import DurableObject # Standard Cloudflare DurableObject base

    class DjangoDO(DjangoCFDurableObject, DurableObject):
        def get_app(self):
            # Your Django project's WSGI application (ensure 'app' matches your project name)
            from app.wsgi import application
            return application
        # You can add custom methods to your Durable Object here

    # Main fetch handler for the worker
    async def on_fetch(request, env):
        # This example routes all requests to a single DO instance (singleton).
        # For multi-tenant apps, derive 'name' from the request (e.g., user ID, path segment).
        # The DO_STORAGE binding name here must match what's in wrangler.jsonc
        do_id = env.DO_STORAGE.idFromName("singleton_instance")
        stub = env.DO_STORAGE.get(do_id)
        return await stub.fetch(request) # Forward the request to the Durable Object
    ```

5.  **Deploy to Cloudflare:**
    ```bash
    npx wrangler deploy
    ```
    This command will also run the `collectstatic` command if configured in `wrangler.jsonc`.

## Running Management Commands

Since this template uses Durable Objects, standard Django management commands like `migrate` or `createsuperuser` cannot be run directly against the deployed DO instances from your local machine in the same way you might with D1 via the API.

This template provides special URL endpoints to trigger these commands on the deployed worker. **These endpoints must be properly secured.**

*   **`/__run_migrations__/`**: Triggers the `migrate` command.
*   **`/__create_admin__/`**: Creates a superuser (username: 'admin', email: 'admin@example.com', password: 'yoursecurepassword' - change this!).

These endpoints are defined in `src/app/urls.py` and are protected by `user_passes_test(is_superuser)`. This means you must first create an admin user and be logged in as that user to access these endpoints.

**Initial Admin User Creation:**
For the very first admin user creation, you might need to temporarily remove the `@user_passes_test(is_superuser)` decorator from `create_admin_view` in `src/app/urls.py`, deploy, access `/__create_admin__/`, and then reinstate the decorator and redeploy. Alternatively, modify the `create_admin_view` to accept a secure token or other mechanism for the initial setup if direct unauthenticated access is undesirable.

**Accessing the Endpoints:**
Once deployed and an admin user exists (and you are logged in as them via Django's admin interface, for example):
- Visit `https://your-worker-url.com/__run_migrations__/` to apply migrations.
- Visit `https://your-worker-url.com/__create_admin__/` to (re)create the admin user if needed.

Check the JSON response in your browser to see the status of the command.

## Development Notes

*   **Durable Object State:** Remember that Durable Objects maintain state. If you make significant changes to your Django models or how state is managed, you might need to consider strategies for migrating or resetting DO state. This can involve clearing storage for specific DO instances or implementing data migration logic within your DO or Django application.
*   **Local Testing:** Testing Durable Objects locally can be challenging. Wrangler provides some local development capabilities, but fully emulating the Cloudflare environment can be complex.
*   **Security:** Pay close attention to the security of your management endpoints. The provided `user_passes_test` is a basic protection; consider more robust authentication/authorization if needed, especially for production environments.
```
