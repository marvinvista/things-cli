# Agent Operating Guide

This repository builds `things-cli`, a macOS command-line interface for Things.

## Non-Negotiable Agent Rules

- Prefer `--json` for all agent reads.
- Run `things diagnose` before relying on live Things data.
- Prefer fast scoped workflows such as `things --json review --limit 20`; use `--scope all` only when needed.
- Never mutate Things without a preview command first.
- Never pass `--yes` unless the requested mutation target has been read and inspected in the same run.
- Export a snapshot before any bulk mutation:

```sh
things export --output /tmp/things-before.json
```

- Treat `things: ... Apple Events ...` errors as access/permission failures, not as empty Things data.
- Do not use or add direct SQLite writes.
- Do not assume any project, tag, list, or todo exists. Discover it with `lists`, `projects`, `tags`, `search`, or `get`.

## Reliable Agent Pattern

```sh
things diagnose
things export --output /tmp/things-before.json
things search "query" --json
things update TODO_ID --tags "Example"
things update TODO_ID --tags "Example" --yes
things undo EVENT_ID
```

Applied mutations append JSONL audit events to `~/.things-cli/mutations.jsonl` by default. Use `--audit-log PATH` or `THINGS_CLI_AUDIT_LOG=PATH` in tests and automation.

Use these commands to inspect agent state:

```sh
things schema
things audit summary
things audit list --limit 20
things diff /tmp/things-before.json /tmp/things-after.json
things undo EVENT_ID
```

`undo` is dry-run by default. Apply with `--yes` only after inspecting the undo plan.
For `add` and `create-project`, undo cancels the created item rather than deleting it.

Bulk `--yes` must use one of:

```sh
things bulk tag --query "query" --tags "Example" --max 10 --yes
things bulk tag --ids-from /tmp/todo-ids.txt --tags "Example" --yes
```

## Mutation Output Contract

Applied single-item mutations return:

```json
{
  "action": "update",
  "before": {},
  "after": {},
  "verified": true,
  "audit_log": "/path/to/mutations.jsonl",
  "event_id": "uuid"
}
```

Dry-runs return:

```json
{
  "dry_run": true,
  "action": "update",
  "payload": {
    "before": {},
    "change": {},
    "apply_with": "--yes"
  }
}
```

Bulk mutations return `results`, where each item has `before`, `after`, and `verified`.

## Validation

Use these checks after changes:

```sh
python3 -m unittest discover -s tests
python3 -m py_compile things_cli/client.py things_cli/cli.py things_cli/workflows.py things_cli/audit.py things_cli/schemas.py things_cli/snapshots.py
```

Live tests mutate Things and must stay opt-in:

```sh
THINGS_LIVE_TESTS=1 .venv/bin/python -m unittest tests.test_live_things
```
