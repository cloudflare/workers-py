# ruff: noqa: F401
# jsonschema -> referencing -> rpds (a Rust extension) seeds a HashMap at import.
import jsonschema
import rpds


def test_import():
    # make sure this file is collected by pytest
    pass
