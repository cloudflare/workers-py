# ruff: noqa: F401
import sys

if sys.version_info >= (3, 14):
    import mcp


def test_import():
    # make sure this file is collected by pytest
    pass
