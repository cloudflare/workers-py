# django-cf
django-cf is a package that integrates Django with Cloudflare products

Integrations:
 - Cloudflare D1
 - Cloudflare Workers

## Installation

```bash
pip install django-cf
```

## Cloudflare D1

Cloudflare D1 doesn't support transactions, meaning all execute queries are final and rollbacks are not available.

A simple tutorial is [available here](https://massadas.com/posts/django-meets-cloudflare-d1/) for you to read.


### D1 Binding

You can now deploy Django into a Cloudflare Python Worker, and in that environment, D1 is available as a Binding for
faster queries.

```python
DATABASES = {
    'default': {
        'ENGINE': 'django_cf.d1_binding',
        'CLOUDFLARE_BINDING': 'DB',
    }
}
```

### D1 API

The D1 engine uses the HTTP api directly from Cloudflare, meaning you only need to create a new D1 database, then
create an API token with `D1 read` and `D1 write` permission, and you are good to go!

But using an HTTP endpoint for executing queries one by one is very slow, and currently there is no way to speed up
it.

```python
DATABASES = {
    'default': {
        'ENGINE': 'django_cf.d1_api',
        'CLOUDFLARE_DATABASE_ID': '<database_id>',
        'CLOUDFLARE_ACCOUNT_ID': '<account_id>',
        'CLOUDFLARE_TOKEN': '<token>',
    }
}
```

## Cloudflare Workers

django-cf includes an adapter that allows you to run Django inside Cloudflare Workers named `DjangoCFAdapter`

Suggested project structure
```
root
 |-> src/
 |-> src/manage.py
 |-> src/worker.py               <-- Wrangler entrypoint
 |-> src/your-apps-here/
 |-> src/vendor/...              <-- Project dependencies, details bellow
 |-> vendor.txt
 |-> wrangler.jsonc
```

`vendor.txt`
```txt
django==5.1.2
django-cf
tzdata
```

`wrangler.jsonc`
```jsonc
{
    "name": "django-on-workers",
    "main": "src/worker.py",
    "compatibility_flags": [
        "python_workers_20250116",
        "python_workers"
    ],
    "compatibility_date": "2025-04-10",
    "assets": {
      "directory": "./staticfiles/"
    },
    "rules": [
        {
            "globs": [
                "vendor/**/*.py",
                "vendor/**/*.mo",
                "vendor/tzdata/**/",
            ],
            "type": "Data",
            "fallthrough": true
        }
    ],
    "d1_databases": [
        {
            "binding": "DB",
            "database_name": "my-django-db",
            "database_id": "924e612f-6293-4a3f-be66-cce441957b03",
        }
    ],
    "observability": {
        "enabled": true
    }
}
```

`src/worker.py`
```python
from django_cf import DjangoCFAdapter

async def on_fetch(request, env):
    from app.wsgi import application  # Update acording to your project structure
    adapter = DjangoCFAdapter(application)

    return adapter.handle_request(request)

```

Then run this command to vendor your dependencies:
```bash
pip install -t src/vendor -r vendor.txt
```

To bundle static assets with your worker, add this line to your `settings.py`, this will place the assets outside the src folder
```python
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR.parent.joinpath('staticfiles').joinpath('static')
```

And this command generate the static assets:
```bash
python src/manage.py collectstatic
```

Now deploy your worker
```bash
npx wrangler deploy
```

### Running migrations and other commands
In the ideal setup, your application will have two settings, one for production and another for development.

- The production one, will connect to D1 via using the binding, as this is way faster.
- The development one, will connect using the D1 API.

Using this setup, you can apply the migrations from your local machine.

In case that is not enought for you, here is a snippet that allows you to apply D1 migrations using a deployed worker:

Just add these new routes to your `urls.py`:

```python
from django.contrib import admin
from django.contrib.auth import get_user_model;
from django.http import JsonResponse
from django.urls import path

def create_admin(request):
    User = get_user_model();
    User.objects.create_superuser('admin', 'admin@do.com', 'password')
    return JsonResponse({"user": "ok"})

def migrate(request):
    from django.core.management import execute_from_command_line
    execute_from_command_line(["manage.py", "migrate"])

    return JsonResponse({"migrations": "ok"})

urlpatterns = [
    path('create-admin', create_admin),
    path('migrate', migrate),
    path('admin/', admin.site.urls),
]
```

You may now call your worker to apply all missing migrations, ex: `https://django-on-workers.{username}.workers.dev/migrate`

## Limitations

When using D1 engine, queries are expected to be slow, and transactions are disabled.

A lot of query features are additionally disabled, for example inline sql functions, used extensively inside Django Admin

Read all Django limitations for SQLite [databases here](https://docs.djangoproject.com/en/5.0/ref/databases/#sqlite-notes).
