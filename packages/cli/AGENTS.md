# packages/cli

## Overview

`workers-py` (or `pywrangler`) is a command-line interface for managing Python Workers.

It provides commands for:
- Installing packages (`pywrangler sync`)
- Running workers locally (`pywrangler dev`)
- Uploading workers to Cloudflare (`pywrangler deploy`)

## Development Guidelines

- `pywrangler` is a wrapper of `wrangler` (https://github.com/cloudflare/workers-sdk), focused on Python Worker-specific functionality.
- If there are commands that are already implemented in `wrangler`, `pywrangler` should delegate to `wrangler` except for Python Worker-specific functionality.

## Testing

- When adding new features, make sure to add both unit tests and integration tests.
  - Unit tests should not depend on external services (`wrangler` or `uv`), only on the code itself.
  - Integration tests should test the interaction between `pywrangler` and external services.
