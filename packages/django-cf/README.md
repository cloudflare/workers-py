# django-cf

`django-cf` is a Python package that seamlessly integrates your Django applications with various Cloudflare services. Utilize the power of Cloudflare's global network for your Django projects.

## Installation

```bash
pip install django-cf
```

## Features

This package provides integration with the following Cloudflare products:

*   **Cloudflare Workers**: Run your Django application on Cloudflare's serverless compute platform.
*   **Cloudflare D1**: Use Cloudflare's serverless SQL database as a backend for your Django application.
*   **Cloudflare Durable Objects**: Leverage stateful objects for applications requiring persistent state within Cloudflare Workers.

### 1. Cloudflare Workers Integration

Run your Django application directly on Cloudflare Workers for edge performance and scalability.

**Suggested Project Structure:**

```
root
 |-> src/
 |    |-> manage.py
 |    |-> worker.py               <-- Wrangler entrypoint
 |    |-> your_django_project/
 |    |-> your_django_apps/
 |    |-> vendor/                 <-- Project dependencies
 |-> staticfiles/                <-- Collected static files
 |-> vendor.txt                  <-- Pip requirements for vendoring
 |-> wrangler.toml               <-- Wrangler configuration (or wrangler.jsonc)
```

**Configuration Steps:**

1.  **`vendor.txt` (Dependencies):**
    List your project dependencies, including `django-cf`.
    ```txt
    django~=5.0 # Or your desired Django version
    django-cf
    tzdata # Often required for timezone support
    ```

2.  **Vendor Dependencies:**
    Install dependencies into the `src/vendor` directory.
    ```bash
    pip install -t src/vendor -r vendor.txt
    ```

3.  **`wrangler.toml` (or `wrangler.jsonc`):**
    Configure your Cloudflare Worker. Below is an example using `wrangler.toml`.
    ```toml
    name = "django-on-workers"
    main = "src/worker.py"
    compatibility_date = "2024-03-20" # Update to a recent date

    compatibility_flags = [ "python_workers" ]

    # Configuration for serving static assets
    [site]
    bucket = "./staticfiles"

    # Rules for including vendored Python packages
    [[rules]]
    globs = ["vendor/**/*.py", "vendor/**/*.mo", "vendor/tzdata/**/"]
    type = "Data"
    fallthrough = true

    # Example: D1 Database binding (if using D1)
    [[d1_databases]]
    binding = "DB" # Name used to access the DB in your worker
    database_name = "my-django-db"
    database_id = "your-d1-database-id" # Replace with your actual D1 DB ID

    [build]
    command = "python src/manage.py collectstatic --noinput"
    ```
    *Note: If using `wrangler.jsonc`, adapt the TOML structure to JSON.*

4.  **`src/worker.py` (Worker Entrypoint):**
    Use `DjangoCFAdapter` to handle requests.
    ```python
    from django_cf import DjangoCFAdapter
    # Ensure your Django project's WSGI application is importable
    # For example, if your project is 'myproject' inside 'src':
    from myproject.wsgi import application

    async def on_fetch(request, env):
        # Optionally, pass 'env' if your Django app needs access to bindings
        adapter = DjangoCFAdapter(application, env_vars=env)
        return await adapter.handle_request(request)
    ```

5.  **Django Settings (`settings.py`):**
    *   **Static Files:** Configure Django to collect static files into the directory specified in `wrangler.toml`.
        ```python
        # settings.py
        import os
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        STATIC_URL = '/static/'
        # STATIC_ROOT should point to the 'bucket' directory in wrangler.toml,
        # often one level above the 'src' directory.
        STATIC_ROOT = os.path.join(os.path.dirname(BASE_DIR), 'staticfiles', 'static')
        ```
    *   **Database (if using D1 or Durable Objects):** See the respective sections below.

6.  **Collect Static Files & Deploy:**
    ```bash
    python src/manage.py collectstatic
    npx wrangler deploy
    ```

**Running Management Commands (including Migrations):**

*   **Local Development (Recommended for D1):**
    For D1, it's often easier to run migrations from your local machine by configuring your development Django settings to use the D1 API.
    ```python
    # settings_dev.py (example for local D1 API access)
    DATABASES = {
        'default': {
            'ENGINE': 'django_cf.d1_api',
            'CLOUDFLARE_DATABASE_ID': '<your_database_id>',
            'CLOUDFLARE_ACCOUNT_ID': '<your_account_id>',
            'CLOUDFLARE_TOKEN': '<your_d1_api_token>',
        }
    }
    ```
    Then run: `python src/manage.py migrate --settings=myproject.settings_dev`

*   **Via a Worker Endpoint (Use with Caution):**
    You can create a special endpoint in your Django app to trigger migrations on the deployed worker. **Secure this endpoint properly!**
    ```python
    # urls.py
    from django.urls import path
    from django.http import JsonResponse
    from django.core.management import call_command
    from django.contrib.auth.decorators import user_passes_test # Example for security

    def is_superuser(user):
        return user.is_superuser

    @user_passes_test(is_superuser) # Protect this endpoint!
    def run_migrations_view(request):
        try:
            call_command("migrate")
            return JsonResponse({"status": "success", "message": "Migrations applied."})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    urlpatterns = [
        # ... your other urls
        path('__run_migrations__/', run_migrations_view, name='run_migrations'),
    ]
    ```
    Access `https://your-worker-url.com/__run_migrations__/` to trigger.

