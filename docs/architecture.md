# Architecture

## Operating context

Gauntlet runs exclusively as an MCP server inside a Claude Code session. There is no CLI, no GitHub-Actions entry point, no standalone invocation. The host Claude Code agent is the Attacker and the Inspector; Gauntlet provides the deterministic primitives.

Gauntlet does not call any LLM itself and requires no Anthropic/OpenAI credentials. The host already holds its own auth; Gauntlet just runs the deterministic pieces it is asked to run.

## Module map

```
gauntlet/
├── models.py    # Pydantic data models - the shared vocabulary with the host
│                #   (Action/Observation wrap HttpRequest/HttpResponse for
│                #   surface-agnostic execution)
├── auth.py      # user authentication config (BearerAuth, ApiKeyAuth, UsersConfig)
├── openapi.py   # OpenAPI 3.x spec parser - produces Target objects
├── roles.py     # WeaponAssessor protocol + DemoWeaponAssessor
├── adapters/    # Adapter protocol + concrete implementations
│   ├── __init__.py   # Adapter protocol (send + execute)
│   ├── http.py       # HttpApi (real HTTP) + InMemoryHttpApi (demo)
│   ├── cli.py        # CliAdapter (stub)
│   └── webdriver.py  # WebDriverAdapter (stub)
├── executor.py  # Drone - runs plans via Adapter.execute(Action) → Observation
├── loop.py      # build_default_iteration_specs + build_risk_report helpers
├── store.py     # PlanStore and FindingsStore - disk-backed knowledge indexed by weapon ID
├── schemas/     # JSON Schema files for weapon / target / users / arsenal
└── server.py    # FastMCP server exposing the 7 gauntlet tools
```

Dependency order:

```
models  ←  auth
models  ←  adapters (http, cli, webdriver, __init__)
models  ←  openapi
models  ←  roles
models  ←  store
models + adapters  ←  executor
models  ←  loop
models + auth + openapi + roles + executor + loop + adapters  ←  server
```

Nothing imports from `server.py`. The MCP entry point (`main()` in `server.py`) runs `FastMCP.run()` which speaks stdio to the Claude Code process that launched it.

## MCP tool surface

| Tool | Returns | Side effect |
|---|---|---|
| `list_weapons(weapons_path, arsenal_path)` | `list[WeaponBrief]` (no blockers) | reads YAML from disk |
| `get_weapon(weapon_id, ...)` | `Weapon` (with blockers) | reads YAML from disk |
| `list_targets(targets_path, openapi_path)` | `list[Target]` | reads YAML / OpenAPI spec from disk |
| `execute_plan(url, plan, users_path)` | `ExecutionResult` | sends real HTTP requests to the SUT |
| `assess_weapon(weapon_id, target, ...)` | `WeaponAssessment` | reads YAML from disk |
| `assemble_run_report(iterations, holdout_results, threshold)` | `dict` with `risk_report` + `clearance` | none |
| `default_iteration_specs()` | `list[IterationSpec]` | none |

## Train/test split

The split is preserved by host-side prompt discipline, not by Gauntlet's runtime:

- The Attacker context may read `list_weapons` (briefs have no blockers) and call `execute_plan`, but must never read `get_weapon` output - that would leak blocker text.
- The HoldoutEvaluator context reads `get_weapon`, constructs acceptance plans from the blockers, and calls `execute_plan` to run them. Results feed into `assemble_run_report` via the `holdout_results` argument.
- The Inspector context reads `ExecutionResult` objects to produce `Finding`s. It does not read blockers.

## Host-driven loop shape

```
(host agent in a Claude Code session)
│
├── Orchestrator context:
│     list_weapons() → pick a weapon
│     list_targets() → pick a target
│     assess_weapon(id, target) → optional preflight
│     default_iteration_specs() → reference ladder
│
├── For each iteration spec (typically 4):
│   ├── Attacker context:
│   │     generate Plan(s) from spec + prior findings
│   │     (never reads blockers)
│   │
│   ├── Orchestrator context:
│   │     execute_plan(url, plan) → ExecutionResult
│   │
│   └── Inspector context:
│         analyze ExecutionResult(s) → Finding(s)
│         (never reads blockers)
│
├── HoldoutEvaluator context:
│     get_weapon(id) → full Weapon (with blockers)
│     derive acceptance plans from blockers
│     execute_plan(url, plan) per holdout plan → ExecutionResult
│
└── Orchestrator context:
      assemble_run_report(iterations, holdout_results) → RiskReport + Clearance
```

## Deterministic vs non-deterministic segments

**Deterministic (no network, no LLM):**

- `InMemoryHttpApi` - in-memory REST API with three seeded flaws: (1) PATCH without ownership check, (2) POST accepts invalid data types for title and missing required fields, (3) GET /tasks leaks all tasks regardless of ownership. Ships with the library as a working example SUT.
- `Drone` - resolves path templates, calls the adapter, evaluates assertions.
- Assertion evaluation, risk-report assembly, weapon assessment - all pure Python.

**Non-deterministic (network):**

- `HttpApi` - sends real HTTP requests; outcome depends on the running server.

The host itself is non-deterministic (it's an LLM agent), but Gauntlet doesn't run the host. Gauntlet's own code is deterministic end-to-end.

## Design decisions

**Why MCP only?** Gauntlet's consumer is the dark-factory pipeline, which runs inside Claude Code. Keeping CLI + MCP + library surfaces in parallel multiplied integration cost without adding value for the one consumer that actually uses it. MCP is the one surface that lets the host drive Gauntlet as a tool inside its own loop.

**Why Pydantic?** All interchange objects are `BaseModel` subclasses with `extra="forbid"`. This catches schema drift early and makes JSON serialization/deserialization free - including over the MCP tool boundary.

**Why Protocols instead of ABCs?** Structural subtyping lets callers pass any object that has the right methods without importing from `gauntlet`. Only `WeaponAssessor` remains as a protocol now that Attacker/Inspector are host-driven.

**Why separate auth.py?** User credentials involve secret resolution from env vars. Isolating this in `auth.py` keeps the rest of the codebase free of secret-handling logic.

**Why Action/Observation instead of passing HttpRequest/HttpResponse directly?** The adversarial loop should not be coupled to a single execution surface. Action wraps an HttpRequest today and will wrap CLI commands or WebDriver interactions in the future; Observation wraps the corresponding response. The Drone converts between the two layers.

**Why host-driven Attacker/Inspector?** Because Gauntlet runs inside Claude Code, the host already has an LLM ready to play both roles. Re-invoking a separate Anthropic or OpenAI client from Gauntlet's own process would require credentials Gauntlet doesn't have a clean way to acquire, and would duplicate reasoning capacity the host already provides.

**Why Arsenals?** Individual weapons test one property at a time, which is the right granularity for authoring and debugging. An Arsenal groups related weapons under one YAML file so the host can select an entire attack class (authorization, input validation, OWASP top-10) as a unit.
