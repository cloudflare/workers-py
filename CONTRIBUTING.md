# Contributing to workers-py

Thank you for your interest in contributing to workers-py! This document provides guidelines and information to help you contribute effectively.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Release Process](#release-process)
- [Submitting Changes](#submitting-changes)

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/workers-py.git
   cd workers-py
   ```
3. Set up the development environment (see [Development Setup](#development-setup))

## Development Setup

Follow the [Development section](https://github.com/cloudflare/workers-py#development) of the README for setting up your development environment.

### Development Dependencies

The project includes these development tools:
- **pytest**: Testing framework
- **ruff**: Fast Python linter
- **mypy**: Static type checking

## Making Changes

1. Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b your-username/your-change-name
   ```

2. Run our code formatter via `uvx ruff format` and linter via `uvx ruff fix .`

3. Add or update tests as needed

4. Run the test suite: `uv clean cache && uv run pytest`

## Commit Message Guidelines

This project uses automated semantic versioning via `python-semantic-release` which relies on
tags in the commit message to determine whether a release should be made.

### Commit Format

The format parsed by python-semantic-release is https://www.conventionalcommits.org/en/v1.0.0/#summary.
It looks something like this:

```
<tag>(<optional scope>): <subject>

<body>

<footer>
```

### Commit Tags

Including "BREAKING CHANGE" in the commit message (either in the body or footer) will trigger a release.

The following tags will trigger a release:

- **feat**: A new feature (triggers minor version bump)
- **fix**: A bug fix (triggers patch version bump)

The following tags will not trigger a release:

- **docs**: Documentation changes
- **style**: Code style changes (formatting, etc.)
- **refactor**: Code refactoring without feature changes
- **test**: Adding or updating tests
- **chore**: Maintenance tasks, dependency updates
- **ci**: CI/CD configuration changes

## Release Process

This project uses **python-semantic-release** for automated versioning and releases. Here's how it works:

### Automated Releases

1. **Version Calculation**: Based on conventional commit messages since the last release:
   - `fix:` commits → patch version bump (1.0.0 → 1.0.1)
   - `feat:` commits → minor version bump (1.0.0 → 1.1.0)
   - `BREAKING CHANGE:` → major version bump (1.0.0 → 2.0.0)

2. **Release Trigger**: Releases are created automatically when changes are pushed to the `main` branch

3. **Release Artifacts**:
   - Git tag (format: `v{version}`)
   - Updated `pyproject.toml` version
   - Changelog generation
   - PyPI package publication (via GitHub Actions)

## Submitting Changes

1. **Push your branch** to your fork:
   ```bash
   git push origin your-username/your-change-name
   ```

2. **Create a Pull Request** on GitHub with:
   - Clear title following conventional commit format
   - Description of changes made
   - Any breaking changes clearly documented
   - Explanation of how you tested your changes under a "Test Plan" section

3. **Review Process**:
   - All CI checks must pass
   - Code review from maintainers
   - Tests must pass
   - Documentation updates if needed

## Questions or Issues?

- Open an issue on GitHub for bugs or feature requests
- Check existing issues before creating new ones
- For questions, use GitHub Discussions or open an issue

Thank you for contributing to workers-py! 🚀
