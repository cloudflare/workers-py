# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

django-cf integrates Django with Cloudflare products (Workers, D1, Durable Objects, R2, and Access). It enables running Django applications on Cloudflare's serverless platform with custom database backends and storage.

## Development Commands

```bash
# Install dependencies (including dev)
pip install -e ".[dev]"

# Run tests (requires wrangler/npm for worker tests)
pytest

# Run a specific test file
pytest tests/d1/test_worker.py

# Lint with ruff
ruff check .

# Build package
pip install build twine
python3 -m build

# Publish to PyPI
python3 -m twine upload dist/*
```

## Architecture

### Core Components

- **`django_cf/__init__.py`** - WSGI adapter classes (`DjangoCF`, `DjangoCFDurableObject`) that bridge Django apps to Cloudflare Workers
- **`django_cf/db/base_engine.py`** - Base database wrapper extending Django's SQLite backend with Cloudflare-specific features (disabled transactions, custom SQL compilers for date truncation)
- **`django_cf/db/backends/d1/`** - D1 database backend using Workers bindings
- **`django_cf/db/backends/do/`** - Durable Objects database backend with local storage
- **`django_cf/storage/r2.py`** - R2 storage backend for file operations
- **`django_cf/middleware/CloudflareAccessMiddleware.py`** - JWT-based auth middleware for Cloudflare Access

### Database Backend Design

All database backends extend `CFDatabaseWrapper` from `base_engine.py`, which:
- Inherits from Django's SQLite backend
- Disables transactions (`atomic_transactions = False`, `supports_transactions = False`)
- Implements custom `CFResult` for handling query results from JS bindings
- Patches date truncation functions for SQLite compatibility

### Test Infrastructure

Tests use `pytest` with session-scoped fixtures that spawn actual Cloudflare Workers via `wrangler dev`:
- `tests/utils.py` - `WorkerFixture` class manages worker lifecycle
- Workers run on random ports and auto-migrate on startup
- Templates in `templates/d1/` and `templates/durable-objects/` are used as test servers

### Key Constraints

- Requires Cloudflare Workers Paid Plan (free tier has CPU limits)
- Transactions are disabled - all queries commit immediately
- Django Admin functionality is limited due to D1/DO constraints
- Code runs inside Pyodide (Python in WASM) on Workers runtime
