from ._workers import (
    DurableObject,
    WorkerEntrypoint,
    WorkflowEntrypoint,
    _EnvWrapper,
    handler,
)
from .blob import Blob, BlobEnding, BlobValue, File
from .fetch import fetch
from .formdata import FormData, FormDataValue
from .request import Request
from .response import FetchResponse, Response
from .rpc import python_from_rpc, python_to_rpc
from .types import (
    Body,
    Context,
    FetchKwargs,
    Headers,
    JSBody,
    RequestInitCfProperties,
)
from .utils import import_from_javascript, patch_env

__all__ = [
    "Blob",
    "BlobEnding",
    "BlobValue",
    "Body",
    "Context",
    "DurableObject",
    "FetchKwargs",
    "FetchResponse",
    "File",
    "FormData",
    "FormDataValue",
    "Headers",
    "JSBody",
    "Request",
    "RequestInitCfProperties",
    "Response",
    "WorkerEntrypoint",
    "WorkflowEntrypoint",
    "env",
    "fetch",
    "handler",
    "import_from_javascript",
    "patch_env",
    "python_from_rpc",
    "python_to_rpc",
    "waitUntil",
    "wait_until",
]


def __getattr__(key):
    if key == "env":
        cloudflare_workers = import_from_javascript("cloudflare:workers")
        return _EnvWrapper(cloudflare_workers.env)
    if key in ("wait_until", "waitUntil"):
        cloudflare_workers = import_from_javascript("cloudflare:workers")
        return cloudflare_workers.waitUntil
    raise AttributeError(f"module {__name__!r} has no attribute {key!r}")
