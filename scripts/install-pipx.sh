#!/usr/bin/env sh
set -eu

if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx is required. Install it with: brew install pipx" >&2
  exit 1
fi

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
pipx install --force "$ROOT_DIR"

echo "Installed things-cli with pipx. Run: things diagnose"
