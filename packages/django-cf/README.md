# django-cf

`django-cf` is a Python package that seamlessly integrates your Django applications with various Cloudflare services. Utilize the power of Cloudflare's global network for your Django projects.

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/G4brym/django-cf/tree/main/templates/d1)

## Installation

```bash
pip install django-cf
```

**Note on Cloudflare Workers Plan:**
This package requires a **Cloudflare Workers Paid Plan** for production use. Django loads many modules which can exceed the CPU time limits included in free accounts. However, if you're interested in experimenting on the free account, feel free to try it out! If you manage to get it working on the free plan, please [open an issue](https://github.com/G4brym/django-cf/issues) describing your setup so other users can benefit from your solution.

## Features

This package provides integration with the following Cloudflare products:

*   **Cloudflare Workers**: Run your Django application on Cloudflare's serverless compute platform.
*   **Cloudflare D1**: Use Cloudflare's serverless SQL database as a backend for your Django application.
*   **Cloudflare Durable Objects**: Leverage stateful objects for applications requiring persistent state within Cloudflare Workers.
*   **Cloudflare R2**: Use Cloudflare's object storage as a Django storage backend for file uploads and static assets.
*   **Cloudflare Access Authentication**: Seamless authentication middleware for Cloudflare Access protected applications.

## Table of Contents

