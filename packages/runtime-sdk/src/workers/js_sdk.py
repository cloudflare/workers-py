import functools
from typing import Any

import _pyodide_entrypoint_helper
from pyodide import __version__ as pyodide_version
from pyodide.ffi import JsException


def import_from_javascript(module_name: str) -> Any:
    """
    Import a JavaScript ES module from Python.

    Args:
        module_name: The name of the module to import. This can be a module name or a path.

    Returns:
        The imported module object.

    Example:
        cloudflare_workers = import_from_javascript("cloudflare:workers")
        env = cloudflare_workers.env

    Note:
        Behind the scenes import_from_javascript uses JSPI to do imports but that means we need an
        async context. To enable importing cloudflare:workers and cloudflare:sockets in the global
        scope we specifically imported them in the global scope and exposed them here.
    """
    # Special case for global scope available modules
    # JSPI won't work in the global scope in 0.26.0a2 so we need modules importable in the global
    # scope to be imported beforehand.
    if module_name == "cloudflare:workers":
        return _pyodide_entrypoint_helper.cloudflareWorkersModule
    elif module_name == "cloudflare:sockets":
        return _pyodide_entrypoint_helper.cloudflareSocketsModule

    try:
        from pyodide.ffi import run_sync

        # Call the JavaScript import function
        return run_sync(_pyodide_entrypoint_helper.doAnImport(module_name))
    except JsException as e:
        raise ImportError(f"Failed to import '{module_name}': {e}") from e
    except RuntimeError as e:
        if e.args[0] == "No suspender":
            raise ImportError(
                f"Failed to import '{module_name}': Only 'cloudflare:workers' and 'cloudflare:sockets' are available in the global scope."
            ) from e
        raise
    except ImportError as e:
        if e.args[0].startswith("cannot import name 'run_sync' from 'pyodide.ffi'"):
            raise ImportError(
                f"Failed to import '{module_name}': Only 'cloudflare:workers' and 'cloudflare:sockets' are available until the next python runtime version."
            ) from e
        raise


@functools.cache
def get_js_sdk():
    # IMPORTANT:
    # The module name here must match how wrangler registers the JS modules
    # while vendoring the python_modules directory.
    # See: https://github.com/cloudflare/workers-sdk/pull/13311
    return import_from_javascript("python_modules/workers/sdk.mjs")


def patch_wait_until(ctx):
    """
    Patch the waitUntil method of the given context to ensure that async operations are properly handled.
    """
    if pyodide_version == "0.26.0a2":
        _pyodide_entrypoint_helper.patchWaitUntil(ctx)
        return

    js_sdk = get_js_sdk()
    js_sdk.patchWaitUntil(ctx)
