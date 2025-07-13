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
*   **Cloudflare Access Authentication**: Seamless authentication middleware for Cloudflare Access protected applications.

## Cloudflare Workers Integration

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
    [assets]
    directory = "./staticfiles"

    # Rules for including vendored Python packages
    # Optionally add a glob rule for "vendor/**/*.mo" to get django translations, but this will require workers paid plan
    [[rules]]
    globs = ["vendor/**/*.py", "vendor/tzdata/**/", "vendor/**/*.txt.gz"]
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

4.  **`src/worker.py` (Worker Entrypoint):**
    Use `DjangoCFAdapter` to handle requests.
    ```python
    from django_cf import DjangoCFAdapter

    async def on_fetch(request, env):
        # Ensure your Django project's WSGI application is importable
        # For example, if your project is 'myproject' inside 'src':
        from myproject.wsgi import application # Import application inside on_fetch
        adapter = DjangoCFAdapter(application)
        return await adapter.handle_request(request)
    ```

5.  **Django Settings (`settings.py`):**
    *   **Static Files:** Configure Django to collect static files into the directory specified in `wrangler.toml`.
        ```python
        # settings.py
        import os
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        STATIC_URL = '/static/'
        # STATIC_ROOT should point to the 'assets' directory in wrangler.toml,
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
    from django.contrib.auth import get_user_model # For create_admin_view

    def is_superuser(user):
        return user.is_superuser

    @user_passes_test(is_superuser) # Protect this endpoint!
    def run_migrations_view(request):
        try:
            call_command("migrate")
            return JsonResponse({"status": "success", "message": "Migrations applied."})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    @user_passes_test(is_superuser) # Protect this endpoint!
    def create_admin_view(request):
        User = get_user_model()
        username = 'admin' # Or get from request, config, etc.
        email = 'admin@example.com' # Or get from request, config, etc.
        password = 'yoursecurepassword' # Ideally, generate or get from a secure source

        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username, email, password)
            return JsonResponse({"status": "success", "message": f"Admin user '{username}' created."})
        else:
            return JsonResponse({"status": "info", "message": f"Admin user '{username}' already exists."})

    urlpatterns = [
        # ... your other urls
        path('__run_migrations__/', run_migrations_view, name='run_migrations'),
        path('__create_admin__/', create_admin_view, name='create_admin'), # Add this
    ]
    ```
    Access `https://your-worker-url.com/__run_migrations__/` to trigger migrations.
    Access `https://your-worker-url.com/__create_admin__/` to trigger admin creation.

## Cloudflare D1 Integration

Use Cloudflare D1, a serverless SQL database, as your Django application's database.

**Important:**
*   **Transactions are disabled** for all D1 database engines. Every query is committed immediately.
*   The D1 backend has some limitations compared to traditional SQLite or other SQL databases. Many advanced ORM features or direct SQL functions (especially those used in Django Admin) might not be fully supported. Refer to the "Limitations" section.

There are two ways to connect to D1:

### a) D1 Binding (Recommended for Workers)

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

### b) D1 API (For Local Development or External Access)

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

## Cloudflare Durable Objects Integration

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
        }
    }
    ```
    The `django_cf.do_binding` engine will automatically use the Durable Object binding specified in your `wrangler.toml` that is associated with the `DjangoCFDurableObject` class. Ensure your `wrangler.toml` correctly binds a name to your `DjangoCFDurableObject` subclass.

## Cloudflare Access Authentication

Seamless authentication middleware for Cloudflare Access protected applications. The middleware is implemented using only Python standard library modules - no external dependencies required!

This middleware works on both self-hosted Django applications and Django hosted on Cloudflare Workers.

### Quick Start

#### 1. Add to INSTALLED_APPS

```python
# settings.py
INSTALLED_APPS = [
    # ... your other apps
    'django_cf',
]
```

#### 2. Configure Cloudflare Access Middleware

Add the middleware to your Django settings:

```python
# settings.py
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',  # Must be before CloudflareAccessMiddleware
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django_cf.middleware.CloudflareAccessMiddleware',
    # ... other middleware (should be placed appropriately in your middleware stack)
]
```

#### 3. Configure Cloudflare Access Settings

Add the required settings to your Django configuration:

```python
# settings.py

