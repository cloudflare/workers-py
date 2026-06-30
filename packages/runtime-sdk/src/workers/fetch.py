from http import HTTPMethod
from typing import Any, Unpack

import js
from js import Object
from pyodide import __version__ as pyodide_version
from pyodide.ffi import JsException, to_js
from pyodide.http import pyfetch

from .request import Request
from .response import Response
from .types import FetchKwargs

if pyodide_version == "0.26.0a2":

    async def _pyfetch_patched(
        request: "str | js.Request", **kwargs: Any
    ) -> "Response":
        # This is copied from https://github.com/pyodide/pyodide/blob/d3f99e1d/src/py/pyodide/http.py
        custom_fetch = kwargs["fetcher"] if "fetcher" in kwargs else js.fetch
        kwargs["fetcher"] = None
        try:
            return Response(
                await custom_fetch(
                    request, to_js(kwargs, dict_converter=Object.fromEntries)
                ),
            )
        except JsException as e:
            raise OSError(e.message) from None
else:
    _pyfetch_patched = pyfetch


async def fetch(
    resource: "str | Request | js.Request",
    **other_options: Unpack[FetchKwargs],
) -> Response:
    if isinstance(resource, Request):
        resource = resource.js_object
    if "method" in other_options and isinstance(other_options["method"], HTTPMethod):
        other_options["method"] = other_options["method"].value

    resp = await _pyfetch_patched(resource, **other_options)
    return Response(resp.js_response)
