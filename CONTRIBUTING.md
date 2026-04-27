# Contributing

Thanks for considering a contribution to `things-cli`.

This project is intentionally conservative because it controls a real Things library through macOS Automation. Small, well-tested changes are much easier to review than broad rewrites.

## Setup

```sh
git clone https://github.com/marvinvista/things-cli.git
cd things-cli
make install
make test
```

## Pull Request Checklist

- Keep behavior source-agnostic. Do not assume a user's project, tag, list, or todo names.
- Keep mutations dry-run-first unless a user explicitly passes `--yes`.
- Do not add direct SQLite writes.
- Update docs when command behavior or JSON output changes.
- Add or update tests for new command behavior.
- Run `make test` before opening a pull request.

## Live Things Testing

The normal test suite does not mutate Things. Live tests are opt-in:

```sh
THINGS_LIVE_TESTS=1 .venv/bin/python -m unittest discover -s tests
```

Only run live tests on a Things library where test-created items are acceptable. Live tests use clearly named test items and clean up by completing or canceling them.

## Style

- Prefer simple standard-library Python.
- Keep CLI output stable and machine-readable when `--json` is used.
- Make permission failures explicit. Do not interpret Apple Events failures as empty Things data.
- Keep public docs focused on what the CLI does, how to install it, and how to use it.

## License

By contributing, you agree that your contributions are licensed under the MIT license.