# Required settings (at least one must be provided)
CLOUDFLARE_ACCESS_AUD = 'your-application-audience-tag'  # Optional if team name is provided
CLOUDFLARE_ACCESS_TEAM_NAME = 'yourteam'  # Optional if AUD is provided

# Optional settings
CLOUDFLARE_ACCESS_EXEMPT_PATHS = [
    '/health/',
    '/api/public/',
    '/admin/login/',  # If you want to keep Django admin login
]
CLOUDFLARE_ACCESS_CACHE_TIMEOUT = 3600  # Cache timeout for public keys (seconds)
```

### Required Settings (At Least One)

You must provide **at least one** of the following settings:

#### `CLOUDFLARE_ACCESS_AUD`
Your Cloudflare Access Application Audience (AUD) tag. You can find this in your Cloudflare Zero Trust dashboard:
1. Go to Access → Applications
2. Select your application
3. Copy the "Application Audience (AUD) Tag"

**When to use**: Provide this if you want strict audience validation or if you have multiple applications with the same team.

#### `CLOUDFLARE_ACCESS_TEAM_NAME`
Your Cloudflare team name (the subdomain part of your team domain). For example, if your team domain is `mycompany.cloudflareaccess.com`, then your team name is `mycompany`.

**When to use**: Provide this if you want simpler configuration or if you only have one application per team.

### Configuration Options

You can configure the middleware in three ways:

1. **Both AUD and Team Name** (Recommended for production):
   ```python
   CLOUDFLARE_ACCESS_AUD = 'your-application-audience-tag'
   CLOUDFLARE_ACCESS_TEAM_NAME = 'yourteam'
   ```

2. **Only AUD** (Team name extracted from JWT):
   ```python
   CLOUDFLARE_ACCESS_AUD = 'your-application-audience-tag'
   ```

3. **Only Team Name** (AUD validated but not enforced):
   ```python
   CLOUDFLARE_ACCESS_TEAM_NAME = 'yourteam'
   ```

### Optional Settings

#### `CLOUDFLARE_ACCESS_EXEMPT_PATHS`
Default: `[]`

List of URL paths that should be exempt from Cloudflare Access authentication. Useful for:
- Health check endpoints
- Public API endpoints
- Webhooks
- Static file serving (if not handled by your web server)

Example:
```python
CLOUDFLARE_ACCESS_EXEMPT_PATHS = [
    '/health/',
    '/api/public/',
    '/webhooks/',
    '/static/',  # If serving static files through Django
]
```

#### `CLOUDFLARE_ACCESS_CACHE_TIMEOUT`
Default: `3600` (1 hour)

How long to cache Cloudflare's public keys (in seconds). Cloudflare rotates these keys periodically, so caching reduces API calls while ensuring fresh keys are fetched when needed.

### How It Works

#### Authentication Flow

1. **Request Processing**: For each incoming request, the middleware checks if the path is exempt from authentication
2. **JWT Extraction**: Extracts the JWT token from:
   - `CF-Access-Jwt-Assertion` header (preferred)
   - `CF_Authorization` cookie (fallback)
3. **Team Discovery**: If team name is not configured, extracts it from the JWT's issuer claim
4. **Public Key Retrieval**: Fetches Cloudflare's public keys from the team's certs endpoint
5. **Token Validation**: Validates the JWT against Cloudflare's public keys:
   - Validates token signature and expiration
   - Validates audience (AUD) if configured
6. **User Management**: 
   - Extracts email and name from JWT claims
   - Creates new Django user if doesn't exist
   - Updates existing user's name if changed
   - Logs the user into Django session
7. **Response**: Proceeds with the request if authentication succeeds, returns 401 if it fails

#### User Creation

When a user authenticates for the first time:
- Username is set to the user's email address
- Email is extracted from JWT `email` claim
- Name is split into first_name and last_name from JWT `name` claim
- User is created with `is_active=True`

For existing users:
- Name is updated if it has changed in Cloudflare
- User is automatically logged in

### Security Considerations

#### Token Validation
- All JWT tokens are validated against Cloudflare's public keys
- Tokens are checked for expiration
- Audience (AUD) is validated to ensure tokens are for your application

#### Caching
- Public keys are cached to reduce API calls to Cloudflare
- Cache keys are scoped to your team name
- Failed key fetches are logged but don't crash the application

#### Error Handling
- Authentication failures return 401 responses
- Server errors return 500 responses
- All errors are logged for debugging

### Logging

The middleware uses Django's logging system with logger name `django_cf.middleware`. To see debug information:

```python
# settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django_cf.middleware': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

