import pydantic
import pydantic_core
from pydantic import BaseModel


def test_pydantic_core_validate_core_schema():
    schema = pydantic_core.core_schema.str_schema()
    validator = pydantic_core.SchemaValidator(schema)
    assert validator.validate_python("hello") == "hello"


def test_pydantic_model_creation():
    class User(BaseModel):
        name: str
        age: int

    user = User(name="Alice", age=30)
    assert user.name == "Alice"
    assert user.age == 30


def test_pydantic_model_validation_error():
    class Item(BaseModel):
        price: float
        quantity: int

    try:
        Item(price="not a number", quantity="bad")
        raise AssertionError("Expected ValidationError")
    except pydantic.ValidationError:
        pass


def test_pydantic_model_serialization():
    class Config(BaseModel):
        host: str
        port: int
        debug: bool = False

    config = Config(host="localhost", port=8080)
    data = config.model_dump()
    assert data == {"host": "localhost", "port": 8080, "debug": False}

    json_str = config.model_dump_json()
    assert "localhost" in json_str
    assert "8080" in json_str
