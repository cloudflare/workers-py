# packages/runtime-sdk

## Overview

`workers-runtime-sdk` is a Python package that provides utilities for running Python code in a Cloudflare Worker environment.

## Features

This package provides utilities for:

- Pythonic wrappers for Cloudflare Worker APIs
- A simple ASGI server for running Python web applications in Cloudflare Workers

## Development Guidelines

- `_pyodide_entrypoint_helper` and `_cloudflare_compat_flags` are internal values that are imported from `workerd`.
  - `workerd` (https://github.com/cloudflare/workerd) is the runtime that Cloudflare Workers use to run Python code.
- When using a feature from `workerd`, always check if we can implement it in this package instead to avoid tight coupling with the runtime.

## Testing

- All the tests should be done inside `workerd`, not in the host environment.
- Tests should be implemented in `../cli/tests` directory.
