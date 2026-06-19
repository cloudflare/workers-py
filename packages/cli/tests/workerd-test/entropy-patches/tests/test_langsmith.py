import langchain_openai.chat_models.base
from langsmith import traceable


def test_langsmith_import():
    assert traceable is not None


def test_langchain_openai_import():
    assert langchain_openai.chat_models.base is not None
