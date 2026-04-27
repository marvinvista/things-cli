from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol


APP_NAME = "Things3"
OPEN_LIST_NAMES = ("Inbox", "Today", "Tomorrow", "Anytime", "Upcoming", "Someday", "Later Projects")


class ThingsError(RuntimeError):
    """Raised when Things cannot be queried or updated reliably."""


class Runner(Protocol):
    def run_jxa(self, script: str) -> str: ...
    def run_applescript(self, script: str) -> str: ...


@dataclass
class OsaRunner:
    app_name: str = APP_NAME
    timeout: int = 90
    retries: int = 1

    def run_jxa(self, script: str) -> str:
        return self._run_osascript(["osascript", "-l", "JavaScript"], script, ".js")

    def run_applescript(self, script: str) -> str:
        return self._run_osascript(["osascript"], script, ".applescript")

    def _run_osascript(self, command: list[str], script: str, suffix: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as handle:
            handle.write(script)
            path = handle.name
        try:
            last_error = ""
            for attempt in range(self.retries + 1):
                try:
                    proc = subprocess.run(
                        [*command, path],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                    )
                except subprocess.TimeoutExpired as exc:
                    last_error = f"osascript timed out after {self.timeout}s"
                    if attempt >= self.retries:
                        raise ThingsError(last_error) from exc
                    time.sleep(0.4 * (attempt + 1))
                    continue

                if proc.returncode == 0:
                    return proc.stdout.strip()
                last_error = proc.stderr.strip() or proc.stdout.strip()
                if attempt < self.retries:
                    time.sleep(0.4 * (attempt + 1))
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

        raise ThingsError(
            "Things Apple Events call failed. Make sure Things is installed and "
            "Automation permission is granted for this terminal.\n"
            f"{last_error}"
        )


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _json_literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _script(body: str, app_name: str = APP_NAME) -> str:
    return f"""
ObjC.import('stdlib');
const app = Application({_json_literal(app_name)});

function valueOrNull(read) {{
  try {{
    const value = read();
    if (value === undefined) return null;
    return value;
  }} catch (error) {{
    return null;
  }}
}}

function dateOrNull(read) {{
  const value = valueOrNull(read);
  if (!value) return null;
  try {{
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, '0');
    const day = String(value.getDate()).padStart(2, '0');
    return `${{year}}-${{month}}-${{day}}`;
  }} catch (error) {{
    return String(value);
  }}
}}

function relationName(read) {{
  return valueOrNull(() => {{
    const relation = read();
    if (!relation) return null;
    return relation.name();
  }});
}}

function relationId(read) {{
  return valueOrNull(() => {{
    const relation = read();
    if (!relation) return null;
    return relation.id();
  }});
}}

function todoToObject(todo) {{
  return {{
    id: todo.id(),
    name: todo.name(),
    status: String(todo.status()),
    notes: valueOrNull(() => todo.notes()),
    tag_names: valueOrNull(() => todo.tagNames()),
    created: dateOrNull(() => todo.creationDate()),
    modified: dateOrNull(() => todo.modificationDate()),
    due: dateOrNull(() => todo.dueDate()),
    when: dateOrNull(() => todo.activationDate()),
    completed: dateOrNull(() => todo.completionDate()),
    canceled: dateOrNull(() => todo.cancellationDate()),
    project: relationName(() => todo.project()),
    project_id: relationId(() => todo.project()),
    area: relationName(() => todo.area()),
    area_id: relationId(() => todo.area()),
    contact: relationName(() => todo.contact())
  }};
}}

function parseDate(value) {{
  if (value === null || value === undefined || value === '') return null;
  const match = String(value).match(/^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})$/);
  if (!match) {{
    throw new Error('Invalid date, expected YYYY-MM-DD: ' + value);
  }}
  const year = Number(match[1]);
  const month = Number(match[2]) - 1;
  const day = Number(match[3]);
  return new Date(year, month, day, 12, 0, 0);
}}

function findList(name) {{
  const lower = String(name).toLowerCase();
  const matches = app.lists().filter(list => list.name().toLowerCase() === lower);
  if (!matches.length) throw new Error('Things list not found: ' + name);
  return matches[0];
}}

function findProject(name) {{
  const lower = String(name).toLowerCase();
  const matches = app.projects().filter(project => project.name().toLowerCase() === lower);
  if (!matches.length) throw new Error('Things project not found: ' + name);
  return matches[0];
}}

function findTodo(id) {{
  try {{
    const todo = app.toDos.byId(id);
    todo.name();
    return todo;
  }} catch (error) {{
    const lists = app.lists();
    for (let i = 0; i < lists.length; i++) {{
      const listName = lists[i].name();
      if (listName === 'Logbook' || listName === 'Trash') continue;
      const hits = lists[i].toDos().filter(todo => todo.id() === id);
      if (hits.length) return hits[0];
    }}
    throw new Error('Things todo not found: ' + id);
  }}
}}

function allTodos(includeClosed) {{
  const seen = {{}};
  const todos = [];
  const lists = app.lists();
  for (let i = 0; i < lists.length; i++) {{
    const listName = lists[i].name();
    if (!includeClosed && (listName === 'Logbook' || listName === 'Trash')) continue;
    const listTodos = lists[i].toDos();
    for (let j = 0; j < listTodos.length; j++) {{
      const todo = listTodos[j];
      const id = todo.id();
      if (seen[id]) continue;
      const item = todoToObject(todo);
      item.list = listName;
      todos.push(item);
      seen[id] = true;
    }}
  }}
  return todos;
}}

function printJSON(value) {{
  return JSON.stringify(value, null, 2);
}}

{body}
"""


class ThingsClient:
    def __init__(self, runner: Runner | None = None, app_name: str = APP_NAME):
        self.app_name = app_name
        self.runner = runner or OsaRunner(app_name=app_name)

    def _run(self, body: str) -> Any:
        output = self.runner.run_jxa(_script(body, self.app_name))
        if not output:
            raise ThingsError("Things returned no output. This usually means Apple Events access failed silently.")
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise ThingsError(f"Things returned non-JSON output: {output}") from exc

    def _normalize_private_todo(self, todo: dict[str, Any], list_name: str | None = None) -> dict[str, Any]:
        def normalize_date(value: Any) -> str | None:
            if not value:
                return None
            text = str(value)
            if "T" in text:
                try:
                    return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
                except ValueError:
                    return text[:10]
            return text[:10]

        def relation_name(value: Any) -> str | None:
            if isinstance(value, dict):
                return value.get("name")
            return value

        def relation_id(value: Any) -> str | None:
            if isinstance(value, dict):
                return value.get("id")
            return None

        project = todo.get("project")
        area = todo.get("area")

        return {
            "id": todo.get("id"),
            "name": todo.get("name") or "",
            "status": todo.get("status"),
            "notes": todo.get("notes") or "",
            "tag_names": todo.get("tagNames") or "",
            "created": normalize_date(todo.get("creationDate")),
            "modified": normalize_date(todo.get("modificationDate")),
            "due": normalize_date(todo.get("deadline")),
            "when": normalize_date(todo.get("when")),
            "completed": normalize_date(todo.get("completionDate")),
            "canceled": normalize_date(todo.get("cancellationDate")),
            "project": relation_name(project),
            "project_id": todo.get("projectId") or relation_id(project),
            "area": relation_name(area),
            "area_id": todo.get("areaId") or relation_id(area),
            "contact": todo.get("contact"),
            "list": list_name,
        }

    def list_todos_fast(
        self,
        list_name: str = "Today",
        limit: int | None = None,
        include_closed: bool = False,
    ) -> list[dict[str, Any]]:
        output = self.runner.run_applescript(
            f"""
tell application {_applescript_string(self.app_name)}
  get _private_experimental_ json of to dos of list {_applescript_string(list_name)}
end tell
"""
        )
        if not output.strip():
            return []
        try:
            raw_todos = json.loads(f"[{output}]")
        except json.JSONDecodeError as exc:
            raise ThingsError(f"Could not parse Things fast JSON output for list {list_name}.") from exc

        todos = [self._normalize_private_todo(todo, list_name) for todo in raw_todos]
        if not include_closed:
            todos = [todo for todo in todos if todo.get("status") == "open"]
        todos.sort(key=lambda item: item.get("when") or item.get("due") or "9999-99-99")
        if limit is not None:
            todos = todos[:limit]
        return todos

    def _open_todos_fast(self) -> list[dict[str, Any]]:
        seen = set()
        todos = []
        for list_name in OPEN_LIST_NAMES:
            for todo in self.list_todos_fast(list_name):
                todo_id = todo.get("id")
                if todo_id in seen:
                    continue
                seen.add(todo_id)
                todos.append(todo)
        todos.sort(key=lambda item: item.get("when") or item.get("due") or "9999-99-99")
        return todos

    def diagnose(self) -> dict[str, Any]:
        return self._run(
            """
const lists = app.lists().map(list => ({ name: list.name(), count: list.toDos().length }));
printJSON({
  app: app.name(),
  version: app.version(),
  bundle: 'com.culturedcode.ThingsMac',
  list_count: lists.length,
  lists,
  top_level_todos: app.toDos().length,
  projects: app.projects().length,
  areas: app.areas().length,
  automation_access_ok: lists.length > 0
});
"""
        )

    def lists(self) -> list[dict[str, Any]]:
        return self._run(
            """
printJSON(app.lists().map(list => ({
  id: list.id(),
  name: list.name(),
  count: list.toDos().length
})));
"""
        )

    def projects(self) -> list[dict[str, Any]]:
        return self._run(
            """
printJSON(app.projects().map(project => ({
  id: project.id(),
  name: project.name(),
  status: String(project.status()),
  tag_names: valueOrNull(() => project.tagNames()),
  due: dateOrNull(() => project.dueDate()),
  when: dateOrNull(() => project.activationDate()),
  count: project.toDos().length
})));
"""
        )

    def tags(self) -> list[dict[str, Any]]:
        return self._run(
            """
printJSON(app.tags().map(tag => ({
  id: tag.id(),
  name: tag.name(),
  shortcut: valueOrNull(() => tag.keyboardShortcut()),
  count: tag.toDos().length
})));
"""
        )

    def export(self, include_closed: bool = False) -> dict[str, Any]:
        if not include_closed:
            return {
                "exported_at": datetime.now().isoformat(),
                "app": self.diagnose()["app"],
                "version": self.diagnose()["version"],
                "include_closed": False,
                "lists": self.lists(),
                "projects": self.projects(),
                "tags": self.tags(),
                "todos": self._open_todos_fast(),
            }
        return self._run(
            f"""
const includeClosed = {json.dumps(include_closed)};
printJSON({{
  exported_at: new Date().toISOString(),
  app: app.name(),
  version: app.version(),
  include_closed: includeClosed,
  lists: app.lists().map(list => ({{ id: list.id(), name: list.name(), count: list.toDos().length }})),
  projects: app.projects().map(project => ({{
    id: project.id(),
    name: project.name(),
    status: String(project.status()),
    tag_names: valueOrNull(() => project.tagNames()),
    due: dateOrNull(() => project.dueDate()),
    when: dateOrNull(() => project.activationDate()),
    count: project.toDos().length
  }})),
  tags: app.tags().map(tag => ({{ id: tag.id(), name: tag.name(), count: tag.toDos().length }})),
  todos: allTodos(includeClosed)
}});
"""
        )

    def list_todos(
        self,
        list_name: str | None = None,
        limit: int | None = None,
        include_closed: bool = False,
    ) -> list[dict[str, Any]]:
        if not include_closed:
            todos = self.list_todos_fast(list_name) if list_name else self._open_todos_fast()
            if limit is not None:
                todos = todos[:limit]
            return todos
        source = "findList(%s).toDos().map(todoToObject)" % _json_literal(list_name) if list_name else f"allTodos({json.dumps(include_closed)})"
        return self._run(
            f"""
let todos = {source};
if (!{json.dumps(include_closed)}) todos = todos.filter(todo => todo.status === 'open');
todos.sort((a, b) => (a.when || a.due || '9999-99-99').localeCompare(b.when || b.due || '9999-99-99'));
if ({json.dumps(limit)} !== null) todos = todos.slice(0, {json.dumps(limit)});
printJSON(todos);
"""
        )

    def get(self, todo_id: str) -> dict[str, Any]:
        return self._run(f"printJSON(todoToObject(findTodo({_json_literal(todo_id)})));")

    def search(
        self,
        query: str,
        list_name: str | None = None,
        limit: int | None = None,
        include_closed: bool = False,
    ) -> list[dict[str, Any]]:
        if not include_closed:
            needle = query.lower()
            todos = self.list_todos_fast(list_name) if list_name else self._open_todos_fast()
            matches = []
            for todo in todos:
                haystack = "\n".join(
                    str(todo.get(key) or "")
                    for key in ("name", "notes", "tag_names", "project", "area", "list")
                ).lower()
                if needle in haystack:
                    matches.append(todo)
            if limit is not None:
                matches = matches[:limit]
            return matches
        source = "findList(%s).toDos().map(todoToObject)" % _json_literal(list_name) if list_name else f"allTodos({json.dumps(include_closed)})"
        return self._run(
            f"""
const needle = {_json_literal(query)}.toLowerCase();
let todos = {source};
if (!{json.dumps(include_closed)}) todos = todos.filter(todo => todo.status === 'open');
todos = todos.filter(todo => {{
  const haystack = [todo.name, todo.notes, todo.tag_names, todo.project, todo.area].join('\\n').toLowerCase();
  return haystack.includes(needle);
}});
if ({json.dumps(limit)} !== null) todos = todos.slice(0, {json.dumps(limit)});
printJSON(todos);
"""
        )

    def add(
        self,
        name: str,
        notes: str | None = None,
        due: date | str | None = None,
        tags: str | None = None,
        when: date | str | None = None,
        list_name: str = "Inbox",
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "notes": notes,
            "due": str(due) if due else None,
            "when": str(when) if when else None,
            "tags": tags,
            "list": list_name,
        }
        return self._run(
            f"""
const payload = {_json_literal(payload)};
const props = {{ name: payload.name }};
if (payload.notes !== null) props.notes = payload.notes;
if (payload.tags !== null) props.tagNames = payload.tags;
if (payload.due !== null) props.dueDate = parseDate(payload.due);
if (payload.when !== null) props.activationDate = parseDate(payload.when);
const target = findList(payload.list);
const todo = app.ToDo(props).make({{ at: target }});
printJSON(todoToObject(todo));
"""
        )

    def update(
        self,
        todo_id: str,
        name: str | None = None,
        notes: str | None = None,
        due: date | str | None = None,
        clear_due: bool = False,
        when: date | str | None = None,
        clear_when: bool = False,
        tags: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "id": todo_id,
            "name": name,
            "notes": notes,
            "due": str(due) if due else None,
            "clear_due": clear_due,
            "when": str(when) if when else None,
            "clear_when": clear_when,
            "tags": tags,
        }
        return self._run(
            f"""
const payload = {_json_literal(payload)};
const todo = findTodo(payload.id);
if (payload.name !== null) todo.name.set(payload.name);
if (payload.notes !== null) todo.notes.set(payload.notes);
if (payload.tags !== null) todo.tagNames.set(payload.tags);
if (payload.clear_due) todo.dueDate.set(null);
if (payload.due !== null) todo.dueDate.set(parseDate(payload.due));
if (payload.clear_when) app.schedule(todo, {{for: null}});
if (payload.when !== null) app.schedule(todo, {{for: parseDate(payload.when)}});
printJSON(todoToObject(todo));
"""
        )

    def move(self, todo_id: str, list_name: str | None = None, project_name: str | None = None) -> dict[str, Any]:
        if bool(list_name) == bool(project_name):
            raise ThingsError("Move requires exactly one of list_name or project_name.")
        if list_name and list_name.lower() in {"today", "tomorrow"}:
            days = 1 if list_name.lower() == "tomorrow" else 0
            return self._run(
                f"""
const todo = findTodo({_json_literal(todo_id)});
const targetDate = new Date();
targetDate.setHours(12, 0, 0, 0);
targetDate.setDate(targetDate.getDate() + {days});
app.schedule(todo, {{for: targetDate}});
const result = todoToObject(todo);
result.list = {_json_literal(list_name)};
printJSON(result);
"""
            )
        target = (
            f"findList({_json_literal(list_name)})"
            if list_name
            else f"findProject({_json_literal(project_name)})"
        )
        return self._run(
            f"""
const todo = findTodo({_json_literal(todo_id)});
const target = {target};
app.move(todo, {{to: target}});
printJSON(todoToObject(todo));
"""
        )

    def create_project(
        self,
        name: str,
        notes: str | None = None,
        due: date | str | None = None,
        when: date | str | None = None,
        tags: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "notes": notes,
            "due": str(due) if due else None,
            "when": str(when) if when else None,
            "tags": tags,
        }
        return self._run(
            f"""
const payload = {_json_literal(payload)};
const props = {{ name: payload.name }};
if (payload.notes !== null) props.notes = payload.notes;
if (payload.tags !== null) props.tagNames = payload.tags;
if (payload.due !== null) props.dueDate = parseDate(payload.due);
if (payload.when !== null) props.activationDate = parseDate(payload.when);
const project = app.Project(props).make();
printJSON(todoToObject(project));
"""
        )

    def complete(self, todo_id: str) -> dict[str, Any]:
        self.set_status(todo_id, "completed")
        return self.get(todo_id)

    def cancel(self, todo_id: str) -> dict[str, Any]:
        self.set_status(todo_id, "canceled")
        return self.get(todo_id)

    def set_status(self, todo_id: str, status: str) -> None:
        if status not in {"open", "completed", "canceled"}:
            raise ThingsError(f"Unsupported Things status: {status}")
        self.runner.run_applescript(
            f"""
tell application {_applescript_string(self.app_name)}
  set status of to do id {_applescript_string(todo_id)} to {status}
end tell
"""
        )

    def restore_todo(self, todo: dict[str, Any]) -> dict[str, Any]:
        todo_id = todo.get("id")
        if not todo_id:
            raise ThingsError("Cannot restore todo without an id.")
        self.update(
            todo_id,
            name=todo.get("name"),
            notes=todo.get("notes"),
            due=todo.get("due"),
            clear_due=todo.get("due") is None,
            when=todo.get("when"),
            clear_when=False,
            tags=todo.get("tag_names"),
        )
        if todo.get("project"):
            self.move(todo_id, project_name=todo.get("project"))
        elif todo.get("list"):
            self.move(todo_id, list_name=todo.get("list"))
        if todo.get("status") in {"open", "completed", "canceled"}:
            self.set_status(todo_id, todo["status"])
        return self.get(todo_id)

    def show(self, todo_id: str) -> dict[str, Any]:
        return self._run(
            f"""
const todo = findTodo({_json_literal(todo_id)});
app.show(todo);
printJSON({{ shown: true, id: todo.id(), name: todo.name() }});
"""
        )
