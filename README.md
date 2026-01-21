# workers-py Monorepo

A monorepo containing Python libraries and tools for Cloudflare Workers.

## Packages

| Package | Description |
|---------|-------------|
| [workers-py](./packages/workers-py/) | A set of libraries and tools for Python Workers |
| [workers-runtime-sdk](./packages/workers-runtime-sdk/) | Python SDK for Cloudflare Workers |

## Development

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) for package management

### Working with packages

Each package is self-contained with its own `pyproject.toml`. To work on a specific package:

```bash
cd packages/<package-name>
uv sync
uv run pytest
```

### Releasing

This project uses [python-semantic-release](https://python-semantic-release.readthedocs.io/) with the monorepo configuration. Each package is released independently.

To release a specific package:

```bash
cd packages/<package-name>
semantic-release version
```

### Commit Conventions

This project uses [Conventional Commits](https://www.conventionalcommits.org/) with package-scoped commits for the monorepo. For package-specific changes, use the scope prefix:

- `feat(workers-py-): add new feature` - Feature for workers-py
- `fix(workers-runtime-sdk-): fix bug` - Bug fix for workers-runtime-sdk

Tags:
- `feat`: New feature (triggers minor version bump)
- `fix`: Bug fix (triggers patch version bump)
- `docs`, `style`, `refactor`, `test`, `chore`, `ci`: Non-release commits

## License

MIT
