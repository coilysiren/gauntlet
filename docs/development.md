# Development Guide

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Docker | any | [docker.com](https://docker.com) |
| uv | latest | `brew install uv` (for local dev / pre-commit) |

## Setup

```bash
git clone git@github.com:coilysiren/gauntlet.git
cd gauntlet
uv sync
uv run pre-commit install  # install git hooks
```

## Running the MCP server locally

```bash
uv run gauntlet-mcp
```

This speaks stdio. To exercise it from Claude Code, register it:

```bash
claude mcp add gauntlet -- uv run gauntlet-mcp
```

Then open a session in this repo and use the `gauntlet` tools under `/mcp`.

## Running the demo API

```bash
uv run python demo_api/server.py
```

Starts the demo API on `http://localhost:8000`. It has three seeded flaws that the weapons in `.gauntlet/weapons/` should surface:

1. **PATCH without ownership check** - any user can modify any task
2. **POST accepts invalid/missing title** - no input validation
3. **GET /tasks leaks all users' data** - no read isolation

Point Gauntlet at `http://localhost:8000` from a Claude Code session to exercise the full loop end-to-end.

## Tests

```bash
# Run tests inside Docker (canonical)
docker compose run --rm test

# Run tests locally (faster iteration)
uv run pytest -m "not docker"

# Run docker integration tests (requires Docker daemon)
uv run pytest -m docker
```

Coverage is printed to the terminal and written to `coverage.xml` after every run. `coverage.xml` is gitignored.

## Linting & formatting

Pre-commit hooks run automatically on every `git commit`. To run manually:

```bash
uv run ruff check .          # lint
uv run ruff check . --fix    # lint + auto-fix
uv run ruff format .         # format
uv run mypy gauntlet tests demo_api --strict  # type-check
```

## CI

Three jobs run on every push and PR to `main`:

| Job | What it checks |
|---|---|
| `lint` | ruff + mypy |
| `test` | pytest + uploads coverage to Codecov |
| `docker` | `docker compose build` + `docker compose run --rm test` |

See `.github/workflows/ci.yml`.

## Dependency management

Add a runtime dependency:

```bash
uv add <package>
```

Add a dev-only dependency:

```bash
uv add --dev <package>
```

Always commit the updated `uv.lock` alongside `pyproject.toml`.
