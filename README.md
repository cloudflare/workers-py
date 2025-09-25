# workers-py

A set of libraries and tools for Python Workers.


## Pywrangler

A CLI tool for managing vendored packages in a Python Workers project.

### Installation

On Linux, you may be able to install the tool globally by running:

```
uv pip install --system workers-py
```

Alternatively, you can add `workers-py` to your pyproject.toml:

```
[dependency-groups]
dev = ["workers-py"]
```

Then run via `uv run pywrangler`.

### Usage

```bash
uv run pywrangler --help
uv run pywrangler sync
```

### Development

To run the CLI tool while developing it, use:

```bash
export REPO_ROOT=/path/to/repo
uv run --project $REPO_ROOT $REPO_ROOT/src/pywrangler --help
```

On Linux, to install it globally, you may also be able to run:

```
uv pip install --system -e .
```

Alternatively, you can add `workers-py` to your pyproject.toml:

```
[dependency-groups]
dev = ["workers-py"]

[tool.uv.sources]
workers-py = { path = "../workers-py" }
```

Then run via `uv run pywrangler`.

## Tests

```
$ uv cache clean
$ uv run pytest
$ uv run pytest tests/test_cli.py::test_sync_command_handles_missing_pyproject -v # Specific test
```
