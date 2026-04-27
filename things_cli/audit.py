from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_AUDIT_PATH = Path.home() / ".things-cli" / "mutations.jsonl"


def audit_path(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser()
    env_path = os.environ.get("THINGS_CLI_AUDIT_LOG")
    if env_path:
        return Path(env_path).expanduser()
    return DEFAULT_AUDIT_PATH


def append_audit_event(
    action: str,
    *,
    path: str | None = None,
    before: Any = None,
    after: Any = None,
    change: Any = None,
    verified: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": "things-cli",
        "action": action,
        "dry_run": False,
        "before": before,
        "change": change,
        "after": after,
        "verified": verified,
    }
    if extra:
        event.update(extra)

    target = audit_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    return {"audit_log": str(target), "event_id": event["event_id"]}


def read_audit_events(path: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    target = audit_path(path)
    if not target.exists():
        return []

    events: list[dict[str, Any]] = []
    with target.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on audit log line {line_number}: {target}") from exc
            events.append(event)

    if limit is not None:
        return events[-limit:]
    return events


def audit_summary(path: str | None = None) -> dict[str, Any]:
    target = audit_path(path)
    events = read_audit_events(path)
    by_action: dict[str, int] = {}
    for event in events:
        action = str(event.get("action") or "unknown")
        by_action[action] = by_action.get(action, 0) + 1

    return {
        "audit_log": str(target),
        "exists": target.exists(),
        "count": len(events),
        "first_timestamp": events[0].get("timestamp") if events else None,
        "last_timestamp": events[-1].get("timestamp") if events else None,
        "by_action": by_action,
    }


def find_audit_event(event_id: str | None = None, *, path: str | None = None, last: bool = False) -> dict[str, Any]:
    events = read_audit_events(path)
    if not events:
        raise ValueError("No audit events found.")
    if last:
        return events[-1]
    if not event_id:
        raise ValueError("Provide an event id or --last.")
    for event in events:
        if event.get("event_id") == event_id:
            return event
    raise ValueError(f"Audit event not found: {event_id}")
