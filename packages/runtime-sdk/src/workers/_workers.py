# This module defines a Workers API for Python. It is similar to the API provided by
# JS Workers, but with changes and additions to be more idiomatic to the Python
# programming language.
import functools
import inspect
from asyncio import create_task, gather
from typing import TYPE_CHECKING, Any

import _cloudflare_compat_flags

# Get globals modules and import function from the entrypoint-helper
import _pyodide_entrypoint_helper
import js
from js import Object
from pyodide.ffi import (
    JsProxy,
    create_once_callable,
    to_js,
)

from .fetch import fetch
from .request import Request
from .rpc import python_from_rpc, python_to_rpc
from .utils import (
    _JS_PASSTHROUGH_TYPES,
    _from_js_error,
    _get_js_constructor_name,
    _is_js_instance,
)

if TYPE_CHECKING:
    from js import DurableObjectState, Env, ExecutionContext


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

    def _convert_result(self, result):
        converted = python_from_rpc(result)

        # After python_from_rpc, some objects may still be JsProxy objects.
        # We need to wrap them with _BindingWrapper (or a subclass of it) again
        # to ensure that accessing attributes on them will be properly converted.
        if self._should_wrap_nested_attribute(converted):
            return self.__class__(converted)
        if isinstance(converted, list):
            return [
                self.__class__(item)
                if self._should_wrap_nested_attribute(item)
                else item
                for item in converted
            ]
        return converted

    @staticmethod
    def _convert_args(args, kwargs):
        js_args = [python_to_rpc(arg) for arg in args]
        js_kwargs = {k: python_to_rpc(v) for k, v in kwargs.items()}
        return js_args, js_kwargs

    def _getattr_helper(self, name):
        attr = getattr(self._binding, name)

        if not callable(attr):
            return self._convert_result(attr)

        def wrapper(*args, **kwargs):
            js_args, js_kwargs = self._convert_args(args, kwargs)
            result = attr(*js_args, **js_kwargs)
            if hasattr(result, "then") and callable(result.then):

                async def await_and_convert():
                    return self._convert_result(await result)

                return await_and_convert()
            return self._convert_result(result)

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

    def __len__(self):
        binding = self._binding
        if not hasattr(binding, "length"):
            raise TypeError(f"'{self._real_name}' object has no len()")
        return binding.length


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


class DurableObjectAbort(BaseException):
    pass


class DurableObjectContext:
    # __new__ and __init__ set up to make sure that the following passes:
    #
    # a = DurableObjectContext(x)
    # assert DurableObjectContext(a) is a
    # assert a._ctx is x
    __new__ = _idempotent_new

    def __init__(self, ctx: "DurableObjectState"):
        if ctx is self:
            return
        self._ctx = ctx

    def __getattr__(self, name: str):
        result = getattr(self._ctx, name)
        if _is_js_instance(result, "DurableObjectStorage"):
            # durable_object.ctx.storage
            result = _BindingWrapper(result)
        setattr(self, name, result)
        return result

    def abort(self, reason: str | None = None):
        # DurableObjectState.abort() terminates JS execution immediately. If Python
        # calls it synchronously while asyncio is still running the task in the event loop,
        # V8 unwinds the stack before asyncio can run its task-exit cleanup, leaving
        # stale task state behind for the next request.
        #
        # Therefore, we queue the real abort into a microtask so Python can unwind first,
        # then raise BaseException to stop user code without being swallowed by
        # `except Exception` handlers.
        ctx = self._ctx

        if reason is None:
            callback = create_once_callable(lambda: ctx.abort())
        else:
            callback = create_once_callable(lambda: ctx.abort(reason))

        js.queueMicrotask(callback)
        raise DurableObjectAbort(reason or "Durable Object abort requested")


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
        "AnalyticsEngineDataset",
        "LocalAnalyticsEngineDataset",
        "ImagesBindingImpl",
        "HostedImagesBindingImpl",
        "Ratelimit",
    }

    __new__ = _idempotent_new

    def __init__(self, env: Any):
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


