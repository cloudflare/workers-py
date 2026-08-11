# pyright: reportMissingImports=false
"""Shared helpers for the Hyperdrive suites.

Unlike every other binding, Hyperdrive is reached over a real TCP socket rather
than a JavaScript API, so these suites need `socket` to work inside workerd.
"""

import re
import uuid

import pyodide
import pytest

# workerd mounts Pyodide's NodeSockFS (backed by `cloudflare:sockets`) during
# startup, which is what makes the `socket` module functional. That landed in
# workerd 1.20260805.1, which bundles Pyodide 314.0.3; older bundles ship a
# stock Emscripten SOCKFS whose `close()` aborts the entire isolate instead of
# raising (pyodide#6312), so we have to skip *before* opening a connection
# rather than letting the failure surface as a test error.
MIN_PYODIDE_VERSION = (314, 0, 3)


def _pyodide_version() -> tuple[int, ...]:
    # Release names are not always PEP 440 clean (e.g. "0.26.0a2").
    return tuple(int(part) for part in re.findall(r"\d+", pyodide.__version__)[:3])


requires_sockets = pytest.mark.skipif(
    _pyodide_version() < MIN_PYODIDE_VERSION,
    reason=(
        "TCP sockets need Pyodide >= "
        f"{'.'.join(str(part) for part in MIN_PYODIDE_VERSION)} "
        "(workerd >= 1.20260805.1)"
    ),
)


def unique_table_name() -> str:
    """Unique per call: CI databases outlive a run and every compat config replays the suite."""
    return f"test_{uuid.uuid4().hex[:10]}"
