import json
from http import HTTPMethod
from typing import Any, Unpack

import js
from pyodide.ffi import JsException, JsProxy

from .blob import Blob
from .formdata import FormData
from .types import FetchKwargs
from .utils import (
    _is_js_instance,
    _js_headers_to_http_message,
    _jsnull_to_none,
    _to_js_headers,
    _to_python_exception,
)


class Request:
    def __init__(
        self, input: "Request | str | js.Request", **other_options: Unpack[FetchKwargs]
    ):
        if _is_js_instance(input, "Request"):
            if len(other_options) > 0:
                raise ValueError(
                    "Expected no options when constructing Request from a js.Request"
                )
            self._js_request = input
            return

        if "method" in other_options and isinstance(
            other_options["method"], HTTPMethod
        ):
            other_options["method"] = other_options["method"].value

        if "headers" in other_options:
            other_options["headers"] = _to_js_headers(other_options["headers"])
        self._js_request = js.Request.new(
            input._js_request if isinstance(input, Request) else input, **other_options
        )

    def __repr__(self):
        return (
            f"Request(method={self._js_request.method!r}, url={self._js_request.url!r})"
        )

    @property
    def js_object(self) -> "js.Request":
        return self._js_request

    # TODO: expose `body` as a native Python stream in the future, follow how we define `Response`
    @property
    def body(self) -> "js.ReadableStream":
        return self.js_object.body

    @property
    def body_used(self) -> bool:
        return self.js_object.bodyUsed

    @property
    def cf(self) -> "JsProxy | None":
        """
        Cloudflare-specific properties about the incoming request
        (IncomingRequestCfProperties).  Access fields via attribute
        notation, for example ``request.cf.colo``.

        Returns None when not present (for example, in the dashboard/playground
        preview or for requests constructed without a ``cf`` value).

        See https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
        """
        return _jsnull_to_none(self.js_object.cf)

    @property
    def cache(self) -> str:
        return self.js_object.cache

    @property
    def credentials(self) -> str:
        return self.js_object.credentials

    @property
    def destination(self) -> str:
        return self.js_object.destination

    @property
    def headers(self):
        return _js_headers_to_http_message(self.js_object.headers)

    @property
    def integrity(self) -> str:
        return self.js_object.integrity

    @property
    def is_history_navigation(self) -> bool:
        return self.js_object.isHistoryNavigation

    @property
    def keepalive(self) -> bool:
        return self.js_object.keepalive

    @property
    def method(self) -> HTTPMethod:
        return HTTPMethod[self.js_object.method]

    @property
    def mode(self) -> str:
        return self.js_object.mode

    @property
    def redirect(self) -> str:
        return self.js_object.redirect

    @property
    def referrer(self) -> str:
        return self.js_object.referrer

    @property
    def referrer_policy(self) -> str:
        return self.js_object.referrerPolicy

    @property
    def url(self) -> str:
        return self.js_object.url

    def _raise_if_failed(self) -> None:
        # TODO: https://github.com/pyodide/pyodide/blob/a53c17fd8/src/py/pyodide/http.py#L252
        if self.body_used:
            # TODO: Use BodyUsedError in newer Pyodide versions.
            raise OSError("Body already used")

    """
    Instance methods defined below.

    The naming of these methods should match Request's methods when possible.

    TODO: AbortController support.
    """

    async def buffer(self) -> "js.ArrayBuffer":
        # The naming of this method matches that of Response.
        self._raise_if_failed()
        return await self.js_object.arrayBuffer()

    async def form_data(self) -> "FormData":
        self._raise_if_failed()
        try:
            return FormData(await self.js_object.formData())
        except JsException as exc:
            raise _to_python_exception(exc) from exc

    async def blob(self) -> Blob:
        self._raise_if_failed()
        return Blob(await self.js_object.blob())

    async def bytes(self) -> bytes:
        self._raise_if_failed()
        return (await self.buffer()).to_bytes()

    def clone(self) -> "Request":
        if self.body_used:
            # TODO: Use BodyUsedError in newer Pyodide versions.
            raise OSError("Body already used")
        return Request(
            self.js_object.clone(),
        )

    async def json(self, **kwargs: Any) -> Any:
        self._raise_if_failed()
        return json.loads(await self.text(), **kwargs)

    async def text(self) -> str:
        self._raise_if_failed()
        return await self.js_object.text()
