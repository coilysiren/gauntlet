# AGENTS.md

Developer reference for agents and humans working on this codebase.

## Docs

- [Architecture](docs/architecture.md) — module map, key abstractions, data flow, design decisions
- [Development](docs/development.md) — setup, tests, linting, Docker, CI
- [Usage](docs/usage.md) — workflow runbook: when to run, how to integrate, how to act on results

## Git workflow

Commit directly to `main` without asking for confirmation, including `git add`. Do not open pull requests unless explicitly asked.

Commit whenever a unit of work feels sufficiently complete — after fixing a bug, adding a feature, passing tests, or reaching any other natural stopping point. Don't wait for the user to ask.

## Before every commit

Sync `docs/architecture.md` with the current module structure in `flux_gate/`. Check for new files, removed files, new classes/protocols, and changed abstractions.

## Approved commands

Any command listed in [docs/development.md](docs/development.md) may be run without requesting user approval.

## Rules

After any code change:

1. Run `docker compose run --rm test` — all tests must pass
2. Run `uv run ruff check . && uv run ruff format --check .` — no lint or format errors
3. Run `uv run mypy flux_gate tests demo_api --strict` — no type errors

Pre-commit enforces rules 2 and 3 automatically on `git commit`.
