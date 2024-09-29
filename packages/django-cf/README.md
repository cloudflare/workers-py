# django-cf
Django database engine for Cloudflare D1 and Durable Objects

## Installation

```bash
pip install django-cf
```

## Using with D1

The D1 engine uses the HTTP api directly from Cloudflare, meaning you only need to create a new D1 database, then
create an API token with `D1 read` permission, and you are good to go!

But using an HTTP endpoint for executing queries one by one is very slow, and currently there is no way to accelerate
it, until a websocket endpoint is available.

The HTTP api doesn't support transactions, meaning all execute queries are final and rollbacks are not available.

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

## Using with Durable Objects

The DO engine, requires you to deploy [workers-dbms](https://github.com/G4brym/workers-dbms) on your cloudflare account.
This engine uses a websocket endpoint to keep the connection alive, meaning sql queries are executed way faster.

workers-dbms have an experimental transaction support, everything should be working out of the box, but you should keep
an eye out for weird issues and report them back.


```python
DATABASES = {
    'default': {
        'ENGINE': 'django_dbms',
        'WORKERS_DBMS_ENDPOINT': '<websocket_endpoint>',  # This should start with wss://
        'WORKERS_DBMS_ACCESS_ID': '<access_id>',  # Optional, but highly recommended!
        'WORKERS_DBMS_ACCESS_SECRET': '<access_secret>',  # Optional, but highly recommended!
    }
}
```


## Limitations

When using D1 engine, queries are expected to be slow, and transactions are disabled.

Read all Django limitations for SQLite [databases here](https://docs.djangoproject.com/en/5.0/ref/databases/#sqlite-notes).
