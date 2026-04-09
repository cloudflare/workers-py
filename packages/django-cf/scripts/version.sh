#!/usr/bin/env bash
set -euo pipefail

# Run changeset version to bump package.json and generate CHANGELOG.md
pnpm exec changeset version

# Sync the version from package.json into pyproject.toml
VERSION=$(jq -r .version package.json)
sed -i "s/^version = \".*\"/version = \"${VERSION}\"/" pyproject.toml
