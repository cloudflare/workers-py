# django-d1
Cloudflare D1 backend engine for Django

This package is still in tests, and issues will probably appear!
Please report any issues you find in the [Issues tab](https://github.com/G4brym/django-d1/issues).

## Installation

```bash
pip install django-d1db
```

## Usage

```python
DATABASES = {
    'default': {
        'ENGINE': 'django_d1',
        'CLOUDFLARE_DATABASE_ID': '<database_id>',
        'CLOUDFLARE_ACCOUNT_ID': '<account_id>',
        'CLOUDFLARE_TOKEN': '<token>',
    }
}
```

The Cloudflare token requires D1 Edit permissions.

A simple tutorial is [available here](https://massadas.com/posts/django-meets-cloudflare-d1/) for you to read.


## Limitations

Due to the remote nature of D1, queries can take some time to execute.

Read all Django limitations for SQLite [databases here](https://docs.djangoproject.com/en/5.0/ref/databases/#sqlite-notes).
