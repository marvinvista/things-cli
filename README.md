# things-cli - Things.app from your terminal

[![CI](https://github.com/marvinvista/things-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/marvinvista/things-cli/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)
[![macOS](https://img.shields.io/badge/macOS-Things%203-lightgrey.svg)](https://culturedcode.com/things/)

`things-cli` is a macOS command-line interface for reading, reviewing, exporting, and updating [Things](https://culturedcode.com/things/) todos.

It is built for humans and local AI agents that need a reliable shell surface around Things: JSON output, dry-run mutations, audit logs, undo, snapshot diffs, and explicit macOS permission diagnostics.

## What you get

- Read Things lists, projects, tags, todos, search results, and individual items.
- Export open todos quickly, with optional full closed-item export when you need Logbook/Trash.
- Review Today, triage attention-worthy tasks, find follow-ups, applications, and stale todos.
- Mutate with previews: `add`, `update`, `move`, `complete`, `cancel`, and `create-project` are dry-run by default.
- Audit every applied mutation to JSONL and undo audited changes.
- Use agent-friendly contracts with `--json`, `schema`, `audit`, and `diff`.
- No direct SQLite writes. All live changes go through Things Apple Events.

## Install

Recommended:

```sh
brew install pipx
pipx ensurepath
pipx install git+https://github.com/marvinvista/things-cli.git
things diagnose
```

From a local clone:

```sh
git clone https://github.com/marvinvista/things-cli.git
cd things-cli
pipx install .
things diagnose
```

The first live command may trigger a macOS Automation permission prompt. Grant your terminal permission to control Things.

## Quick Start

```sh
# Check Things access
things diagnose

# Read data
things --json list --list Today --limit 10
things --json search "follow up" --limit 10
things get THINGS_TODO_ID

# Export before larger changes
things export --output /tmp/things-before.json

# Preview, then apply
things update THINGS_TODO_ID --tags "Follow Up"
things update THINGS_TODO_ID --tags "Follow Up" --yes

# Inspect and undo
things audit list --limit 5
things undo --last
things undo --last --yes
```

## Command Map

Command | Purpose
--- | ---
`diagnose` | Check Apple Events access and Things counts.
`lists`, `projects`, `tags` | Inspect Things structure without assuming names exist.
`list`, `search`, `get`, `show` | Read and reveal todos.
`export`, `diff` | Snapshot Things and compare before/after JSON exports.
`add`, `update`, `move`, `complete`, `cancel`, `create-project` | Dry-run-first mutations.
`bulk tag`, `bulk move` | Guardrailed batch changes using `--max` or `--ids-from`.
`audit summary`, `audit list`, `undo` | Review and reverse audited mutations.
`review`, `triage`, `attention`, `applications`, `followups`, `stale` | Daily planning workflows.
`schema` | Machine-readable JSON output contracts.

## Agent Pattern

```sh
things diagnose
things export --output /tmp/things-before.json
things --json search "query"
things update TODO_ID --tags "Example"
things update TODO_ID --tags "Example" --yes
things audit list --limit 5
```

Rules of thumb:

- Prefer `--json` for agent reads.
- Run `things diagnose` before trusting live data.
- Never mutate without inspecting the dry-run preview first.
- Export before bulk changes.
- Treat `Things Apple Events call failed` as a permission/runtime failure, not empty data.

More detail: [AGENTS.md](AGENTS.md), [docs/agent-usage.md](docs/agent-usage.md), and [docs/json-contract.md](docs/json-contract.md).

## Development

```sh
make install
make test
```

The default test suite does not mutate Things. Live tests are opt-in:

```sh
THINGS_LIVE_TESTS=1 .venv/bin/python -m unittest discover -s tests
```

Live tests create clearly named test items and cancel/complete them afterward. Keep them opt-in because they touch the real Things app.

## Permissions

`things-cli` uses Apple Events/JXA through `osascript`. If a command fails with an Apple Events error, grant your terminal app permission in:

`System Settings -> Privacy & Security -> Automation`

## Current Boundaries

- Requires macOS with Things 3 installed.
- Does not mutate checklist/subtask internals; Things does not expose those cleanly through the public scripting surface.
- Full `--include-closed` exports may be slower on very large Things libraries because they include Logbook and Trash.
- Moving todos into smart lists like Today/Tomorrow is implemented as scheduling. Moving between regular lists/projects uses Things move semantics.

## Related Docs

- [Install guide](docs/install.md)
- [Agent usage](docs/agent-usage.md)
- [JSON contracts](docs/json-contract.md)
- [Release checklist](docs/release.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

MIT. See [LICENSE](LICENSE).
