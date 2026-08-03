import datetime
import inspect

import js
from js import Object
from pyodide.ffi import JsProxy, create_proxy, to_js

from .blob import Blob, File
from .fetch import fetch
from .formdata import FormData
from .request import Request
from .response import Response
from .utils import (
    _JS_PASSTHROUGH_TYPES,
    _get_js_constructor_name,
    _is_iterable,
    _is_js_instance,
    jsnull,
)


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


# ---------------------------------------------------------------------------
# Binding wrappers
# ---------------------------------------------------------------------------


def _idempotent_new(cls, obj):
    """Set __new__ on a class to this so cls is idempotent:

    >>> a = A(x)
    >>> b = A(a)
    >>> assert a is b

    For this to work, start the __init__ function with:

    if obj is self:
        return

    to prevent double-init.
    """
    if isinstance(obj, cls):
        return obj
    return object.__new__(cls)


class _BindingWrapper:
    __new__ = _idempotent_new

    def __init__(self, binding):
        if binding is self:
            return
        self._binding = binding

    @property
    def _real_name(self):
        js_name = _get_js_constructor_name(self._binding)
        if not js_name:
            # Should not happen, but just in case
            return type(self).__name__
        return js_name

    def _should_wrap_nested_attribute(self, jsobj) -> bool:
        if not isinstance(jsobj, JsProxy):
            return False

        # TODO: This allowlist approach is a workaround. The long-term fix is to
        # add dedicated Python wrappers for these types in python_from_rpc so they
        # never reach _BindingWrapper in the first place.
        js_type = _get_js_constructor_name(jsobj)
        return js_type and js_type not in _JS_PASSTHROUGH_TYPES

    def _wrap_js_value(self, value):
        """
        Wrap JSProxy returned from RPC calls with a
        proper wrapper class.
        """
        if not self._should_wrap_nested_attribute(value):
            return value

        # A function or RpcTarget returned over RPC arrives as a callable JsRpcStub.
        # Boxing it in a wrapper that has __call__ allows it to be called.
        if callable(value):
            return _RpcStubWrapper(value)

        return self.__class__(value)

    def _convert_result(self, result):
        converted = python_from_rpc(result)

        # After python_from_rpc, some objects may still be JsProxy objects.
        # We need to wrap them with _BindingWrapper (or a subclass of it) again
        # to ensure that accessing attributes on them will be properly converted.
        if isinstance(converted, list):
            return [self._wrap_js_value(item) for item in converted]
        return self._wrap_js_value(converted)

    @staticmethod
    def _convert_args(args, kwargs):
        js_args = [python_to_rpc(arg) for arg in args]
        js_kwargs = {k: python_to_rpc(v) for k, v in kwargs.items()}
        return js_args, js_kwargs

    def _conver_and_invoke(self, fn, args, kwargs):
        js_args, js_kwargs = self._convert_args(args, kwargs)
        result = fn(*js_args, **js_kwargs)
        if hasattr(result, "then") and callable(result.then):

            async def await_and_convert():
                return self._convert_result(await result)

            return await_and_convert()
        return self._convert_result(result)

    def _getattr_helper(self, name):
        attr = getattr(self._binding, name)

        if not callable(attr):
            return self._convert_result(attr)

        def wrapper(*args, **kwargs):
            return self._conver_and_invoke(attr, args, kwargs)

        return wrapper

    def __getattr__(self, name):
        result = self._getattr_helper(name)
        setattr(self, name, result)
        return result

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._convert_result(self._binding[key])
        return self._convert_result(getattr(self._binding, key))

    def __iter__(self):
        binding = self._binding
        if not hasattr(binding, "__iter__"):
            raise TypeError(f"'{self._real_name}' object is not iterable")
        for item in binding:
            yield self._convert_result(item)

    def __bool__(self):
        return self._binding is not None

    def __len__(self):
        length = getattr(self._binding, "length", None)
        # RPC object always returns true for attribute lookup,
        # so make sure it is actually a numeric length.
        if not isinstance(length, int):
            raise TypeError(f"'{self._real_name}' object has no len()")
        return length


class _RpcStubWrapper(_BindingWrapper):
    """
    A function or RpcTarget received over RPC.

    Calling is always allowed but the server will reject it
    if the target turns out not to be callable.
    """

    def __call__(self, *args, **kwargs):
        return self._conver_and_invoke(self._binding, args, kwargs)


class _FetcherWrapper(_BindingWrapper):
    def fetch(self, *args, **kwargs):
        return fetch(*args, fetcher=self._binding.fetch, **kwargs)


class _DurableObjectNamespaceWrapper:
    def __init__(self, binding):
        self._binding = binding

    def __getattr__(self, name):
        return getattr(self._binding, name)

    def get(self, *args, **kwargs):
        return _FetcherWrapper(self._binding.get(*args, **kwargs))

    def getByName(self, *args, **kwargs):
        return _FetcherWrapper(self._binding.getByName(*args, **kwargs))

    def jurisdiction(self, *args, **kwargs):
        return _DurableObjectNamespaceWrapper(
            self._binding.jurisdiction(*args, **kwargs)
        )


class _WorkflowInstanceWrapper(_BindingWrapper):
    # status/pause/resume/restart/terminate share their JS names and are handled by
    # the _BindingWrapper, which already converts arguments and results.
    # Only send_event needs the snake_case -> camelCase mapping for backward compatibility

    async def send_event(self, *args, **kwargs):
        js_args, js_kwargs = self._convert_args(args, kwargs)
        return self._convert_result(
            await self._binding.sendEvent(*js_args, **js_kwargs)
        )


class _WorkflowBindingWrapper(_BindingWrapper):
    async def get(self, *args, **kwargs):
        js_args, js_kwargs = self._convert_args(args, kwargs)
        return _WorkflowInstanceWrapper(await self._binding.get(*js_args, **js_kwargs))

    async def create(self, *args, **kwargs):
        js_args, js_kwargs = self._convert_args(args, kwargs)
        return _WorkflowInstanceWrapper(
            await self._binding.create(*js_args, **js_kwargs)
        )

    async def create_batch(self, *args, **kwargs):
        js_args, js_kwargs = self._convert_args(args, kwargs)
        return [
            _WorkflowInstanceWrapper(w)
            for w in await self._binding.createBatch(*js_args, **js_kwargs)
        ]


class _EnvWrapper:
    _BINDING_TYPES = {
        "KvNamespace",
        "R2Bucket",
        "D1Database",
        "WorkerQueue",
        "Ai",
        "VectorizeIndexImpl",
        "AnalyticsEngine",
        "AnalyticsEngineDataset",
        "LocalAnalyticsEngineDataset",
        "ImagesBindingImpl",
        "HostedImagesBindingImpl",
        "Ratelimit",
    }

    __new__ = _idempotent_new

    def __init__(self, env):
        if env is self:
            return
        self._env = env

    def _getattr_helper(self, name):
        binding = getattr(self._env, name)
        if _is_js_instance(binding, "Fetcher"):
            return _FetcherWrapper(binding)

        if _is_js_instance(binding, "DurableObjectNamespace"):
            return _DurableObjectNamespaceWrapper(binding)

        if _is_js_instance(binding, "WorkflowImpl"):
            return _WorkflowBindingWrapper(binding)

        if _is_js_instance(binding, self._BINDING_TYPES):
            return _BindingWrapper(binding)

        return binding

    def __getattr__(self, name):
        result = self._getattr_helper(name)
        setattr(self, name, result)
        return result
