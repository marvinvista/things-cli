from __future__ import annotations

from typing import Any


TODO_SCHEMA: dict[str, Any] = {
    "id": "string",
    "name": "string",
    "status": "open|completed|canceled",
    "notes": "string|null",
    "tag_names": "comma-separated string|null",
    "created": "YYYY-MM-DD|null",
    "modified": "YYYY-MM-DD|null",
    "due": "YYYY-MM-DD|null",
    "when": "YYYY-MM-DD|null",
    "completed": "YYYY-MM-DD|null",
    "canceled": "YYYY-MM-DD|null",
    "project": "string|null",
    "project_id": "string|null",
    "area": "string|null",
    "area_id": "string|null",
    "contact": "string|null",
    "list": "string|null",
}

EXPORT_SCHEMA: dict[str, Any] = {
    "exported_at": "ISO-8601 timestamp",
    "app": "Things",
    "version": "string",
    "include_closed": "boolean",
    "lists": [{"id": "string", "name": "string", "count": "integer"}],
    "projects": [{"id": "string", "name": "string", "status": "string", "count": "integer"}],
    "tags": [{"id": "string", "name": "string", "count": "integer"}],
    "todos": [TODO_SCHEMA],
}

DRY_RUN_SCHEMA: dict[str, Any] = {
    "dry_run": True,
    "action": "string",
    "payload": {
        "before": "object|null",
        "change": "object",
        "apply_with": "--yes",
    },
}

APPLIED_MUTATION_SCHEMA: dict[str, Any] = {
    "action": "string",
    "before": "object|null",
    "after": "object",
    "verified": "boolean",
    "audit_log": "path",
    "event_id": "uuid",
}

UNDO_DRY_RUN_SCHEMA: dict[str, Any] = {
    "dry_run": True,
    "action": "undo",
    "payload": {
        "event_id": "uuid",
        "original_action": "string",
        "undo_plan": [
            {
                "operation": "restore|cancel-created",
                "id": "todo-id",
                "before": "object|null",
                "after": "object|null",
            }
        ],
        "apply_with": "--yes",
    },
}

AUDIT_EVENT_SCHEMA: dict[str, Any] = {
    "event_id": "uuid",
    "timestamp": "ISO-8601 timestamp",
    "tool": "things-cli",
    "action": "string",
    "dry_run": False,
    "before": "object|array|null",
    "change": "object|null",
    "after": "object|array|null",
    "verified": "boolean|null",
}

SCHEMAS: dict[str, dict[str, Any]] = {
    "todo": TODO_SCHEMA,
    "export": EXPORT_SCHEMA,
    "dry-run": DRY_RUN_SCHEMA,
    "applied-mutation": APPLIED_MUTATION_SCHEMA,
    "undo-dry-run": UNDO_DRY_RUN_SCHEMA,
    "audit-event": AUDIT_EVENT_SCHEMA,
}
