# JSON Contract

This document describes the stable JSON shapes intended for agents.

## Todo

```json
{
  "id": "string",
  "name": "string",
  "status": "open",
  "notes": "string",
  "tag_names": "Comma, Separated",
  "created": "YYYY-MM-DD",
  "modified": "YYYY-MM-DD",
  "due": "YYYY-MM-DD",
  "when": "YYYY-MM-DD",
  "completed": null,
  "canceled": null,
  "project": "string",
  "project_id": "string",
  "area": "string",
  "area_id": "string",
  "contact": "string",
  "list": "Today"
}
```

Date fields may be `null`.

## Dry-Run Mutation

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

Dry-runs do not write audit events.

## Applied Single-Item Mutation

```json
{
  "action": "update",
  "before": {},
  "after": {},
  "verified": true,
  "audit_log": "~/.things-cli/mutations.jsonl",
  "event_id": "uuid"
}
```

## Applied Bulk Mutation

```json
{
  "action": "bulk tag",
  "count": 2,
  "results": [
    {
      "before": {},
      "after": {},
      "verified": true
    }
  ],
  "audit_log": "~/.things-cli/mutations.jsonl",
  "event_id": "uuid"
}
```

## Undo Dry-Run

```json
{
  "dry_run": true,
  "action": "undo",
  "payload": {
    "event_id": "uuid",
    "original_action": "update",
    "undo_plan": [
      {
        "operation": "restore",
        "id": "todo-id",
        "before": {}
      }
    ],
    "apply_with": "--yes"
  }
}
```

## Audit Event

Each audit log line is JSON:

```json
{
  "event_id": "uuid",
  "timestamp": "2026-04-26T00:00:00+00:00",
  "tool": "things-cli",
  "action": "update",
  "dry_run": false,
  "before": {},
  "change": {},
  "after": {},
  "verified": true
}
```

## Error Behavior

CLI errors are written to stderr and return exit code `2`. Apple Events errors should be treated as access failures unless proven otherwise.

## Discovering Schemas

Agents can retrieve the current schema bundle from the CLI:

```sh
things schema
```
