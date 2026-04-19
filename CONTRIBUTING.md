# Contributing to Gauntlet

## Development environment

See [docs/development.md](docs/development.md) for full setup instructions. The short version:

```bash
git clone git@github.com:coilysiren/gauntlet.git
cd gauntlet
uv sync
uv run pre-commit install
```

## How to add a new weapon

A weapon is a YAML file that defines an attack strategy. No Python code is required.

1. Create a new YAML file in `.gauntlet/weapons/` (or wherever your project keeps weapons):

```yaml
# .gauntlet/weapons/my_new_weapon.yaml
id: my_snake_case_weapon_id
title: Short human-readable title
description: >
  Plain-English description of the attack surface. This is shown to the
  host agent's Attacker context (via WeaponBrief). Be specific about what
  API behavior is being tested.
blockers:
  - A concrete, externally observable assertion (e.g. "A DELETE by a non-owner is rejected with 403")
  - Another assertion the system must satisfy
  - Include expected HTTP status codes when possible
```

2. The fields map to the `Weapon` model in `gauntlet/models.py`:
   - `id` — stable snake_case identifier used to accumulate findings across runs
   - `title` — human-readable name
   - `description` — exposed via `WeaponBrief` to the host's Attacker context; `blockers` are withheld
   - `blockers` — the weapon's Vitals; checked by the host's HoldoutEvaluator context to produce a Clearance

3. Quality guidelines (enforced by `DemoWeaponAssessor` in `gauntlet/roles.py`):
   - Each blocker should be at least 20 characters
   - Include expected HTTP status codes in blockers (e.g. "rejected with 403")
   - Specify target endpoints so the assessor does not penalize the weapon

4. Test your weapon by exercising the MCP server from a Claude Code session — the host calls `assess_weapon` and `execute_plan` against a live SUT.

## How to add a new adapter

Adapters are execution surfaces that translate `Action`/`Observation` (or `HttpRequest`/`HttpResponse`) into real interactions. The existing adapters are HTTP (`gauntlet/adapters/http.py`), CLI (`gauntlet/adapters/cli.py`), and WebDriver (`gauntlet/adapters/webdriver.py`).

To add a new adapter, implement the `Adapter` protocol defined in `gauntlet/adapters/__init__.py`:

```python
from gauntlet.models import Action, HttpRequest, HttpResponse, Observation


class MyAdapter:
    """Implements the Adapter protocol."""

    def send(self, user: str, request: HttpRequest) -> HttpResponse:
        # HTTP-specific entry point.
        ...

    def execute(self, user: str, action: Action) -> Observation:
        # Surface-agnostic entry point — the Drone calls this.
        response = self.send(user, action.to_http_request())
        return Observation.from_http_response(response)
```

The protocol requires two methods:

```python
class Adapter(Protocol):
    def send(self, user: str, request: HttpRequest) -> HttpResponse: ...
    def execute(self, user: str, action: Action) -> Observation: ...
```

Place your adapter module in `gauntlet/adapters/` and re-export it from `gauntlet/adapters/__init__.py` by adding it to the imports and `__all__` list.

## How to add a new MCP tool

MCP tools live in `gauntlet/server.py`. Each tool is a decorated function:

```python
@mcp.tool()
def my_new_tool(arg: str) -> SomeModel:
    """One-line summary, followed by a body explaining when the host should call this
    and any host-discipline constraints (e.g. 'read only in the Inspector context')."""
    ...
```

Tool inputs and outputs should be Pydantic models from `models.py` (or a primitive type). FastMCP generates the JSON Schema automatically from the type hints. Keep the tool surface minimal — one tool per deterministic operation the host cannot do on its own.

Add test coverage in `tests/test_gauntlet.py` by calling the tool function directly — it's just a Python function decorated with `@mcp.tool()`.

## Running tests

```bash
# Canonical: run tests inside Docker
docker compose run --rm test

# Local (faster iteration, skips Docker-only tests)
uv run pytest -m "not docker"

# Docker integration tests only
uv run pytest -m docker
```

## Code style

Linting and formatting are enforced by pre-commit hooks and CI. To run manually:

```bash
uv run ruff check .            # lint
uv run ruff format --check .   # format check
uv run mypy gauntlet tests demo_api --strict  # type-check
```

All code must pass `ruff check` and `ruff format --check` with no errors. Type annotations are required (`mypy --strict`).

## Extension points summary

| Extension point | What to create | Interface / schema |
|---|---|---|
| New weapon | YAML file in `.gauntlet/weapons/` | `id`, `title`, `description`, `blockers` fields |
| New adapter | Python module in `gauntlet/adapters/` | `Adapter` protocol: `send()` + `execute()` |
| New MCP tool | `@mcp.tool()` function in `gauntlet/server.py` | Typed Python function; Pydantic in/out |
| New weapon assessor | Python class anywhere | `WeaponAssessor` protocol: `assess(weapon, target) -> WeaponAssessment` |
