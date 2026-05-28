# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) or Opencode (opencode.ai) when working with code in this repository.

Subdirectory `AGENTS.md` files provide package-specific context (key classes, where-to-look tables, local conventions and anti-patterns).

## Instructions for AI Code Assistants

- Suggest updates to AGENTS.md when you find new high-level information

## Project overview

This repository (`workers-py`) contains two Python packages that are used for Cloudflare Python Workers.

- `packages/cli` contains the command-line interface for managing Python Workers, including installing packages, running workers locally, and uploading workers to Cloudflare.
- `packages/runtime-sdk` contains the runtime SDK for Python Workers, which provides a base class for Python Workers and utilities for working with Cloudflare's runtime.

### `packages/cli`

For cli conventions, see `packages/cli/AGENTS.md`.

### `packages/runtime-sdk`

For runtime-sdk conventions, see `packages/runtime-sdk/AGENTS.md`.

## Build System & Commands

This project uses the following tools to manage the build process:

- `uv` for package installation and running of tools. Never use system Python or pip directly.
- `pytest` for the implementation of tests, use `uv run pytest` to run tests.
- `pre-commit` for linting and formatting, use `uv run pre-commit run --all-files` to run pre-commit.

Since this repository contains two packages, `cli` and `runtime-sdk`, the build system and commands are managed separately for each package.
Every command should be run inside the respective package directory, not at the root of the repository.
