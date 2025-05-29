
# workers-py

A set of libraries and tools for Python Workers.


## Pywrangler 

A CLI tool for managing vendored packages in a Python Workers project.

### Installation

TODO

### Usage

```bash
uvx pywrangler --help
uvx pywrangler sync
```


## Tests

```
$ uv cache clean
$ uv run pytest
$ uv run pytest tests/test_cli.py::test_sync_command_handles_missing_pyproject -v # Specific test
```