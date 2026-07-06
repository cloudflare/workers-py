from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import _pyodide_entrypoint_helper
import js
from pyodide.ffi import (
    JsException,
    destroy_proxies,
    to_js,
)

from .workflows import NonRetryableError

try:
    from pyodide.ffi import jsnull
except ImportError:
    jsnull = None


RESPONSE_ACCEPTED_TYPES = {
    # BufferSource types
    "Blob",
    "ArrayBuffer",
    "TypedArray",
    "DataView",
    "Uint8Array",
    "Uint8ClampedArray",
    "Int8Array",
    "Uint16Array",
    "Int16Array",
    "Uint32Array",
    "Int32Array",
    "Float16Array",
    "Float32Array",
    "Float64Array",
    "BigInt64Array",
    "BigUint64Array",
    # Other types
    "FormData",
    "ReadableStream",
    "URLSearchParams",
    "Response",
}

# JS built-in types that should NOT be wrapped in _BindingWrapper.
# These have their own Python-side semantics (e.g. passed directly to Response())
# and wrapping them breaks property access like `.constructor.name`.
_JS_PASSTHROUGH_TYPES = RESPONSE_ACCEPTED_TYPES | {
    "Headers",
}


def _jsnull_to_none(x):
    if x is jsnull:
        return None
    return x


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


@contextmanager
def patch_env(
    d: dict[str, Any] | Sequence[tuple[str, Any]] | None = None, **kwds: dict[str, Any]
) -> Iterator[None]:
    if d:
        kwds = dict(d) | kwds
    yield from _pyodide_entrypoint_helper.patch_env_helper(to_js(kwds))


def _to_python_exception(exc: JsException) -> Exception:
    if exc.name == "RangeError":
        return ValueError(exc.message)
    elif exc.name == "TypeError":
        return TypeError(exc.message)
    else:
        return exc


def _from_js_error(exc: JsException) -> Exception:
    # convert into Python exception after a full round trip
    # Python - JS - Python
    if not exc.message or not exc.message.startswith("PythonError"):
        return _to_python_exception(exc)

    # extract the Python exception type from the traceback
    error_message_last_line = exc.message.split("\n")[-2]
    if error_message_last_line.startswith("TypeError"):
        return TypeError(error_message_last_line)
    elif error_message_last_line.startswith("ValueError"):
        return ValueError(error_message_last_line)
    elif error_message_last_line.startswith("workers.workflows.NonRetryableError"):
        return NonRetryableError(error_message_last_line)
    else:
        return _to_python_exception(exc)


@contextmanager
def _manage_pyproxies():
    proxies = js.Array.new()
    try:
        yield proxies
    finally:
        destroy_proxies(proxies)


def _is_js_instance(val, js_cls_names: str | set[str]):
    if not hasattr(val, "constructor"):
        return False
    name = val.constructor.name
    if isinstance(js_cls_names, set):
        return name in js_cls_names
    return name == js_cls_names


try:
    import _cloudflare_compat_flags
except ImportError:
    _cloudflare_compat_flags = object()


def get_compat_flag(flag: str) -> bool:
    return getattr(_cloudflare_compat_flags, flag, False)


def _to_js_headers(headers):
    if isinstance(headers, list):
        # We should have a list[tuple[str, str]]
        return js.Headers.new(headers)
    elif isinstance(headers, dict):
        return js.Headers.new(headers.items())
    elif _is_js_instance(headers, "Headers"):
        return headers
    else:
        raise TypeError("Received unexpected type for headers argument")


def _js_headers_to_http_message(
    js_headers: dict[str, str],
):
    # `http.client` is imported here because it costs a lot of CPU time when imported at the
    # top-level. At least it does when we do so in our validator tests, doesn't seem to cause
    # trouble in production. So as a workaround we do the import here.
    #
    # TODO(later): when dedicated snapshots are default we can move this import to the top-level.
    import http.client

    # Newer Pyodide versions already expose headers as an http.client.HTTPMessage,
    # in which case there is nothing to convert.
    if isinstance(js_headers, http.client.HTTPMessage):
        return js_headers

    result = http.client.HTTPMessage()
    if not get_compat_flag("python_request_headers_preserve_commas"):
        for key, val in js_headers:
            result[key] = val.strip()

        return result

    # With the exception of Set-Cookie, duplicate headers can and are combined with a comma
    # in the JS Headers API. We do the same when returning the headers to Python.
    #
    # See https://httpwg.org/specs/rfc9110.html#rfc.section.5.3.
    set_cookie_headers = js_headers.getSetCookie()
    if set_cookie_headers:
        for value in set_cookie_headers:
            result.add_header("Set-Cookie", value.strip())

    for key, val in js_headers:
        if key.lower() == "set-cookie":
            continue
        result.add_header(key, val.strip())

    return result


def _get_js_constructor_name(obj) -> str | None:
    if hasattr(obj, "constructor"):
        return obj.constructor.name
    return None


def _supports_buffer_protocol(o):
    try:
        # memoryview used only for testing type; 'with' releases the view instantly
        with memoryview(o):
            return True
    except TypeError:
        return False


def _is_iterable(obj):
    if isinstance(obj, (str, bytes)):
        return False
    try:
        iter(obj)
    except TypeError:
        return False
    else:
        return True
