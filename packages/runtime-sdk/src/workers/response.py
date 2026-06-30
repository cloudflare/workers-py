import json
from contextlib import contextmanager
from http import HTTPStatus
from typing import Any, Never

import js
import pyodide.http
from pyodide.ffi import JsException, JsProxy, create_proxy

from .blob import Blob
from .formdata import FormData
from .types import Body, Headers
from .utils import (
    RESPONSE_ACCEPTED_TYPES,
    _get_js_constructor_name,
    _is_js_instance,
    _js_headers_to_http_message,
    _jsnull_to_none,
    _to_js_headers,
    _to_python_exception,
)


@contextmanager
def _get_js_body(body):
    if isinstance(body, bytes):
        proxy_bytes = create_proxy(body)
        proxy_buffer = proxy_bytes.getBuffer()
        try:
            yield proxy_buffer.data
            return
        finally:
            proxy_buffer.release()
            proxy_bytes.destroy()
    if isinstance(body, FormData):
        yield body.js_object
        return
    yield body


class FetchResponse(pyodide.http.FetchResponse):
    # TODO: Consider upstreaming the `body` attribute
    # TODO: Behind a compat flag make this return a native stream (StreamReader?), or perhaps
    #       behind a different name, maybe `stream`?
    @property
    def body(self) -> "js.ReadableStream":
        """
        Returns the body as a JavaScript ReadableStream from the JavaScript Response instance.
        """
        return _jsnull_to_none(self.js_response.body)

    @property
    def js_object(self) -> "js.Response":
        return self.js_response

    @property
    def headers(self):
        return _js_headers_to_http_message(self.js_object.headers)

    """
    Instance methods defined below.

    Some methods are implemented by `FetchResponse`, these include `buffer`
    (replacing JavaScript's `arrayBuffer`), `bytes`, `json`, and `text`.

    There are also some additional methods implemented by `FetchResponse`.
    See https://pyodide.org/en/stable/usage/api/python-api/http.html#pyodide.http.FetchResponse
    for details.
    """

    async def formData(self) -> "FormData":  # TODO: Remove after certain compat date.
        return await self.form_data()

    async def form_data(self) -> "FormData":
        self._raise_if_failed()
        try:
            return FormData(await self.js_response.formData())
        except JsException as exc:
            raise _to_python_exception(exc) from exc

    def replace_body(self, body: Body) -> "Response":
        """
        Returns a new Response object with the same options (status, headers, etc) as
        the original but with an updated body.
        """
        b = body.js_object if isinstance(body, FormData) else body
        js_resp = js.Response.new(b, self.js_response)
        return Response(js_resp)

    async def blob(self) -> "Blob":
        self._raise_if_failed()
        return Blob(await self.js_object.blob())

    """
    Static methods defined below. The `error` static method is not implemented as
    it is not useful for the Workers use case.
    """

    @staticmethod
    def redirect(url: str, status: HTTPStatus | int = HTTPStatus.FOUND):
        code = status.value if isinstance(status, HTTPStatus) else status
        try:
            return js.Response.redirect(url, code)
        except JsException as exc:
            raise _to_python_exception(exc) from exc

    @staticmethod
    def from_json(
        data: str | dict[str, Any] | list[Any] | JsProxy,
        status: HTTPStatus | int = HTTPStatus.OK,
        status_text="",
        headers: Headers = None,
    ) -> "Response":
        options = Response._create_options(status, status_text, headers)
        js_resp = None
        try:
            if isinstance(data, JsProxy):
                js_resp = js.Response.json(data, **options)
            else:
                if "headers" not in options:
                    options["headers"] = _to_js_headers(
                        {"content-type": "application/json"}
                    )
                elif not options["headers"].has("content-type"):
                    options["headers"].set("content-type", "application/json")
                js_resp = js.Response.new(json.dumps(data), **options)
        except JsException as exc:
            raise _to_python_exception(exc) from exc

        return Response(js_resp)

    def json(self, *args: Never, **kwargs: Never):
        if isinstance(self, Response):
            return super().json()
        # For compatibility, allow static use of Response.json() to mean Response.from_json().
        data = self
        return Response.from_json(data, *args, **kwargs)


class Response(FetchResponse):
    """
    This class represents the response to an HTTP request, with a similar API to that of the web
    `Response` API: https://developer.mozilla.org/en-US/docs/Web/API/Response.
    """

    def __init__(
        self,
        body: Body = None,
        status: HTTPStatus | int | None = None,
        status_text="",
        headers: Headers = None,
        web_socket: "js.WebSocket | None" = None,
    ):
        """
        Represents the response to a request.

        Based on the JS API of the same name:
        https://developer.mozilla.org/en-US/docs/Web/API/Response/Response.
        """
        # Verify passed in types.
        js_type = _get_js_constructor_name(body)
        if js_type:
            if js_type not in RESPONSE_ACCEPTED_TYPES:
                raise TypeError(f"Unsupported type in Response: {js_type}")
        elif not isinstance(body, str | FormData | bytes) and body is not None:
            raise TypeError(f"Unsupported type in Response: {type(body).__name__}")

        # Handle constructing a Response from a JS Response.
        if _is_js_instance(body, "Response"):
            if status is not None or len(status_text) > 0 or headers is not None:
                raise ValueError(
                    "Expected no options when constructing Response from a js.Response"
                )
            super().__init__(body.url, body)
            return

        options = self._create_options(status, status_text, headers, web_socket)

        # To avoid unnecessary copies we use this context manager.
        with _get_js_body(body) as js_body:
            # Initialize via the FetchResponse super-class which gives us access to
            # methods that we would ordinarily have to redeclare.
            js_resp = js.Response.new(js_body, **options)
        super().__init__(js_resp.url, js_resp)

    def __repr__(self):
        body = [f"status={self.status}"]
        if self.js_object.statusText:
            body.append(f"status_text={self.status_text!r}")
        if "content-type" in self.headers:
            body.append(f"content_type={self.headers['content-type']!r}")
        if self.js_object.url:
            body.append(f"url={self.js_object.url!r}")
        if self.js_object.type != "default":
            body.append(f"type={self.js_object.type!r}")
        return f"Response({', '.join(body)})"

    @staticmethod
    def _create_options(
        status: HTTPStatus | int | None = HTTPStatus.OK,
        status_text="",
        headers: Headers = None,
        web_socket: "js.WebSocket | None" = None,
    ):
        options = {}
        if status:
            options["status"] = (
                status.value if isinstance(status, HTTPStatus) else status
            )
        if status_text:
            options["statusText"] = status_text
        if headers:
            options["headers"] = _to_js_headers(headers)
        if web_socket:
            options["webSocket"] = web_socket
        return options
