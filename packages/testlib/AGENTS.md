# packages/testlib

## Overview

`testlib` holds shared helpers for tests that run pytest *inside* workerd. It is
not published; `runtime-sdk` and `django-cf` vendor it into their test workers
via `../packages/testlib` in `[tool.uv.sources]`.

## Key modules

| Module | Runs on | Purpose |
|---|---|---|
| `testlib/host.py` | host | `dev_server`, `pywrangler_sync`, `register_in_worker_suites` |
| `testlib/entrypoint.py` | worker | `TestRunner`, `TestRunnerEntrypoint` (`/run-tests/<suite>`, `/health`), `ResultCollector` |
| `testlib/tracebacks.py` | both | Pickle worker exceptions and remap their frames onto host source roots |

## How in-worker suites are exposed on the host

- A worker project has `src/test_<suite>.py` modules. The worker serves
  `GET /run-tests/<suite>`, runs that module with `pytest.main` and returns
  per-test JSON results keyed by `ResultCollector._key` (`Class__name`).
- `register_in_worker_suites(globals(), src_dir)` in a host test module parses
  each `src/test_<suite>.py` with `ast` and generates one host test per
  in-worker test. Host node IDs mirror the in-worker ones: a class registered
  under the key `test_kv.py` (collected thanks to `__test__ = True`), with
  in-worker classes mirrored as nested classes, e.g.
  `tests/test_bindings.py::test_kv.py::TestFoo::test_bar[3.12]`.
- The suite is run once per `dev_server` (`functools.cache` on
  `get_suite_results`); each host test just looks up its result.

## Conventions and pitfalls

- Keep `host._result_key` and `entrypoint.ResultCollector._key` in sync.
- Python 3.12 (Pyodide 0.26.0a2) reports false passes for async in-worker
  tests; verify failure behaviour on 3.13+.
- `pywrangler sync` in tests may need `UV_NATIVE_TLS=1` on hosts with custom
  CA certificates.