- [Database Backends](#database-backends)
  - [Cloudflare D1](#cloudflare-d1-integration)
  - [Cloudflare Durable Objects](#cloudflare-durable-objects-integration)
- [Storage Backends](#storage-backends)
  - [Cloudflare R2](#cloudflare-r2-storage)
- [Middleware](#middleware)
  - [Cloudflare Access Authentication](#cloudflare-access-authentication)
- [Examples](#examples)
- [Limitations](#limitations)

## Database Backends

### Cloudflare D1 Integration

Use Cloudflare D1, a serverless SQL database, as your Django application's database.

**Important:**
*   **Transactions are disabled** for all D1 database engines. Every query is committed immediately.
*   The D1 backend has some limitations compared to traditional SQLite or other SQL databases. Many advanced ORM features or direct SQL functions (especially those used in Django Admin) might not be fully supported. Refer to the "Limitations" section.

**Configuration:**

1.  **`wrangler.jsonc` (or `wrangler.toml`):**
    ```jsonc
    {
      "d1_databases": [
        {
          "binding": "DB",
          "database_name": "my-django-db",
          "database_id": "your-d1-database-id"
        }
      ]
    }
    ```

2.  **Worker Entrypoint (`src/index.py`):**
    ```python
    from workers import WorkerEntrypoint
    from django_cf import DjangoCF

    class Default(DjangoCF, WorkerEntrypoint):
        async def get_app(self):
            from app.wsgi import application
            return application
    ```

3.  **Django Settings (`settings.py`):**
    ```python
    DATABASES = {
        'default': {
            'ENGINE': 'django_cf.db.backends.d1',
            # 'CLOUDFLARE_BINDING' should match the binding name in your wrangler.jsonc
            'CLOUDFLARE_BINDING': 'DB',
        }
    }
    ```

For a complete working example with full configuration and management endpoints, see the [D1 template](templates/d1/).

### Cloudflare Durable Objects Integration

Utilize Durable Objects for stateful data persistence directly within your Cloudflare Workers. This is useful for applications requiring low-latency access to state associated with specific objects or instances.

**Important:**
*   **Transactions are disabled** for Durable Objects. All queries are committed immediately, and rollbacks are not available.
*   Durable Objects offer a unique model for state. Understand its consistency and scalability characteristics before implementing.

**Configuration:**

1.  **`wrangler.jsonc` (or `wrangler.toml`):**
    Define your Durable Object class and binding.
    ```jsonc
    {
      "durable_objects": {
        "bindings": [
          {
            "name": "DO_STORAGE",
            "class_name": "DjangoDO"
          }
        ]
      },
      "migrations": [
        {
          "tag": "v1",
          "new_sqlite_classes": ["DjangoDO"]
        }
      ]
    }
    ```

2.  **Worker Entrypoint (`src/index.py`):**
    ```python
    from workers import DurableObject, WorkerEntrypoint
    from django_cf import DjangoCFDurableObject

    class DjangoDO(DjangoCFDurableObject, DurableObject):
        def get_app(self):
            from app.wsgi import application
            return application

    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            # Route requests to a DO instance
            id = self.env.DO_STORAGE.idFromName("singleton_instance")
            obj = self.env.DO_STORAGE.get(id)
            return await obj.fetch(request)
    ```

3.  **Django Settings (`settings.py`):**
    ```python
    DATABASES = {
        'default': {
            'ENGINE': 'django_cf.db.backends.do',
        }
    }
    ```

For a complete working example with full configuration and management endpoints, see the [Durable Objects template](templates/durable-objects/).

## Storage Backends

### Cloudflare R2 Storage

Use Cloudflare R2, a global object storage service, as your Django storage backend for handling file uploads, media files, and static assets.

**Features:**
*   **Serverless Object Storage**: Store files in Cloudflare's globally distributed object storage.
*   **S3-Compatible API**: R2 uses an S3-compatible API accessible through Workers bindings.
*   **No Egress Fees**: R2 has no egress fees, making it cost-effective for serving files.
*   **Integrated with Workers**: Direct access to R2 buckets through Worker bindings.

**Configuration:**

1.  **`wrangler.jsonc` (or `wrangler.toml`):**
    ```jsonc
    {
      "r2_buckets": [
        {
          "binding": "BUCKET",
          "bucket_name": "my-django-bucket"
        }
      ]
    }
    ```

2.  **Django Settings (`settings.py`):**
    ```python
    STORAGES = {
        "default": {
            "BACKEND": "django_cf.storage.R2Storage",
            "OPTIONS": {
                # The binding name must match the one in wrangler.jsonc
                "binding": "BUCKET",
                # Optional: prefix for all files
                "location": "",
                # Optional: allow overwriting existing files (default: False)
                "allow_overwrite": False,
            }
        },
        # Optional: separate storage for static files
        "staticfiles": {
            "BACKEND": "django_cf.storage.R2Storage",
            "OPTIONS": {
                "binding": "BUCKET",
                "location": "static",
            }
        },
    }
    ```

**Usage Example:**

```python
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

# Save a file
content = ContentFile(b"Hello, R2!")
path = default_storage.save("hello.txt", content)

# Read a file
with default_storage.open("hello.txt", "rb") as f:
    content = f.read()

# Check if file exists
exists = default_storage.exists("hello.txt")

# Delete a file
default_storage.delete("hello.txt")

# List files in a directory
directories, files = default_storage.listdir("uploads/")
```

**Configuration Options:**

*   **`binding`** (required): The R2 bucket binding name from your `wrangler.jsonc`
*   **`location`** (optional): A prefix path for all files stored in R2 (default: empty string)
*   **`allow_overwrite`** (optional): Controls file overwrite behavior:
    - `True` (default): Files with the same name will be overwritten
    - `False`: If a file exists, a new filename will be generated by appending `_1`, `_2`, etc. before the file extension

**Important Notes:**
*   R2 Storage is designed to work within Cloudflare Workers and requires Worker bindings.
*   The `url()` method raises `NotImplementedError` by default since R2 objects are not publicly accessible. You'll need to configure R2 public buckets or implement signed URLs for public access.
*   All file operations use the Workers R2 API, which provides low-latency access to your objects.

## Examples

Complete, production-ready examples are available in the `templates/` directory:

- **[D1 Template](templates/d1/)** - Django on Cloudflare Workers with D1 database
- **[Durable Objects Template](templates/durable-objects/)** - Django on Cloudflare Workers with Durable Objects

Each template includes:
- Pre-configured `wrangler.jsonc`
- Worker entrypoint setup
- Django settings configured for the respective backend
- Management command endpoints for migrations and admin creation
- Complete deployment instructions

## Middleware

### Cloudflare Access Authentication

Seamless authentication middleware for Cloudflare Access protected applications. The middleware is implemented using only Python standard library modules - no external dependencies required!

This middleware works on both self-hosted Django applications and Django hosted on Cloudflare Workers.

#### Quick Start

##### 1. Add to INSTALLED_APPS

```python
# settings.py
INSTALLED_APPS = [
    # ... your other apps
    'django_cf',
]
```

##### 2. Configure Cloudflare Access Middleware

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

##### 3. Configure Cloudflare Access Settings

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

#### Required Settings (At Least One)

You must provide **at least one** of the following settings:

##### `CLOUDFLARE_ACCESS_AUD`
Your Cloudflare Access Application Audience (AUD) tag. You can find this in your Cloudflare Zero Trust dashboard:
1. Go to Access → Applications
2. Select your application
3. Copy the "Application Audience (AUD) Tag"

**When to use**: Provide this if you want strict audience validation or if you have multiple applications with the same team.

##### `CLOUDFLARE_ACCESS_TEAM_NAME`
Your Cloudflare team name (the subdomain part of your team domain). For example, if your team domain is `mycompany.cloudflareaccess.com`, then your team name is `mycompany`.

**When to use**: Provide this if you want simpler configuration or if you only have one application per team.

#### Configuration Options

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

#### Optional Settings

##### `CLOUDFLARE_ACCESS_EXEMPT_PATHS`
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

##### `CLOUDFLARE_ACCESS_CACHE_TIMEOUT`
Default: `3600` (1 hour)

How long to cache Cloudflare's public keys (in seconds). Cloudflare rotates these keys periodically, so caching reduces API calls while ensuring fresh keys are fetched when needed.

#### How It Works

##### Authentication Flow

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

##### User Creation

When a user authenticates for the first time:
- Username is set to the user's email address
- Email is extracted from JWT `email` claim
- Name is split into first_name and last_name from JWT `name` claim
- User is created with `is_active=True`

For existing users:
- Name is updated if it has changed in Cloudflare
- User is automatically logged in

#### Security Considerations

##### Token Validation
- All JWT tokens are validated against Cloudflare's public keys
- Tokens are checked for expiration
- Audience (AUD) is validated to ensure tokens are for your application

##### Caching
- Public keys are cached to reduce API calls to Cloudflare
- Cache keys are scoped to your team name
- Failed key fetches are logged but don't crash the application

##### Error Handling
- Authentication failures return 401 responses
- Server errors return 500 responses
- All errors are logged for debugging

#### Logging

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

#### Common Issues and Troubleshooting

##### 401 Unauthorized Responses

**Cause**: JWT token is missing, invalid, or expired.

**Solutions**:
1. Ensure your application is behind Cloudflare Access
2. Check that users are properly authenticated with Cloudflare Access
3. If using `CLOUDFLARE_ACCESS_AUD`, verify it matches your application's AUD tag
4. If using `CLOUDFLARE_ACCESS_TEAM_NAME`, check that it's correct
5. Review middleware logs for specific validation errors

##### 500 Internal Server Error

**Cause**: Unable to fetch Cloudflare public keys or other configuration issues.

**Solutions**:
1. Verify your team name is correct (if using `CLOUDFLARE_ACCESS_TEAM_NAME`)
2. Check network connectivity to Cloudflare
3. Review logs for specific error messages
4. If using only AUD, ensure the JWT contains a valid issuer claim

##### Users Not Being Created

**Cause**: Missing email claim in JWT or database issues.

**Solutions**:
1. Check that your Cloudflare Access application is configured to include email in JWT
2. Verify Django database migrations are up to date
3. Check Django user model permissions

#### Advanced Usage

##### Custom User Creation

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

##### Multiple Applications

If you have multiple Cloudflare Access applications, you can configure different middleware instances or use environment-specific settings.

#### Development

##### Testing

When developing applications with this middleware, you may want to disable it in certain environments:

```python
# settings.py
if DEBUG and not os.getenv('ENABLE_CF_ACCESS'):
    # Remove CloudflareAccessMiddleware from MIDDLEWARE list
    MIDDLEWARE = [m for m in MIDDLEWARE if 'CloudflareAccessMiddleware' not in m]
```

##### Local Development

For local development without Cloudflare Access:
1. Set exempt paths to include your development URLs
2. Use Django's built-in authentication for local testing
3. Consider using environment variables to toggle the middleware

## Limitations

*   **D1 Database:**
    *   **Transactions are disabled.** All queries are final, and rollbacks are not available.
    *   A number of Django ORM features, particularly those relying on specific SQL functions (e.g., some used by the Django Admin), may not work as expected or at all. Django Admin functionality will be limited.
    *   Always refer to the official [Django limitations for SQLite databases](https://docs.djangoproject.com/en/stable/ref/databases/#sqlite-notes), as D1 is SQLite-compatible but has its own serverless characteristics.
*   **Durable Objects:**
    *   **Transactions are disabled.** All queries are final, and rollbacks are not available.
    *   While powerful for stateful serverless applications, ensure you understand the consistency model and potential data storage costs associated with Durable Objects.

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

*For complete, working examples of Django projects on Cloudflare Workers, refer to the templates in the `templates/` directory.*
