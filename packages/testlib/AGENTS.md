# packages/testlib

## Overview

`testlib` holds shared helpers for tests that run pytest *inside* workerd. It is
not published; `runtime-sdk` and `django-cf` vendor it into their test workers
via `../packages/testlib` in `[tool.uv.sources]`.

## Key modules

| Module | Runs on | Purpose |
|---|---|---|
| `testlib/host.py` | host | `dev_server`, `pywrangler_sync`, `register_in_worker_suites`, arg/keyword forwarding |
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

## Forwarding from the outer to the inner pytest run

- `worker_pytest_args(config)` forwards `config.invocation_params.args` minus
  positional targets and `HOST_ONLY_OPTIONS` (currently `-m/--markexpr`).
  `addopts` are never forwarded. Sent as repeated `?arg=` query params.
- `host_only_keywords(item)` sends the `-k` keywords that exist only on the host
  (ancestor names such as `test_bindings.py`, suite marks, the compat-config
  param such as `3.12`) as repeated `?kw=` params; `ExtraKeywordsPlugin` adds
  them to in-worker items so `-k` selects the same tests on both sides.
- Workers that don't subclass `TestRunnerEntrypoint` (e.g. the FastAPI test
  worker) must build a `RunSuiteRequest` from the query string themselves.

## Conventions and pitfalls

- Keep `host._result_key` and `entrypoint.ResultCollector._key` in sync.
- Add host-only options to `HOST_ONLY_OPTIONS` as they turn up (plugin options
  not installed in the worker, e.g. `-n`, `--cov`, `--lf`, produce an inner
  usage error surfaced as a 500).
- `-x`/`--maxfail` stops the inner session early; later host tests in that
  suite then fail as "not found in results".
- Python 3.12 (Pyodide 0.26.0a2) reports false passes for async in-worker
  tests; verify failure behaviour on 3.13+.
- `pywrangler sync` in tests may need `UV_NATIVE_TLS=1` on hosts with custom
  CA certificates.