def handler(func):
    """
    When applied to handlers such as `on_fetch` it will rewrite arguments passed in to native Python
    types defined in this module. For example, the `request` argument to `on_fetch` gets converted
    to an instance of the Request class defined in this module.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # TODO: support transforming kwargs
        if len(args) > 0 and _is_js_instance(args[0], "Request"):
            args = (Request(args[0]), *args[1:])

        # Wrap `env` so that bindings can be used without to_js.
        if len(args) > 1:
            args = (args[0], _EnvWrapper(args[1]), *args[2:])

        return func(*args, **kwargs)

    return wrapper


class _WorkflowStepWrapper:
    __new__ = _idempotent_new

    def __init__(self, js_step):
        if js_step is self:
            return
        self._js_step = js_step
        self._memoized_dependencies = {}
        self._in_flight = {}
        self.step_closures = {}

        # Assign the appropriate method based on compat flag
        if _cloudflare_compat_flags.python_workflows_implicit_dependencies:
            self.do = self._do_implicit
        else:
            self.do = self._do_legacy

    def _do_legacy(self, name, depends=None, concurrent=False, config=None):
        """Original signature - positional args allowed, explicit depends parameter."""
        return self._create_step_decorator(
            name=name,
            depends=depends,
            concurrent=concurrent,
            config=config,
            implicit=False,
        )

    def _do_implicit(self, name=None, *, concurrent=False, config=None):
        """New signature - keyword-only args, dependencies resolved from param names."""
        return self._create_step_decorator(
            name=name,
            depends=None,
            concurrent=concurrent,
            config=config,
            implicit=True,
        )

    def _create_step_decorator(self, name, depends, concurrent, config, implicit):
        """Shared decorator factory for both legacy and implicit modes."""

        def decorator(func):
            step_name = func.__name__ if name is None else name

            async def wrapper():
                results_future_list = self._build_dependency_list(
                    func, depends, implicit
                )
                results = await self._gather_results(results_future_list, concurrent)
                return await _do_call(self, step_name, config, func, *results)

            wrapper._step_name = step_name
            self.step_closures[step_name] = wrapper
            return wrapper

        return decorator

    def _build_dependency_list(self, func, depends, implicit):
        """Build the dependency list based on mode (implicit vs legacy)."""
        sig = inspect.signature(func)
        results_future_list = []

        if implicit:
            # Implicit mode: resolve dependencies from parameter names
            for p in sig.parameters.values():
                if p.name in self.step_closures:
                    results_future_list.append(self.step_closures[p.name])
                elif p.name == "ctx":
                    results_future_list.append(p)
                else:
                    raise TypeError(f"Received unexpected parameter {p.name}")
        else:
            # Legacy mode: use explicit depends list, support ctx parameter
            non_ctx_params = [p for p in sig.parameters.values() if p.name != "ctx"]

            if depends is None and len(non_ctx_params) > 0:
                raise TypeError(
                    f"Step has {len(non_ctx_params)} non-ctx parameter(s) but no 'depends' list provided"
                )

            elif depends is not None and len(depends) != len(non_ctx_params):
                raise TypeError(
                    f"Step declares {len(non_ctx_params)} non-ctx parameter(s) but 'depends' has {len(depends)} item(s)"
                )

            curr = 0
            for p in sig.parameters.values():
                if p.name == "ctx":
                    results_future_list.append(p)
                else:
                    results_future_list.append(depends[curr])
                    curr += 1

        return results_future_list

    async def _gather_results(self, results_future_list, concurrent):
        """Resolve dependencies concurrently or sequentially."""
        if concurrent:
            return await gather(
                *[self._resolve_dependency(dep) for dep in results_future_list or []]
            )
        else:
            return [
                await self._resolve_dependency(dep) for dep in results_future_list or []
            ]

    def sleep(self, *args, **kwargs):
        return self._js_step.sleep(*args, **kwargs)

    def sleep_until(self, name, timestamp):
        if not isinstance(timestamp, str):
            timestamp = python_to_rpc(timestamp)

        return self._js_step.sleepUntil(name, timestamp)

    async def wait_for_event(self, name, event_type, /, timeout="24 hours"):
        return python_from_rpc(
            await self._js_step.waitForEvent(
                name,
                to_js(
                    {"type": event_type, "timeout": timeout},
                    dict_converter=Object.fromEntries,
                ),
            )
        )

    async def _resolve_dependency(self, dep):
        if hasattr(dep, "name") and dep.name == "ctx":
            return dep
        elif dep._step_name in self._memoized_dependencies:
            return self._memoized_dependencies[dep._step_name]
        elif dep._step_name in self._in_flight:
            return await self._in_flight[dep._step_name]

        return await dep()


async def _do_call(entrypoint, name, config, callback, *results):
    async def _callback(ctx=None):
        # deconstruct the actual ctx object
        resolved_results = tuple(
            python_from_rpc(ctx)
            if isinstance(r, inspect.Parameter) and r.name == "ctx"
            else r
            for r in results
        )
        result = callback(*resolved_results)

        if inspect.iscoroutine(result):
            result = await result
        return to_js(result, dict_converter=Object.fromEntries)

    async def _closure():
        try:
            if config is None:
                coroutine = await entrypoint._js_step.do(name, _callback)
            else:
                coroutine = await entrypoint._js_step.do(
                    name, to_js(config, dict_converter=Object.fromEntries), _callback
                )

            return python_from_rpc(coroutine)
        except Exception as exc:
            raise _from_js_error(exc) from exc

    task = create_task(_closure())
    entrypoint._in_flight[name] = task

    try:
        result = await task
        entrypoint._memoized_dependencies[name] = result
    finally:
        del entrypoint._in_flight[name]

    return result


def _wrap_class(cls):
    # Override the class __init__ so that we can wrap the `env` in the constructor.
    original_init = cls.__dict__.get("__init__")
    if original_init is None:
        return cls

    def wrapped_init(self, *args, **kwargs):
        args = list(args)
        if len(args) > 0:
            _pyodide_entrypoint_helper.patchWaitUntil(args[0])
            if issubclass(cls, DurableObject):
                args[0] = DurableObjectContext(args[0])
        if len(args) > 1:
            args[1] = _EnvWrapper(args[1])

        original_init(self, *args, **kwargs)

    cls.__init__ = wrapped_init
    return cls


def _wrap_workflow_step(cls):
    run_fn = cls.__dict__.get("run")
    if run_fn is None:
        return

    @functools.wraps(run_fn)
    async def wrapped_run(self, event=None, step=None, /, *args, **kwargs):
        if event is not None:
            event = python_from_rpc(event)
        if step is not None:
            step = _WorkflowStepWrapper(step)

        result = run_fn(self, event, step, *args, **kwargs)

        if inspect.iscoroutine(result):
            result = await result

        if result is None:
            return result

        # This should be wrapped again to js object
        # as the value will go through the RPC boundary
        return python_to_rpc(result)

    cls.run = wrapped_run


@_wrap_class
class DurableObject:
    """
    Base class used to define a Durable Object.
    """

    ctx: "DurableObjectContext"
    env: "Env"

    def __init__(self, ctx: "DurableObjectState", env: "Env"):
        self.ctx = ctx
        self.env = env

    def __init_subclass__(cls, **_kwargs):
        _wrap_class(cls)


@_wrap_class
class WorkerEntrypoint:
    """
    Base class used to define a Worker Entrypoint.
    """

    ctx: "ExecutionContext"
    env: "Env"

    def __init__(self, ctx: "ExecutionContext", env: "Env"):
        self.ctx = ctx
        self.env = env

    def __init_subclass__(cls, **_kwargs: Any):
        _wrap_class(cls)
        _wrap_queue_handler(cls)


@_wrap_class
class WorkflowEntrypoint:
    """
    Base class used to define a Workflow Entrypoint.
    """

    ctx: "ExecutionContext"
    env: "Env"

    def __init__(self, ctx: "ExecutionContext", env: "Env"):
        self.ctx = ctx
        self.env = env

    def __init_subclass__(cls, **_kwargs: Any):
        _wrap_class(cls)
        _wrap_workflow_step(cls)


def _wrap_queue_handler(cls):
    queue_fn = getattr(cls, "queue", None)
    if queue_fn is None:
        return

    @functools.wraps(queue_fn)
    async def wrapped_queue(self, batch, *args, **kwargs):
        wrapped_batch = _BindingWrapper(batch)
        result = queue_fn(self, wrapped_batch, *args, **kwargs)
        if inspect.iscoroutine(result):
            result = await result
        return result

    cls.queue = wrapped_queue
