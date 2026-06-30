import datetime
import inspect

import js
from js import Object
from pyodide.ffi import JsProxy, create_proxy, to_js

from .blob import Blob, File
from .formdata import FormData
from .request import Request
from .response import Response
from .utils import _is_iterable, _is_js_instance, jsnull


def _python_from_rpc_default_converter(value, convert, cache):
    if value is jsnull:
        return None

    if not hasattr(value, "constructor"):
        # Assume that the object doesn't need conversion as it's not a JS object.
        return value

    if value.constructor.name == "Response":
        return Response(value)
    elif value.constructor.name == "FormData":
        return FormData(value)
    elif value.constructor.name == "Blob":
        return Blob(value)
    elif value.constructor.name == "File":
        return File(value)
    elif value.constructor.name == "Request":
        return Request(value)
    elif value.constructor.name == "Date":
        # TODO: Pyodide should gain support for this, we should upstream this.
        return datetime.datetime.fromtimestamp(value.getTime() / 1000)
    elif value.constructor.name == "Error":
        return Exception(value.toString())
    elif value.constructor.name == "Number":
        return value.valueOf()

    # We used to throw an error here, but since these conversions are now automatic when the default
    # entrypoint is being used, it makes sense to be less loud about it and just pass through the
    # JS value un-modified.
    #
    # This does mean that in the future we need to be careful when adding type wrappers for new
    # types here, so if you're doing this make sure to do so behind a compat flag.
    return value


class JsDict(dict):
    """
    Python dictionary that allows attribute access to keys.

    This is used to convert JS objects to Python dictionaries while maintaining
    the ability to access keys as attributes.
    """

    def __getattr__(self, name):
        # The limitation of this approach is that if there is a key that conflicts with a built-in
        # method or attribute of the dict class, it will not be accessible through attribute access.
        # But that is a reasonable trade-off for the convenience of being able to access keys as
        # attributes.
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        self[name] = value


def _replace_jsnull_with_none(obj):
    """
    Recursively converts JS objects to Python objects.
    """
    if obj is jsnull:
        return None
    if isinstance(obj, dict):
        return JsDict({k: _replace_jsnull_with_none(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_replace_jsnull_with_none(v) for v in obj]
    return obj


def python_from_rpc(obj: "JsProxy"):
    """
    Converts JS objects like Response, Request, Blob, etc. to equivalent Python objects defined in
    this module and also other JS objects like Map, Set, etc. to equivalent Python stdlib objects.

    This method is used for Workers RPC in Python to convert JavaScript objects to Python. As such
    it does not support serializing all JS object types.
    """

    if obj is jsnull:
        return None

    if not hasattr(obj, "constructor"):
        return obj

    if obj.constructor.name == "TestController":
        # This object currently has no methods defined on it. If this changes we should
        # implement a Python wrapper for it, but for now we'll just pass in None.
        return None

    result = obj.to_py(default_converter=_python_from_rpc_default_converter)

    return _replace_jsnull_with_none(result)


def _raise_on_disabled_type(value):
    # Lazy import: _BindingWrapper is defined in _workers.py
    from ._workers import _BindingWrapper

    if isinstance(value, _BindingWrapper):
        return

    if callable(value) and not isinstance(value, type):
        return

    if _is_js_instance(value, "RegExp"):
        raise TypeError(f"{value.constructor.name} cannot be sent over RPC.")

    if isinstance(value, (tuple, bytearray)):
        raise TypeError(f"{type(value)} cannot be sent over RPC.")

    if inspect.isawaitable(value):
        # The caller is expected to await the value prior to conversion.
        raise TypeError(f"Awaitable {type(value)} cannot be sent over RPC.")

    if _is_iterable(value):
        if isinstance(value, dict):
            for v in value.values():
                _raise_on_disabled_type(v)
        else:
            for v in value:
                _raise_on_disabled_type(v)


def _python_to_rpc_default_converter(obj, convert, cache):
    # Lazy import: _BindingWrapper is defined in _workers.py
    from ._workers import _BindingWrapper

    if obj is None:
        return jsnull

    if isinstance(obj, _BindingWrapper):
        return obj._binding

    if hasattr(obj, "js_object"):
        return obj.js_object

    if isinstance(obj, datetime.datetime):
        # TODO: Pyodide should gain support for this, we should upstream this.
        return js.Date.new(obj.timestamp() * 1000)

    if isinstance(obj, Exception):
        return js.Error.new(str(obj))

    if callable(obj) and not isinstance(obj, type):
        # Wrap function with create_proxy so that
        # it doesn't get garbage collected
        return create_proxy(obj)

    _raise_on_disabled_type(obj)

    return obj


def _replace_none_with_jsnull(value):
    if value is None:
        return jsnull
    if isinstance(value, dict):
        return {k: _replace_none_with_jsnull(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_none_with_jsnull(v) for v in value]
    return value


def python_to_rpc(value) -> JsProxy:
    """
    Converts Python objects defined in this module (Response, Request, etc) and native Python types
    like Map, Set, datetime to equivalent JavaScript types.

    This method is used for Workers RPC in Python to convert Python objects to JavaScript. As such
    it does not support serializing all Python object types.
    """
    # Lazy import: _BindingWrapper is defined in _workers.py
    # TODO: refactor more to avoid circular imports
    from ._workers import _BindingWrapper

    if value is None:
        return jsnull

    if isinstance(value, _BindingWrapper):
        return value._binding

    value = _replace_none_with_jsnull(value)

    # `to_js` won't always call the default_converter, for example when a list of tuples is passed
    _raise_on_disabled_type(value)

    result = to_js(
        value,
        default_converter=_python_to_rpc_default_converter,
        dict_converter=Object.fromEntries,
    )

    return result
