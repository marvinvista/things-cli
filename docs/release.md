# Release Checklist

Use this before tagging or publishing a public release.

## Local Checks

```sh
make clean
make test
python3 -m venv /tmp/things-cli-release-smoke
/tmp/things-cli-release-smoke/bin/python -m pip install setuptools wheel
/tmp/things-cli-release-smoke/bin/python -m pip install --no-build-isolation .
/tmp/things-cli-release-smoke/bin/things --help
```

## Live Checks

Run only on a Things library where test-created items are acceptable:

```sh
THINGS_LIVE_TESTS=1 .venv/bin/python -m unittest discover -s tests
```

## Public Surface

```sh
python3 scripts/validate_public_surface.py
```

Review `README.md`, `docs/install.md`, `SECURITY.md`, and `CHANGELOG.md` for the target version.

## GitHub Release

1. Update `CHANGELOG.md`.
2. Tag the release, for example `v0.1.0`.
3. Create a GitHub release with install instructions.
4. Verify install from GitHub:

```sh
pipx install --force git+https://github.com/marvinvista/things-cli.git
things diagnose
```

## Future Distribution

The project is currently installable with `pipx` from GitHub. PyPI and Homebrew distribution should be added only after the GitHub install path is stable for external users.
