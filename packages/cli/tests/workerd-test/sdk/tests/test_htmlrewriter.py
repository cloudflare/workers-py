import asyncio

import pytest
from workers import HTMLRewriter, Response

from pyodide.ffi import JsException
from pyodide.http import AbortError


@pytest.mark.asyncio
async def test_sync_element_handler():
    html = "<html><body><div>Hello</div></body></html>"
    response = Response(html, headers={"content-type": "text/html"})

    class Handler:
        def __init__(self):
            self.called = False

        def element(self, el):
            self.called = True
            el.setAttribute("data-modified", "true")

    handler = Handler()
    rewriter = HTMLRewriter()
    rewriter.on("div", handler)
    result = rewriter.transform(response)

    text = await result.text()
    assert handler.called, "Handler should have been called"
    assert 'data-modified="true"' in text, f"Expected modified attribute in: {text}"


@pytest.mark.asyncio
async def test_async_element_handler():
    html = "<html><body><div>Hello</div></body></html>"
    response = Response(html, headers={"content-type": "text/html"})

    class AsyncHandler:
        def __init__(self):
            self.called = False

        async def element(self, el):
            await asyncio.sleep(0.01)
            self.called = True
            el.setAttribute("data-async", "true")

    handler = AsyncHandler()
    rewriter = HTMLRewriter()
    rewriter.on("div", handler)
    result = rewriter.transform(response)

    text = await result.text()
    assert handler.called, "Async handler should have been called"
    assert 'data-async="true"' in text, f"Expected async attribute in: {text}"


@pytest.mark.asyncio
async def test_document_handler():
    html = "<!DOCTYPE html><html><body>Test</body></html>"
    response = Response(html, headers={"content-type": "text/html"})

    class DocHandler:
        def __init__(self):
            self.saw_doctype = False
            self.saw_end = False

        def doctype(self, doctype):
            self.saw_doctype = True

        def end(self, end):
            self.saw_end = True
            end.append("<!-- end -->", html=True)

    handler = DocHandler()
    rewriter = HTMLRewriter()
    rewriter.on_document(handler)
    result = rewriter.transform(response)

    text = await result.text()
    assert handler.saw_doctype, "Should have seen doctype"
    assert handler.saw_end, "Should have seen end"
    assert "<!-- end -->" in text, f"Expected appended content in: {text}"


@pytest.mark.asyncio
async def test_text_handler():
    html = "<html><body><p>Hello World</p></body></html>"
    response = Response(html, headers={"content-type": "text/html"})

    class TextHandler:
        def __init__(self):
            self.texts = []

        def text(self, text):
            if text.text:
                self.texts.append(text.text)

    handler = TextHandler()
    rewriter = HTMLRewriter()
    rewriter.on("p", handler)
    result = rewriter.transform(response)

    text = await result.text()
    assert "Hello World" in "".join(handler.texts), (
        f"Expected text chunks to contain 'Hello World', got: {handler.texts}"
    )
    assert "Hello World" in text


@pytest.mark.asyncio
async def test_comment_handler():
    html = "<html><body><!-- a comment --><div>Test</div></body></html>"
    response = Response(html, headers={"content-type": "text/html"})

    class CommentHandler:
        def __init__(self):
            self.seen_comments = []

        def comments(self, comment):
            self.seen_comments.append(comment.text)

    handler = CommentHandler()
    rewriter = HTMLRewriter()
    rewriter.on("body", handler)
    result = rewriter.transform(response)

    await result.text()
    assert " a comment " in handler.seen_comments, (
        f"Expected comment text, got: {handler.seen_comments}"
    )


@pytest.mark.asyncio
async def test_combined_element_and_document_handlers():
    html = "<!DOCTYPE html><html><body><div>Test</div></body></html>"
    response = Response(html, headers={"content-type": "text/html"})

    class ElemHandler:
        def __init__(self):
            self.called = False

        def element(self, el):
            self.called = True
            el.setAttribute("data-elem", "true")

    class DocHandler:
        def __init__(self):
            self.saw_end = False

        def end(self, end):
            self.saw_end = True
            end.append("<!-- footer -->", html=True)

    elem_handler = ElemHandler()
    doc_handler = DocHandler()
    rewriter = HTMLRewriter()
    rewriter.on("div", elem_handler)
    rewriter.on_document(doc_handler)
    result = rewriter.transform(response)

    text = await result.text()
    assert elem_handler.called, "Element handler should have been called"
    assert doc_handler.saw_end, "Document handler should have seen end"
    assert 'data-elem="true"' in text
    assert "<!-- footer -->" in text


