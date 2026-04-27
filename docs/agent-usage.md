# Using things-cli From AI Coding Agents

`things-cli` can be used by local AI coding agents such as Codex when the agent process can run shell commands on macOS and has Apple Events permission to control Things.

## Requirements

- macOS.
- Things installed.
- `things` installed through `pipx` or a local virtualenv.
- Automation permission for the terminal or agent host process.

## Preflight

Always start with:

```sh
things diagnose
```

The command should return JSON with `automation_access_ok: true`. If it fails, stop and ask the user to grant macOS Automation permission.

## Read

Use JSON for agent parsing:

```sh
things --json list --list Today --limit 20
things --json search "invoice" --limit 20
things --json review --limit 20
things export --output /tmp/things-before.json
```

Do not interpret an Apple Events failure as an empty task list.
Review workflows default to the fast `Today` scope. Use `--scope all` only when a full-library pass is needed.

## Mutate

All mutations are dry-run by default:

```sh
things update TODO_ID --tags "Finance"
```

Only apply after inspecting the preview:

```sh
things update TODO_ID --tags "Finance" --yes
```

The applied command emits an `event_id` and `audit_log` path. Preserve those in agent reports.

To inspect available machine-readable contracts:

```sh
things schema
```

## Bulk Mutation Rule

Before bulk mutation:

```sh
things export --output /tmp/things-before-bulk.json
things bulk tag --query "invoice" --tags "Finance"
things bulk tag --query "invoice" --tags "Finance" --max 10 --yes
```

The first bulk command is a preview. The second applies and writes a JSONL audit event.
Bulk `--yes` requires either `--max` or `--ids-from`.

For exact targeting:

```sh
things bulk tag --ids-from /tmp/todo-ids.txt --tags "Finance"
things bulk tag --ids-from /tmp/todo-ids.txt --tags "Finance" --yes
```

## Audit Logs

Default path:

```sh
~/.things-cli/mutations.jsonl
```

Override path:

```sh
things --audit-log /tmp/things-agent-audit.jsonl update TODO_ID --tags "Finance" --yes
THINGS_CLI_AUDIT_LOG=/tmp/things-agent-audit.jsonl things update TODO_ID --tags "Finance" --yes
```

Each line is one JSON object with `event_id`, `timestamp`, `action`, `before`, `change`, `after`, and `verified`.

Inspect logs:

```sh
things audit summary
things audit list --limit 20
```

## Undo

Undo is audit-log driven and dry-run by default:

```sh
things undo EVENT_ID
things undo EVENT_ID --yes
things undo --last
```

Undo restores audited `before` payloads when available. For created items, undo cancels the created todo or project rather than deleting it.

## Snapshot Diffing

Agents should take snapshots before and after larger work:

```sh
things export --output /tmp/things-before.json
# run reviewed mutations
things export --output /tmp/things-after.json
things diff /tmp/things-before.json /tmp/things-after.json
```
