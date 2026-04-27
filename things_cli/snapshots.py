from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TRACKED_TODO_FIELDS = (
    "name",
    "status",
    "notes",
    "tag_names",
    "due",
    "when",
    "completed",
    "canceled",
    "project",
    "project_id",
    "area",
    "area_id",
    "contact",
    "list",
)


def load_snapshot(path: str) -> dict[str, Any]:
    with Path(path).expanduser().open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("todos"), list):
        raise ValueError(f"Snapshot does not look like a things-cli export: {path}")
    return payload


def todos_by_id(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for todo in snapshot.get("todos", []):
        todo_id = todo.get("id")
        if todo_id:
            result[todo_id] = todo
    return result


def diff_snapshots(before_path: str, after_path: str) -> dict[str, Any]:
    before_snapshot = load_snapshot(before_path)
    after_snapshot = load_snapshot(after_path)
    before = todos_by_id(before_snapshot)
    after = todos_by_id(after_snapshot)

    before_ids = set(before)
    after_ids = set(after)

    added = [after[todo_id] for todo_id in sorted(after_ids - before_ids)]
    removed = [before[todo_id] for todo_id in sorted(before_ids - after_ids)]
    changed = []

    for todo_id in sorted(before_ids & after_ids):
        field_changes = {}
        for field in TRACKED_TODO_FIELDS:
            old = before[todo_id].get(field)
            new = after[todo_id].get(field)
            if old != new:
                field_changes[field] = {"before": old, "after": new}
        if field_changes:
            changed.append(
                {
                    "id": todo_id,
                    "before_name": before[todo_id].get("name"),
                    "after_name": after[todo_id].get("name"),
                    "changes": field_changes,
                }
            )

    return {
        "before": before_path,
        "after": after_path,
        "before_count": len(before),
        "after_count": len(after),
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "added": added,
        "removed": removed,
        "changed": changed,
    }