### Common Issues and Troubleshooting

#### 401 Unauthorized Responses

**Cause**: JWT token is missing, invalid, or expired.

**Solutions**:
1. Ensure your application is behind Cloudflare Access
2. Check that users are properly authenticated with Cloudflare Access
3. If using `CLOUDFLARE_ACCESS_AUD`, verify it matches your application's AUD tag
4. If using `CLOUDFLARE_ACCESS_TEAM_NAME`, check that it's correct
5. Review middleware logs for specific validation errors

#### 500 Internal Server Error

**Cause**: Unable to fetch Cloudflare public keys or other configuration issues.

**Solutions**:
1. Verify your team name is correct (if using `CLOUDFLARE_ACCESS_TEAM_NAME`)
2. Check network connectivity to Cloudflare
3. Review logs for specific error messages
4. If using only AUD, ensure the JWT contains a valid issuer claim

#### Users Not Being Created

**Cause**: Missing email claim in JWT or database issues.

**Solutions**:
1. Check that your Cloudflare Access application is configured to include email in JWT
2. Verify Django database migrations are up to date
3. Check Django user model permissions

### Advanced Usage

#### Custom User Creation

If you need custom user creation logic, you can subclass the middleware:

```python
from django_cf.middleware import CloudflareAccessMiddleware
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomCloudflareAccessMiddleware(CloudflareAccessMiddleware):
    def _get_or_create_user(self, email, name):
        # Your custom user creation logic here
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': name.split(' ')[0] if name else '',
                'last_name': ' '.join(name.split(' ')[1:]) if name else '',
                'is_active': True,
                'is_staff': email.endswith('@yourcompany.com'),  # Custom logic
            }
        )
        return user
```

#### Multiple Applications

If you have multiple Cloudflare Access applications, you can configure different middleware instances or use environment-specific settings.

### Development

#### Testing

When developing applications with this middleware, you may want to disable it in certain environments:

```python
# settings.py
if DEBUG and not os.getenv('ENABLE_CF_ACCESS'):
    # Remove CloudflareAccessMiddleware from MIDDLEWARE list
    MIDDLEWARE = [m for m in MIDDLEWARE if 'CloudflareAccessMiddleware' not in m]
```

#### Local Development

For local development without Cloudflare Access:
1. Set exempt paths to include your development URLs
2. Use Django's built-in authentication for local testing
3. Consider using environment variables to toggle the middleware

## Limitations

*   **D1 Database:**
    *   **Transactions are disabled for all D1 engines (Binding and API).** All queries are final, and rollbacks are not available.
    *   When using the **D1 API engine**, queries can be slower compared to the D1 Binding engine due to the overhead of HTTP requests.
    *   A number of Django ORM features, particularly those relying on specific SQL functions (e.g., some used by the Django Admin), may not work as expected or at all. Django Admin functionality will be limited.
    *   Always refer to the official [Django limitations for SQLite databases](https://docs.djangoproject.com/en/stable/ref/databases/#sqlite-notes), as D1 is SQLite-compatible but has its own serverless characteristics.
*   **Durable Objects:** While powerful for stateful serverless applications, ensure you understand the consistency model and potential data storage costs associated with Durable Objects.

## Contributing

See [DEVELOPMENT.md](DEVELOPMENT.md) for details on setting up a development environment and contributing to `django-cf`.

We welcome contributions! Please see our contributing guidelines and feel free to submit issues and pull requests.

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review Cloudflare Access documentation
3. Submit an issue on GitHub with detailed error logs and configuration (remove sensitive information)

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

*For a more detailed example of a Django project structured for Cloudflare Workers with D1, check out relevant community projects or the `django-cf` examples if available.*
