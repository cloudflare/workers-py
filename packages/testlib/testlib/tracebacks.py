"""Ship exceptions raised inside the worker to the host with pickle.

The worker pickles the exception with tblib's pickling support, which carries
the traceback, the ``__cause__``/``__context__`` chain and ``__notes__``. Hooks
on both ends keep that from failing on things pickle cannot handle.

The host unpickles and raises the result, so pytest renders the failure exactly
as if the test had run here.
"""

from __future__ import annotations

import base64
import functools
import pickle
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from types import TracebackType
from typing import NotRequired, TypedDict

from tblib import pickling_support


class WorkerException(TypedDict):
    """Pickled exception from the worker, base64-encoded."""

    pickle: str
    when: NotRequired[str]


def _safe_repr(value: object) -> str:
    try:
        return repr(value)
    except Exception:
        return object.__repr__(value)


# --- worker side: pickling ---------------------------------------------------


class _Pickler(pickle.Pickler):
    def reducer_override(self, obj):
        if isinstance(obj, BaseException):
            func, args, *state = pickling_support.pickle_exception(obj)
            return (_unpickle_exception, (func, args, str(obj)), *state)
        if isinstance(obj, TracebackType):
            return pickling_support.pickle_traceback(obj)
        if isinstance(obj, type):
            try:
                pickle.dumps(obj)
            except Exception:
                return (_exception_class, (obj.__qualname__, obj.__module__))
            return NotImplemented
        if type(obj).__module__ in ["builtins", "tblib"]:
            return NotImplemented
        return (str, (_safe_repr(obj),))


def _link(entries: Sequence[TracebackType]) -> TracebackType | None:
    """Chain non-contiguous traceback entries into one traceback."""
    tb = None
    for entry in reversed(entries):
        tb = TracebackType(tb, entry.tb_frame, entry.tb_lasti, entry.tb_lineno)
    return tb


def dump_exception(exc: BaseException, entries: Sequence[TracebackType]) -> str:
    """Pickle ``exc`` for the host; ``entries`` replaces its traceback if given."""
    exc = exc.with_traceback(_link(entries))
    buffer = BytesIO()
    _Pickler(buffer, protocol=pickle.HIGHEST_PROTOCOL).dump(exc)
    return base64.b64encode(buffer.getvalue()).decode()


# --- host side: unpickling ---------------------------------------------------


def _exception_class(qualname: str, module: str) -> type[Exception]:
    """Dummy exception class. Pickle can't reference @functools.cache wrappers by name."""
    return _make_exception_class(qualname, module)


@functools.cache
def _make_exception_class(qualname: str, module: str) -> type[Exception]:
    return type(
        qualname.rsplit(".", 1)[-1],
        (Exception,),
        {"__module__": module, "__qualname__": qualname, "_testlib_stand_in": True},
    )


def _unpickle_exception(func, args, message):
    exc = func(*args)
    if getattr(type(exc), "_testlib_stand_in", False):
        # A stand-in lacks the original __str__, so make str(exc) the message
        # the worker printed
        exc.args = (message,)
    return exc


@functools.cache
def _locate_source(filename: str, roots: tuple[Path, ...]) -> str:
    """Map a worker-side path onto the host file it was copied from."""
    if not filename.startswith("/session/metadata/"):
        return filename
    parts = Path(filename).parts[3:]
    if parts[0] == "python_modules":
        parts = parts[1:]
    for root in roots:
        candidate = root.joinpath(*parts)
        if candidate.is_file():
            return str(candidate)
    return filename


class _Unpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        try:
            return super().find_class(module, name)
        except (ImportError, AttributeError):
            # The only globals the worker references that we may lack are
            # exception classes; everything else was reduced to builtins.
            return _exception_class(name, module)


def load_exception(
    payload: WorkerException, source_roots: Sequence[Path] = ()
) -> BaseException:
    """Recreate an exception pickled by ``dump_exception``."""
    roots = tuple(source_roots)
    data = base64.b64decode(payload["pickle"])
    with pickling_support.map_filenames(lambda name: _locate_source(name, roots)):
        return _Unpickler(BytesIO(data)).load()
