# workers-py

A set of libraries and tools for Python Workers.


## Pywrangler

A CLI tool for managing vendored packages in a Python Workers project.

### Installation

On Linux, you may be able to install the tool globally by running:

```
uv tool install workers-py
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
# install packages
uv run pywrangler sync
# run dev server
uv run pywrangler dev
# deploy
uv run pywrangler deploy
```

### Advanced Usage

#### Using local packages

By default, pywrangler only allow installing packages from wheels, and not from source distributions.

This is because Python workers needs cross-compiled wheels to
run on the Worker runtime, while building from source distributions will output native wheels that are not compatible with the Worker runtime.

However, when you are testing your local package that does not include
any native extensions, you can use the `--allow-local` flag to allow installing
it from source distribution.

```
uv run pywrangler sync --allow-local
```

#### Skip native installation

pywrangler installs packages twice, once for the native environment and once for
the Worker runtime environment.

This has two purposes:
1. To give a type information properly for the IDEs which is
required for type checking and autocompletion.
2. Make sure packages actually exist and are installable in the native environment.

However, this has drawbacks:

1. It takes more time to install packages.
2. It may fail if the package is built only for the WASM environment / Worker runtime.

In such cases, you can pass the `--skip-native` flag to skip the native installation, and only install the package for the Worker runtime.

```
uv run pywrangler sync --skip-native-installation
```

The skipped state is remembered by later `sync`, `dev`, and `deploy` commands
until project dependencies or the pywrangler version changes. Run
`pywrangler sync --force` to install native packages explicitly.

### Development

To run the CLI tool while developing it, install it globally:

```
uv tool install -e .
```

Then run it via `pywrangler`.

Alternatively, you can add `workers-py` to your pyproject.toml:

```
[dependency-groups]
dev = ["workers-py"]

[tool.uv.sources]
workers-py = { path = "../workers-py/packages/cli" }
workers-runtime-sdk = { path = "../workers-py/packages/runtime-sdk" }
```

Then run via `uv run pywrangler`.

#### Lint

```
uv run ruff check --fix
uv run ruff format
```

#### Tests

```
$ uv cache clean
$ uv run pytest
$ uv run pytest tests/test_cli.py::test_sync_command_handles_missing_pyproject -v # Specific test
```
