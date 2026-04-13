# Contributing to Gauntlet

## Development environment

See [docs/development.md](docs/development.md) for full setup instructions. The short version:

```bash
git clone git@github.com:coilysiren/gauntlet.git
cd gauntlet
docker compose build
uv run pre-commit install
```

## How to add a new weapon

A weapon is a YAML file that defines an attack strategy. No Python code is required.

1. Create a new YAML file in `.gauntlet/guards/` (or wherever your project keeps weapons):

```yaml
# .gauntlet/guards/my_new_weapon.yaml
id: my_snake_case_weapon_id
title: Short human-readable title
description: >
  Plain-English description of the attack surface. This is shown to the
  Attacker to guide probe plan generation. Be specific about what API
  behavior is being tested.
blockers:
  - A concrete, externally observable assertion (e.g. "A DELETE by a non-owner is rejected with 403")
  - Another assertion the system must satisfy
  - Include expected HTTP status codes when possible
target_endpoints:
  - POST /resources
  - DELETE /resources/{id}
```

2. The fields map to the `Weapon` model in `gauntlet/models.py`:
   - `id` -- stable snake_case identifier used to accumulate findings across runs
   - `title` -- human-readable name
   - `description` -- given to the Attacker (via `WeaponBrief`); the Attacker never sees `blockers`
   - `blockers` -- the weapon's Vitals; checked independently by the holdout system to produce a Clearance

3. Quality guidelines (enforced by `WeaponAssessor` in `gauntlet/roles.py`):
   - Each blocker should be at least 20 characters
   - Include expected HTTP status codes in blockers (e.g. "rejected with 403")
   - Specify target endpoints so the assessor does not penalize the weapon

4. Test your weapon by running the full loop against a live API:

```bash
gauntlet http://localhost:8000 --weapon .gauntlet/guards/my_new_weapon.yaml
```

## How to add a new adapter

Adapters are execution surfaces that translate `HttpRequest`/`HttpResponse` into real interactions. The existing adapters are HTTP (`gauntlet/adapters/http.py`), CLI (`gauntlet/adapters/cli.py`), and WebDriver (`gauntlet/adapters/webdriver.py`).

To add a new adapter, implement the `Adapter` protocol defined in `gauntlet/adapters/__init__.py`:

```python
from gauntlet.adapters import Adapter
from gauntlet.models import HttpRequest, HttpResponse


class MyAdapter:
    """Implements the Adapter protocol."""

    def send(self, user: str, request: HttpRequest) -> HttpResponse:
        # Translate the request into your execution surface,
        # execute it, and return an HttpResponse.
        ...
```

The protocol requires a single method:

```python
class Adapter(Protocol):
    def send(self, user: str, request: HttpRequest) -> HttpResponse: ...
```

Place your adapter module in `gauntlet/adapters/` and re-export it from `gauntlet/adapters/__init__.py` by adding it to the imports and `__all__` list.

## How to add a new role

Roles are defined as Python `Protocol` classes in `gauntlet/roles.py`. The existing roles are:

| Role | Method | Purpose |
|---|---|---|
| `Attacker` | `generate_plans(spec, previous_iterations) -> list[Plan]` | Generates test plans |
| `Inspector` | `analyze(spec, execution_results) -> list[Finding]` | Analyzes results for findings |
| `HoldoutVitals` | `acceptance_plans(weapon) -> list[Plan]` | Converts blockers to acceptance plans |
| `WeaponAssessor` | `assess(weapon, target) -> WeaponAssessment` | Preflight quality check on weapons |

To implement a new variant of an existing role, create a class that satisfies the protocol. No base class inheritance is needed -- just match the method signature.

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
| New weapon | YAML file in `.gauntlet/guards/` | `id`, `title`, `description`, `blockers` fields |
| New adapter | Python module in `gauntlet/adapters/` | `Adapter` protocol: `send(user, request) -> HttpResponse` |
| New attacker | Python class anywhere | `Attacker` protocol: `generate_plans(spec, previous_iterations) -> list[Plan]` |
| New inspector | Python class anywhere | `Inspector` protocol: `analyze(spec, execution_results) -> list[Finding]` |
| New holdout vitals | Python class anywhere | `HoldoutVitals` protocol: `acceptance_plans(weapon) -> list[Plan]` |
| New weapon assessor | Python class anywhere | `WeaponAssessor` protocol: `assess(weapon, target) -> WeaponAssessment` |
