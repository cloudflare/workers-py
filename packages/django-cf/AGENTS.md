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
- Ruff is configured in `pyproject.toml`. `target-version` is `py312` here because the package declares `requires-python = ">=3.12"`; the two sibling packages target `py311`.
- That ruff config deliberately ignores `B904`, `B905`, `C901`, `PERF401`, `PLR0911`, `PLR0912`, `PLR0913`, `PLR0915`, `PLR2004`, `PLW0603` and `UP038`, because fixing the existing violations would mean behavioural or structural changes. Write new code that does not need those ignores.
- mypy and semgrep currently skip this package. Adding either is a deliberate follow-up, not something to switch on incidentally.

## Testing

- Lint everything with `uvx pre-commit run -a` from the repository root.
- The suites split by whether they need a real Worker:
  - Host-runnable, no Node required: `tests/db/`, `tests/middleware/`, `tests/test_wsgi_handler.py`.
  - Require `wrangler dev`: `tests/d1/`, `tests/durable_objects/`, `tests/r2/`, `tests/e2e/`, `tests/test_date_trunc.py`.
- A bare `pytest` collects everything and fails without a Node toolchain. For the host-runnable subset, run from `packages/django-cf`:
  ```bash
  uv sync
  uv run pytest tests/db tests/middleware tests/test_wsgi_handler.py
  ```
- The Worker-backed suites additionally need `npm run setup-test`, which runs `npm install` and copies `django_cf/` into each fixture's `python_modules/` directory. Adding, moving or renaming library files means re-running it.
- Those suites get their base URL from the `d1_web_server`, `durable_objects_web_server` and `r2_web_server` fixtures in `tests/utils.py`, each of which spawns `npx wrangler dev` on a free port.
- The template and fixture apps expose management endpoints for test setup, such as `/__run_migrations__/` and `/__create_admin__/`, which creates an admin user with username `admin` and password `password`.
- This package has no test job in `.github/workflows/tests.yml` yet, so nothing here runs in CI.