### 2. Cloudflare D1 Integration

Use Cloudflare D1, a serverless SQL database, as your Django application's database.

**Important:**
*   **Transactions are disabled** for all D1 database engines. Every query is committed immediately.
*   The D1 backend has some limitations compared to traditional SQLite or other SQL databases. Many advanced ORM features or direct SQL functions (especially those used in Django Admin) might not be fully supported. Refer to the "Limitations" section.

There are two ways to connect to D1:

#### a) D1 Binding (Recommended for Workers)

When your Django application is running on Cloudflare Workers, use D1 Bindings for the fastest access. The D1 database is made available to your worker via an environment binding.

**Django Settings (`settings.py`):**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django_cf.d1_binding',
        # 'CLOUDFLARE_BINDING' should match the binding name in your wrangler.toml
        'CLOUDFLARE_BINDING': 'DB',
    }
}
```
Ensure your `wrangler.toml` includes the D1 database binding (as shown in the Cloudflare Workers section).

#### b) D1 API (For Local Development or External Access)

Connect to D1 via its HTTP API. This method is suitable for local development (e.g., running migrations) or when accessing D1 from outside Cloudflare Workers.

**Note:** Accessing D1 via the API can be slower than using bindings due to the nature of HTTP requests for each query.

**Django Settings (`settings.py`):**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django_cf.d1_api',
        'CLOUDFLARE_DATABASE_ID': '<your_database_id>',
        'CLOUDFLARE_ACCOUNT_ID': '<your_account_id>',
        'CLOUDFLARE_TOKEN': '<your_d1_api_token>', # Ensure this token has D1 Read/Write permissions
    }
}
```

A simple tutorial for getting started with Django and D1 is [available here](https://massadas.com/posts/django-meets-cloudflare-d1/).

### 3. Cloudflare Durable Objects Integration

Utilize Durable Objects for stateful data persistence directly within your Cloudflare Workers. This is useful for applications requiring low-latency access to state associated with specific objects or instances.

**Note:** Durable Objects offer a unique model for state. Understand its consistency and scalability characteristics before implementing.

**Configuration:**

1.  **`wrangler.toml` (or `wrangler.jsonc`):**
    Define your Durable Object class and binding.
    ```toml
    # In your wrangler.toml
    [[durable_objects.bindings]]
    name = "DO_STORAGE" # Name to access the DO namespace in your worker
    class_name = "DjangoDO" # The class name in your worker.py

    # You also need to declare the new class for migrations
    [[migrations]]
    tag = "v1" # Or any other tag
    new_classes = ["DjangoDO"]
    ```

2.  **`src/worker.py` (Worker Entrypoint & Durable Object Class):**
    ```python
    from django_cf import DjangoCFDurableObject
    from PythonWorker import DurableObject # Standard Cloudflare DurableObject base

    # Your Django project's WSGI application
    from myproject.wsgi import application

    class DjangoDO(DjangoCFDurableObject, DurableObject):
        def get_app(self):
            # This method provides the Django WSGI app to the Durable Object
            return application
        # You can add custom methods to your Durable Object here

    # Main fetch handler for the worker
    async def on_fetch(request, env):
        # Example: Route all requests to a single DO instance (singleton)
        # For multi-tenant apps, derive 'name' from the request (e.g., user, path)
        do_id = env.DO_STORAGE.idFromName("singleton_instance")
        stub = env.DO_STORAGE.get(do_id)
        return await stub.fetch(request) # Forward the request to the Durable Object
    ```

3.  **Django Settings (`settings.py`):**
    Configure Django to use the Durable Object backend.
    ```python
    DATABASES = {
        'default': {
            'ENGINE': 'django_cf.do_binding',
            # 'CLOUDFLARE_BINDING' should match the 'name' of your DO binding in wrangler.toml
            'CLOUDFLARE_BINDING': 'DO_STORAGE',
            # 'CLOUDFLARE_INSTANCE_NAME' is optional, defaults to "singleton_instance"
            # It's the name used with idFromName() if not dynamically determined.
            # 'CLOUDFLARE_INSTANCE_NAME': 'my_default_do_instance',
        }
    }
    ```

## Limitations

*   **D1 Database:**
    *   **Transactions are disabled for all D1 engines (Binding and API).** All queries are final, and rollbacks are not available.
    *   When using the **D1 API engine**, queries can be slower compared to the D1 Binding engine due to the overhead of HTTP requests.
    *   A number of Django ORM features, particularly those relying on specific SQL functions (e.g., some used by the Django Admin), may not work as expected or at all. Django Admin functionality will be limited.
    *   Always refer to the official [Django limitations for SQLite databases](https://docs.djangoproject.com/en/stable/ref/databases/#sqlite-notes), as D1 is SQLite-compatible but has its own serverless characteristics.
*   **Durable Objects:** While powerful for stateful serverless applications, ensure you understand the consistency model and potential data storage costs associated with Durable Objects.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for details on setting up a development environment and contributing to `django-cf`.

## License

This project is licensed under the [LICENSE](LICENSE) file.
---

*For a more detailed example of a Django project structured for Cloudflare Workers with D1, check out relevant community projects or the `django-cf` examples if available.*