@pytest.mark.asyncio
async def test_no_matching_selector():
    html = "<html><body><div>Test</div></body></html>"
    response = Response(html, headers={"content-type": "text/html"})

    class Handler:
        def __init__(self):
            self.called = False

        def element(self, el):
            self.called = True

    handler = Handler()
    rewriter = HTMLRewriter()
    rewriter.on("nonexistent", handler)
    result = rewriter.transform(response)

    text = await result.text()
    assert not handler.called, "Handler should not have been called"
    assert "Test" in text, "Content should pass through unchanged"


@pytest.mark.asyncio
async def test_chained_api():
    html = "<html><body><div>D</div><span>S</span></body></html>"
    response = Response(html, headers={"content-type": "text/html"})

    class H1:
        def element(self, el):
            el.setAttribute("data-h1", "true")

    class H2:
        def element(self, el):
            el.setAttribute("data-h2", "true")

    result = HTMLRewriter().on("div", H1()).on("span", H2()).transform(response)
    text = await result.text()
    assert 'data-h1="true"' in text
    assert 'data-h2="true"' in text


@pytest.mark.asyncio
async def test_multiple_handlers():
    html = "<html><body><div>D</div><span>S</span></body></html>"
    response = Response(html, headers={"content-type": "text/html"})

    class Handler1:
        def element(self, el):
            el.setAttribute("data-h1", "true")

    class Handler2:
        def element(self, el):
            el.setAttribute("data-h2", "true")

    rewriter = HTMLRewriter()
    rewriter.on("div", Handler1())
    rewriter.on("span", Handler2())

    result = rewriter.transform(response)
    text = await result.text()

    assert 'data-h1="true"' in text, f"Handler1 didn't work: {text}"
    assert 'data-h2="true"' in text, f"Handler2 didn't work: {text}"


@pytest.mark.asyncio
async def test_rewriter_reuse():
    html = "<div>Test</div>"

    class Counter:
        def __init__(self):
            self.count = 0

        def element(self, el):
            self.count += 1
            el.setAttribute("data-count", str(self.count))

    counter = Counter()
    rewriter = HTMLRewriter()
    rewriter.on("div", counter)

    result1 = rewriter.transform(Response(html, headers={"content-type": "text/html"}))
    text1 = await result1.text()
    assert 'data-count="1"' in text1, f"First transform failed: {text1}"
    assert counter.count == 1

    result2 = rewriter.transform(Response(html, headers={"content-type": "text/html"}))
    text2 = await result2.text()
    assert 'data-count="2"' in text2, f"Second transform failed: {text2}"
    assert counter.count == 2


@pytest.mark.asyncio
async def test_stream_cancellation():
    html = "<html><body><div>Test</div></body></html>"
    response = Response(html, headers={"content-type": "text/html"})

    class Handler:
        def __init__(self):
            self.called = False

        def element(self, el):
            self.called = True

    handler = Handler()
    rewriter = HTMLRewriter()
    rewriter.on("div", handler)

    result = rewriter.transform(response)

    body = result.js_object.body
    reader = body.getReader()
    await reader.cancel()

    # After cancellation, read() returns done instead of throwing
    data = await reader.read()
    assert data.done


def is_proxy_destroyed(proxy) -> bool:
    try:
        return not getattr(proxy, "_attr", True)
    except JsException as e:
        return "Object has already been destroyed" in str(e)


@pytest.mark.asyncio
async def test_proxy_cleanup_on_completion():
    import pyodide_js

    pyodide_js.setDebug(True)
    html = "<html><body><div>Test</div></body></html>"
    response = Response(html, headers={"content-type": "text/html"})

    class Handler:
        def element(self, el):
            el.setAttribute("data-test", "true")

    rewriter = HTMLRewriter()
    rewriter.on("div", Handler())
    result = rewriter.transform(response)

    proxies = rewriter._last_handler_proxies
    assert proxies is not None
    # 1 method proxy (element) + 2 stream proxies (start + cancel)
    assert len(proxies) == 3

    for proxy in proxies:
        assert not is_proxy_destroyed(proxy), "Proxy should be alive before consumption"

    text = await result.text()
    assert 'data-test="true"' in text

    # Proxy destruction is deferred via waitUntil to avoid destroying them
    # while JS HTMLRewriter is still finalizing. Yield to let it complete.
    await asyncio.sleep(0)

    for proxy in proxies:
        assert is_proxy_destroyed(proxy), "Proxy should be destroyed after consumption"


@pytest.mark.asyncio
async def test_exception_handling():
    html = "<html><body><div>Test</div></body></html>"
    response = Response(html, headers={"content-type": "text/html"})

    class Handler:
        def element(self, el):
            el.setAttribute("data-test", "true")
            raise RuntimeError("Test exception")

    rewriter = HTMLRewriter()
    rewriter.on("div", Handler())
    result = rewriter.transform(response)

    try:
        await result.text()
    except Exception as e:
        # Note: workerd will show the `info: uncaught exception; source = Uncaught; stack = PythonError`
        # in the log message, which is expected
        assert "PythonError" in str(e)
