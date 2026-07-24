from collections.abc import Awaitable
from http import HTTPMethod
from typing import Any, Protocol, TypeAlias, TypedDict

import js
from pyodide.ffi import JsBuffer
from pyodide.http import pyfetch

from .formdata import FormData


class Context(Protocol):
    def waitUntil(self, other: Awaitable[Any]) -> None: ...


JSBody: TypeAlias = (
    "js.Blob | JsBuffer | js.FormData | js.ReadableStream | js.URLSearchParams"
)
Body: TypeAlias = "str | FormData | JSBody"
Headers: TypeAlias = "dict[str, str] | list[tuple[str, str]] | js.Headers"


# https://developers.cloudflare.com/workers/runtime-apis/request/#the-cf-property-requestinitcfproperties
class RequestInitCfProperties(TypedDict, total=False):
    apps: bool | None
    cacheEverything: bool | None
    cacheKey: str | None
    cacheTags: list[str] | None
    cacheTtl: int
    cacheTtlByStatus: dict[str, int]
    image: (
        Any | None
    )  # TODO: https://developers.cloudflare.com/images/transform-images/transform-via-workers/
    mirage: bool | None
    polish: str | None
    resolveOverride: str | None
    scrapeShield: bool | None
    webp: bool | None


# This matches the Request options:
# https://developers.cloudflare.com/workers/runtime-apis/request/#options
class FetchKwargs(TypedDict, total=False):
    headers: "Headers | None"
    body: "Body | None"
    method: HTTPMethod | None
    redirect: str | None
    cf: RequestInitCfProperties | None
    fetcher: type[pyfetch] | None
