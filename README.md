
# workers-py

A set of libraries and tools for Python Workers.


## Pywrangler 

A CLI tool for managing vendored packages in a Python Workers project.

### Installation

You may be able to install the tool globally by running:

```
uv pip install --system workers-py
```

Alternatively, you can add `workers-py` to your pyproject.toml:

```
[project]
dependencies = [
    "workers-py",
    ...
]
```

### Usage

```bash
uvx pywrangler --help
uvx pywrangler sync
```

### Development

To run the CLI tool while developing it, use:

```bash
uv run --project $REPO_ROOT $REPO_ROOT/src/pywrangler --help
```

To install it globally, you may also be able to run:

```
uv pip install --system -e .
```

## Tests

```
$ uv cache clean
$ uv run pytest
$ uv run pytest tests/test_cli.py::test_sync_command_handles_missing_pyproject -v # Specific test
```