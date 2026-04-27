#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", "build", "dist", ".mypy_cache", ".ruff_cache"}
CHECK_EXTENSIONS = {".md", ".py", ".toml", ".yml", ".yaml", ".json", ".sh", ".txt"}

FORBIDDEN_PATTERNS = [
    (re.compile(r"/Users/[A-Za-z0-9._-]+"), "local absolute user path"),
    (re.compile(r"/private/var/|/var/folders/"), "local macOS temporary path"),
    (re.compile(r"github\.com/OWNER/"), "placeholder GitHub owner"),
    (re.compile(r"BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY"), "private key material"),
    (re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*=\s*['\"][^'\"]+['\"]"), "literal credential assignment"),
    (re.compile(r"(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"), "email address"),
]

FORBIDDEN_FILE_PATTERNS = [
    (re.compile(r"(^|/)\.env(\..*)?$"), "environment file"),
    (re.compile(r"\.(sqlite|sqlite3|db|jsonl)$"), "local data file"),
    (re.compile(r"(^|/)(things-before|things-after|things-snapshot|things-full-snapshot)\.json$"), "Things snapshot"),
]

ALLOWED_PATHS = {
    Path("scripts/validate_public_surface.py"),
}


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.is_file() and path.suffix in CHECK_EXTENSIONS:
            files.append(path)
    return sorted(files)


def main() -> int:
    failures: list[str] = []
    for path in iter_files():
        rel = path.relative_to(ROOT)
        rel_text = rel.as_posix()
        for pattern, label in FORBIDDEN_FILE_PATTERNS:
            if pattern.search(rel_text):
                failures.append(f"{rel}: contains {label}")
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, label in FORBIDDEN_PATTERNS:
            if rel in ALLOWED_PATHS:
                continue
            if pattern.search(text):
                failures.append(f"{rel}: contains {label}")

    if failures:
        print("Public surface validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Public surface validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
