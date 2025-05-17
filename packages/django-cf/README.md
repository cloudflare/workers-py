# django-cf
Django-CF is a package that integrates Django with Cloudflare products

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

## Running in Workers Tips

Suggested project structure
```
root
 |-> src/
 |-> src/your-apps-here/
 |-> src/vendor/...
 |-> vendor.txt
 |-> wrangler.jsonc
```

Your vendor.txt should have only the packages you need for production, and due to workers limit in upload size, try to keep this small

Suggested `vendor.txt`
```txt
django==5.1.2
django-cf
tzdata
```

Then run this command to vendor your dependencies:
```bash
pip install -t src/vendor -r vendor.txt
```

Suggested `wrangler.jsonc`

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

## Limitations

When using D1 engine, queries are expected to be slow, and transactions are disabled.

A lot of query features are additionally disabled, for example inline sql functions, used extensively inside Django Admin

Read all Django limitations for SQLite [databases here](https://docs.djangoproject.com/en/5.0/ref/databases/#sqlite-notes).
