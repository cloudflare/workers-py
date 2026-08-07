"""
Loader shim for the top level package patches.

This module is imported by the .pth file on every Python startup. The patches
depend on the `_cloudflare` package, which only exists inside the workers
runtime. When running outside of the workers runtime, `_cloudflare` is not
available, so we silently skip loading the patches. Skipping is also what we
want in that case: the patches adapt packages to the workers runtime and should
not change how they behave under native Python.
"""

import importlib.util

if importlib.util.find_spec("_cloudflare") is not None:
    import _workers_sdk_entropy_import_context  # noqa: F401
    import _workers_sdk_package_patches  # noqa: F401
