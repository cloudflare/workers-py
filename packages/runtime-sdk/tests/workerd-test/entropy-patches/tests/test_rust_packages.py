# ruff: noqa: F401

import sys

if sys.version_info < (3, 14):
    # FIXME : starting from Python 3.14, package maintainers
    # started to publish pyemscripten wheels, which broke rust entropy.
    # Currently, we patch "once" for all rust packages, assuming that
    # all the packages shares the hash seed and it is initialized only once.
    # however, that is not true when the package is built separately (not from pyodide distribution),
    # with a different version of rust toolchain.
    import cryptography.exceptions
    import jiter
    import tiktoken._tiktoken


def test_import():
    # make sure this file is collected by pytest
    pass
