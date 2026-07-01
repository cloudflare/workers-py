from collections.abc import Iterable
from contextlib import ExitStack, contextmanager
from enum import StrEnum

import js
from pyodide.ffi import create_proxy, to_js

from .utils import _is_iterable, _manage_pyproxies, _supports_buffer_protocol

BlobValue = (
    "str | bytes | js.ArrayBuffer | js.TypedArray | js.DataView | js.Blob | Blob | File"
)


class BlobEnding(StrEnum):
    TRANSPARENT = "transparent"
    NATIVE = "native"


class Blob:
    def __init__(
        self,
        blob_parts: "Iterable[BlobValue] | BlobValue",
        content_type: str | None = None,
        endings: BlobEnding | str | None = None,
    ):
        if endings:
            endings = str(endings)

        is_single_item = not _is_iterable(blob_parts)
        if is_single_item:
            # Inherit the content_type if we have a single item. If a File is passed
            # in then its metadata is lost.
            if not content_type and isinstance(blob_parts, Blob):
                content_type = blob_parts.content_type
            if hasattr(blob_parts, "constructor") and (
                blob_parts.constructor.name in ("Blob", "File")
            ):
                if not content_type:
                    content_type = blob_parts.type

            # Otherwise create a new Blob below.
            blob_parts = [blob_parts]

        with ExitStack() as stack:
            args = [stack.enter_context(_make_blob_entry(e)) for e in blob_parts]
            with _manage_pyproxies() as pyproxies:
                self._js_blob = js.Blob.new(
                    to_js(args, pyproxies=pyproxies),
                    type=content_type,
                    endings=endings,
                )

    @property
    def size(self) -> int:
        return self._js_blob.size

    @property
    def content_type(self) -> str:
        return self._js_blob.type

    @property
    def js_object(self) -> "js.Blob":
        return self._js_blob

    async def text(self) -> str:
        return await self.js_object.text()

    async def bytes(self) -> bytes:
        return (await self.js_object.arrayBuffer()).to_bytes()

    def slice(
        self,
        start: int | None = None,
        end: int | None = None,
        content_type: str | None = None,
    ):
        js_sliced_blob = self.js_object.slice(start, end, content_type)
        return Blob([js_sliced_blob])


class File(Blob):
    def __init__(
        self,
        blob_parts: "Iterable[BlobValue] | BlobValue",
        filename: str,
        content_type: str | None = None,
        endings: BlobEnding | str | None = None,
        last_modified: int | None = None,
    ):
        if endings:
            endings = str(endings)

        is_single_item = not _is_iterable(blob_parts)
        if is_single_item:
            # Inherit the content_type and lastModified if we have a
            # single item.
            if not content_type and isinstance(blob_parts, Blob):
                content_type = blob_parts.content_type
            if not last_modified and isinstance(blob_parts, File):
                last_modified = blob_parts.last_modified
            if hasattr(blob_parts, "constructor") and (
                blob_parts.constructor.name in ("Blob", "File")
            ):
                if not content_type:
                    content_type = blob_parts.type
                if blob_parts.constructor.name == "File":
                    if not last_modified:
                        last_modified = blob_parts.lastModified

            # Otherwise create a new File below.
            blob_parts = [blob_parts]

        with ExitStack() as stack:
            args = [stack.enter_context(_make_blob_entry(e)) for e in blob_parts]
            with _manage_pyproxies() as pyproxies:
                self._js_blob = js.File.new(
                    to_js(args, pyproxies=pyproxies),
                    filename,
                    type=content_type,
                    endings=endings,
                    lastModified=last_modified,
                )

    @property
    def name(self) -> str:
        return self._js_blob.name

    @property
    def last_modified(self) -> int:
        return self._js_blob.lastModified


@contextmanager
def _make_blob_entry(e):
    if isinstance(e, str):
        yield e
        return
    if isinstance(e, Blob):
        yield e._js_blob
        return
    if hasattr(e, "constructor") and (e.constructor.name in ("Blob", "File")):
        yield e
        return
    if _supports_buffer_protocol(e):
        px = create_proxy(e)
        buf = px.getBuffer()
        try:
            yield buf.data
            return
        finally:
            buf.release()
            px.destroy()
    raise TypeError(f"Don't know how to handle {type(e)} for Blob()")
