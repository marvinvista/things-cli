# Security Policy

## Supported Versions

`things-cli` is pre-1.0. Security fixes target the current `main` branch and the latest tagged release once releases begin.

## Reporting a Vulnerability

Please do not open a public issue for vulnerabilities that expose private Things data, local paths, credentials, or mutation behavior that can cause unintended changes.

Use GitHub's private vulnerability reporting if it is enabled for the repository. If it is not enabled yet, open a minimal issue asking for a private reporting channel without including sensitive details.

## Security Model

`things-cli`:

- Talks to Things through macOS Apple Events/JXA.
- Does not write directly to Things SQLite databases.
- Defaults mutations to dry-run previews.
- Writes applied mutation audit events to `~/.things-cli/mutations.jsonl` unless overridden.
- May print todo names, notes, tags, project names, and other Things metadata to stdout.

Users should treat CLI output, exports, and audit logs as private productivity data.

## Permissions

The CLI requires macOS Automation permission for the calling terminal process to control Things. A failure such as `Things Apple Events call failed` should be treated as an access/runtime failure, not as proof that Things contains no data.
