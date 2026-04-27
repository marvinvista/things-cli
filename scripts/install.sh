#!/usr/bin/env sh
set -eu

python3 -m venv .venv
.venv/bin/python -m pip install setuptools wheel
.venv/bin/python -m pip install --no-build-isolation -e .

echo "Installed things-cli. Run: .venv/bin/things diagnose"
