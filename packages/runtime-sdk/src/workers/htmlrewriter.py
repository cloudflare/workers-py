import js
from js import Object
from pyodide.ffi import JsProxy, create_proxy, to_js

from ._workers import Response, _jsnull_to_none

_ELEMENT_HANDLER_METHODS = ("element", "comments", "text")
_DOCUMENT_HANDLER_METHODS = ("doctype", "comments", "text", "end")


def _create_js_handler(
    handler: object, method_names: tuple[str, ...], handler_proxies: list[JsProxy]
) -> JsProxy:
    """
    Instead of creating a single proxy for the entire handler object,
    create individual proxies for each method and attach them to a plain JS object.

    Proxying the handler object directly causes a problem as
    the original HTMLRewriter stores the reference to each method,
    and handler objects may be destroyed while JS still holds references to them.
    """
    methods: dict[str, JsProxy] = {}
    for name in method_names:
        method = getattr(handler, name, None)
        if method is not None:
            proxy = create_proxy(method)
            handler_proxies.append(proxy)
            methods[name] = proxy
    return to_js(methods, dict_converter=Object.fromEntries)


class HTMLRewriter:
    def __init__(self):
        self._handlers: list[tuple] = []
        # Testing purpose only, stores the proxies created for handlers
        self._last_handler_proxies: list[JsProxy] | None = None

    def on(self, selector: str, handlers: object) -> "HTMLRewriter":
        self._handlers.append(("element", selector, handlers))
        return self

    def on_document(self, handlers: object) -> "HTMLRewriter":
        self._handlers.append(("document", handlers))
        return self

    def transform(self, response: Response) -> "Response":
        js_rewriter = js.HTMLRewriter.new()
        handler_proxies: list[JsProxy] = []

        def _destroy_proxies():
            for proxy in handler_proxies:
                proxy.destroy()

        for handler_info in self._handlers:
            if handler_info[0] == "element":
                _, selector, handler = handler_info
                js_handler = _create_js_handler(
                    handler, _ELEMENT_HANDLER_METHODS, handler_proxies
                )
                js_rewriter.on(selector, js_handler)
            else:
                _, handler = handler_info
                js_handler = _create_js_handler(
                    handler, _DOCUMENT_HANDLER_METHODS, handler_proxies
                )
                js_rewriter.onDocument(js_handler)

        self._last_handler_proxies = handler_proxies
        transformed = js_rewriter.transform(response.js_object)

        if _jsnull_to_none(transformed.body) is None:
            _destroy_proxies()
            return Response(transformed)

        reader = transformed.body.getReader()

        async def start(controller):
            completed = False
            try:
                while True:
                    result = await reader.read()
                    if result.done:
                        controller.close()
                        completed = True
                        break
                    controller.enqueue(result.value)
            except Exception as e:
                controller.error(e)
            finally:
                if completed:
                    # Happy path: HTMLRewriter finished processing,
                    # safe to destroy all proxies
                    _destroy_proxies()
                # TODO(later):
                # On cancel/exception the HTMLRewriter may still hold
                # internal references to handler method proxies, so we
                # intentionally leak them to avoid runtime errors.
                # We should investigate if there is a way to properly
                # clean up these proxies.

        async def cancel(reason):
            if reader:
                await reader.cancel(reason)

        start_proxy = create_proxy(start)
        cancel_proxy = create_proxy(cancel)
        handler_proxies.append(start_proxy)
        handler_proxies.append(cancel_proxy)

        wrapped_body = js.ReadableStream.new(
            start=start_proxy,
            cancel=cancel_proxy,
        )

        return Response(
            js.Response.new(
                wrapped_body,
                status=transformed.status,
                statusText=transformed.statusText,
                headers=transformed.headers,
            )
        )
