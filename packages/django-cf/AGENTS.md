# packages/django-cf

## Overview

`django-cf` is a Python package that lets a Django application run on Cloudflare Workers and use Cloudflare products as Django backends.

It is published to PyPI as `django-cf` and imported as `django_cf`.

## Features

- Database backends for Cloudflare D1 (`django_cf.db.backends.d1`) and Durable Objects (`django_cf.db.backends.do`), both built on the shared engine in `django_cf/db/base_engine.py`
- A Django storage backend for Cloudflare R2 (`django_cf.storage.R2Storage`)
- Authentication middleware for Cloudflare Access (`django_cf.middleware.CloudflareAccessMiddleware`)
- WSGI entrypoints for Workers and Durable Objects (`DjangoCF`, `DjangoCFDurableObject`)

## Development Guidelines

- Both database backends have transactions **disabled**. Every query commits immediately and rollbacks are unavailable, so code that relies on `atomic()` for correctness will not behave as it does on other backends.
- This package still uses a flat layout (`django_cf/`) and a setuptools build backend, unlike `packages/cli` and `packages/runtime-sdk` which use src-layout and hatchling.
- `templates/d1/` and `templates/durable-objects/` are deployable example projects, and `tests/servers/r2/` is a fixture app used by the R2 integration tests. None of them are part of the wheel.
- That ruff config deliberately ignores `B904`, `B905`, `C901`, `PERF401`, `PLR0911`, `PLR0912`, `PLR0913`, `PLR0915`, `PLR2004`, `PLW0603` and `UP038`, because fixing the existing violations would mean behavioural or structural changes. Write new code that does not need those ignores.
- mypy and semgrep currently skip this package. Adding either is a deliberate follow-up, not something to switch on incidentally.

## Testing

- Lint everything with `uvx pre-commit run -a` from the repository root.
- Every suite needs a Node toolchain, because every suite runs against a real Worker. Run them from `packages/django-cf` with `uv run --frozen pytest tests`; the `django-test` job in `.github/workflows/tests.yml` runs the same command.
- `tests/conftest.py` is the whole harness. It copies the worker project into a tmpdir, runs `pywrangler sync`, overwrites the vendored `django_cf/` with the working tree, then starts `pywrangler dev` on a free port. Nothing is installed into the repository, so there is no setup step to re-run after editing library files.
- Two shapes of suite:
  - `tests/d1/`, `tests/durable_objects/`, `tests/r2/` drive a deployed Django app over HTTP, via the session-scoped `d1_web_server`, `durable_objects_web_server` and `r2_web_server` fixtures. Those apps live in `templates/` and `tests/servers/r2/` and expose management endpoints for setup, such as `/__run_migrations__/` and `/__create_admin__/`, which creates an admin user with username `admin` and password `password`.
  - `tests/in_worker/` runs pytest *inside* workerd. The real test bodies are `tests/in_worker/worker/src/test_*.py`; `register_in_worker_suites` discovers them by AST and generates one host-side test per in-worker test, so a failure inside the Worker surfaces as an ordinary pytest failure. `pyproject.toml` ignores that `src` directory so the host collector does not try to import Worker-only modules.
