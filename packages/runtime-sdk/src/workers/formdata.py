from collections.abc import Generator, MutableMapping

import js

from .blob import Blob, File
from .utils import _is_js_instance

FormDataValue = "str | js.Blob | Blob"


def _py_value_to_js(item: FormDataValue) -> "str | js.Blob":
    if isinstance(item, Blob):
        return item.js_object
    else:
        return item


def _js_value_to_py(item: FormDataValue) -> "str | Blob | File":
    if hasattr(item, "constructor") and (item.constructor.name in ("Blob", "File")):
        if item.constructor.name == "File":
            return File(item, item.name)
        else:
            return Blob(item)
    else:
        return item


class FormData(MutableMapping[str, FormDataValue]):
    """
    This class represents a set of key/value pairs for forms.

    The API of this class follows that of https://pypi.org/project/multidict/ and
    https://developer.mozilla.org/en-US/docs/Web/API/FormData.
    """

    def __init__(
        self, form_data: "js.FormData | None | dict[str, FormDataValue]" = None
    ):
        if not form_data:
            self._js_form_data = js.FormData.new()
            return

        if isinstance(form_data, dict):
            self._js_form_data = js.FormData.new()
            for k, v in form_data.items():
                self._js_form_data.append(k, _py_value_to_js(v))
            return

        if _is_js_instance(form_data, "FormData"):
            self._js_form_data = form_data
            return

        raise TypeError("Expected form_data to be a dict or an instance of FormData")

    def __getitem__(self, key: str) -> FormDataValue:
        return _js_value_to_py(self._js_form_data.get(key))

    def __setitem__(self, key: str, value: FormDataValue):
        if isinstance(value, list):
            raise TypeError("Expected single item in arguments to FormData.__setitem__")
        self._js_form_data.set(key, _py_value_to_js(value))

    def append(self, key: str, value: FormDataValue, filename: str | None = None):
        self._js_form_data.append(key, _py_value_to_js(value), filename)

    def delete(self, key: str):
        self._js_form_data.delete(key)

    def __contains__(self, key: str) -> bool:
        return self._js_form_data.has(key)

    def values(self) -> Generator[FormDataValue, None, None]:
        for val in self._js_form_data.values():
            yield _js_value_to_py(val)

    def keys(self) -> Generator[str, None, None]:
        yield from self._js_form_data.keys()

    def __iter__(self):
        yield from self.keys()

    def items(self) -> Generator[tuple[str, FormDataValue], None, None]:
        for k, v in self._js_form_data.entries():
            yield (k, _js_value_to_py(v))

    def __delitem__(self, key: str):
        self.delete(key)

    def __len__(self):
        return len(self.keys())

    def get_all(self, key: str) -> list[FormDataValue]:
        return [_js_value_to_py(x) for x in self._js_form_data.getAll(key)]

    @property
    def js_object(self) -> "js.FormData":
        return self._js_form_data
