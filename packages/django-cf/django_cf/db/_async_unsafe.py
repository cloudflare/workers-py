"""Helper for removing Django's ``async_unsafe`` guard from backend methods."""

from django.utils import asyncio as _django_asyncio


def _async_unsafe_probe():
    pass


# Capture async_unsafe function so we don't accidentally unwrap something else
_ASYNC_UNSAFE_WRAPPER_CODE = _django_asyncio.async_unsafe(_async_unsafe_probe).__code__


def _unwrap_async_unsafe(method):
    """
    Unwrap Django's async_unsafe decorator to get the original method.

    This is needed because Django does not allow calling database operations
    from within an async context, but Python workers always run in an async context.

    All the database backends that django-cf provides are async-safe so we need
    to unwrap the async_unsafe decorator to allow calling database operations
    from within an async context.
    """
    method_code = getattr(method, "__code__", None)
    is_async_unsafe = method_code is _ASYNC_UNSAFE_WRAPPER_CODE
    wrapped = getattr(method, "__wrapped__", None)

    if is_async_unsafe:
        return wrapped

    return method
