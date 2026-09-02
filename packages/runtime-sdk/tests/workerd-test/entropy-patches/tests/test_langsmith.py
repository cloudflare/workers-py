# ruff: noqa: F401
import langsmith._internal._constants

import sys

if sys.version_info <= (3, 13):
    # This is broken in Python 3.13
    # because it calls ssl.create_default_context() in the top-level which is not supported
    # in Python <= 3.13
    import langchain_openai.chat_models.base


def test_import():
    # make sure this file is collected by pytest
    pass
